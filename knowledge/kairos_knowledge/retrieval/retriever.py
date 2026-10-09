"""Hybrid retrieval: lexical (FTS) + semantic (pgvector) + graph neighbours, fused with RRF.

Owner: P2 — Knowledge, Memory & Console
"""

from __future__ import annotations

import time
from typing import Any

from kairos_contracts.schema import EvidenceSet, Principal, SearchHit, SearchMode, SearchQuery
from kairos_contracts.schema.common import PrivacyLevel, TrustLevel
from kairos_contracts.util import path_allowed, privacy_allows

from ..indexing.store import PgStore

_RRF_K = 60
# Weighted RRF. Graph neighbours of the top hits are an expansion signal, not a ranking of relevance: at weight 1 they
# outranked the best lexical/semantic matches (retrieval QA on the demo bundle fell from 8/10 lexical-only to 1/10).
# Checked with real embeddings (nomic-embed-text): graph 0 and 0.1 give 9/10 with the same ranks, 0.25 slips, 0.5+ collapses.
MODE_WEIGHTS = {"lexical": 1.0, "semantic": 1.0, "graph": 0.1}
SNIPPET_CHARS = 400  # enough for a finance table row or two; the firewall still screens the full body
_PER_MODE_LIMIT = 50
_TRUST_ORDER = [TrustLevel.UNTRUSTED, TrustLevel.UNVERIFIED, TrustLevel.TRUSTED, TrustLevel.VERIFIED]
_PRIVACY_ORDER = [PrivacyLevel.PUBLIC, PrivacyLevel.INTERNAL, PrivacyLevel.CONFIDENTIAL, PrivacyLevel.RESTRICTED]


class _Candidate:
    __slots__ = ("path", "ranks", "best_chunk")

    def __init__(self, path: str) -> None:
        self.path = path
        self.ranks: dict[str, int] = {}  # mode -> 1-based rank
        self.best_chunk: dict[str, Any] | None = None

    def rrf_score(self) -> float:
        return sum(MODE_WEIGHTS.get(m, 1.0) / (_RRF_K + r) for m, r in self.ranks.items())


class HybridRetriever:
    def __init__(self, store: PgStore, models: Any, firewall: Any) -> None:
        self.store = store
        self.models = models
        self.firewall = firewall

    async def search(self, query: SearchQuery, principal: Principal) -> EvidenceSet:
        t0 = time.monotonic()
        min_trust_values = [t.value for t in _TRUST_ORDER[_TRUST_ORDER.index(query.min_trust) :]]
        candidates: dict[str, _Candidate] = {}

        if SearchMode.LEXICAL in query.modes:
            rows = await self.store.lexical_search(
                query.text, query.scope, query.types, query.tags, min_trust_values, _PER_MODE_LIMIT
            )
            self._apply_mode(candidates, rows, "lexical")

        if SearchMode.SEMANTIC in query.modes and self.models is not None:
            from kairos_contracts.schema import EmbedRequest

            qvec = (await self.models.embed(EmbedRequest(texts=[query.text], input_type="query"))).vectors[0]
            rows = await self.store.semantic_search(qvec, query.scope, query.types, query.tags, min_trust_values, _PER_MODE_LIMIT)
            self._apply_mode(candidates, rows, "semantic")

        if SearchMode.GRAPH in query.modes:
            seeds = sorted(candidates.values(), key=lambda c: c.rrf_score(), reverse=True)[:5]
            seed_paths = [c.path for c in seeds]
            if seed_paths:
                edges = await self.store.neighbors(seed_paths)
                neighbor_paths: list[str] = []
                for e in edges:
                    for p in (e["dst"], e["src"]):
                        if p not in seed_paths and p not in neighbor_paths:
                            neighbor_paths.append(p)
                for rank, path in enumerate(neighbor_paths, start=1):
                    cand = candidates.setdefault(path, _Candidate(path))
                    cand.ranks["graph"] = rank

        total_candidates = len(candidates)

        objects = await self.store.get_object_rows(list(candidates))
        filtered = 0
        visible: list[_Candidate] = []
        for path, cand in candidates.items():
            obj = objects.get(path)
            if obj is None:
                continue
            # Scope AND privacy are checked here in Python, not in the SQL base filter, so that objects hidden by
            # privacy are counted in filtered_by_policy (brief §12). Cheap at demo scale; don't move privacy into
            # SQL without another way to count what it removes.
            ok = path_allowed(path, principal.data_scopes) and privacy_allows(PrivacyLevel(obj["privacy"]), principal.max_privacy)
            if not ok:
                filtered += 1
                continue
            visible.append(cand)

        visible.sort(key=lambda c: c.rrf_score(), reverse=True)
        top = visible[: query.top_k]

        max_per_mode: dict[str, float] = {}
        for cand in visible:
            for mode, rank in cand.ranks.items():
                raw = 1.0 / (_RRF_K + rank)
                max_per_mode[mode] = max(max_per_mode.get(mode, 0.0), raw)

        hits: list[SearchHit] = []
        for cand in top:
            obj = objects[cand.path]
            scores = {}
            for mode, rank in cand.ranks.items():
                raw = 1.0 / (_RRF_K + rank)
                denom = max_per_mode.get(mode) or 1.0
                scores[mode] = round(raw / denom, 4)
            snippet = self._snippet_for(cand, obj)
            hits.append(
                SearchHit(
                    path=cand.path,
                    title=obj["title"],
                    type=obj["type"],
                    snippet=snippet,
                    chunk_id=cand.best_chunk["chunk_id"] if cand.best_chunk else None,
                    score=round(cand.rrf_score(), 6),
                    scores=scores,
                    provenance=_provenance_from_row(obj),
                    body=obj["body"],
                )
            )

        if self.firewall is not None:
            hits = await self.firewall.screen(hits)
        if not query.include_body:
            hits = [h.model_copy(update={"body": None}) for h in hits]

        return EvidenceSet(
            query=query,
            hits=hits,
            total_candidates=total_candidates,
            filtered_by_policy=filtered,
            took_ms=(time.monotonic() - t0) * 1000,
        )

    def _apply_mode(self, candidates: dict[str, _Candidate], rows: list[dict[str, Any]], mode: str) -> None:
        seen_paths: list[str] = []
        for row in rows:
            path = row["path"]
            if path not in seen_paths:
                seen_paths.append(path)
        for rank, path in enumerate(seen_paths, start=1):
            cand = candidates.setdefault(path, _Candidate(path))
            cand.ranks[mode] = rank
            if cand.best_chunk is None:
                for row in rows:
                    if row["path"] == path:
                        cand.best_chunk = row
                        break

    def _snippet_for(self, cand: _Candidate, obj: dict[str, Any]) -> str:
        if cand.best_chunk and cand.best_chunk.get("text"):
            return snippet_of(cand.best_chunk["text"])
        return snippet_of(obj.get("body") or "")


def snippet_of(text: str, width: int = SNIPPET_CHARS) -> str:
    """The chunk's content, not its heading: agents only see snippets (a title-only snippet made them invent numbers).
    Markdown heading lines are dropped, whitespace collapsed, cut at a word boundary."""
    flat = " ".join(line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))
    flat = " ".join(flat.split())
    if len(flat) <= width:
        return flat
    cut = flat[:width].rsplit(" ", 1)[0]
    return f"{cut} …"


def _provenance_from_row(obj: dict[str, Any]):
    from kairos_contracts.schema import Provenance

    fm = obj.get("frontmatter") or {}
    if isinstance(fm, str):
        import json

        fm = json.loads(fm)
    return Provenance(
        source=fm.get("source") or "okf",
        source_ref=obj["okf_file"],
        source_version=fm.get("source_version"),
        created_at=fm.get("created_at"),
        updated_at=fm.get("updated_at"),
        author=fm.get("author"),
        generator=fm.get("generator"),
        verification_status=fm.get("verification_status", "unverified"),
        trust=obj["trust"],
    )


__all__ = ["HybridRetriever"]
