"""Chunk OKF bodies by heading, embed them, and upsert into Postgres. Also derives graph edges.

Owner: P2 — Knowledge, Memory & Console
"""

from __future__ import annotations

import re
from typing import Any

from kairos_contracts.schema import KnowledgeObject
from kairos_contracts.util import estimate_tokens

from .store import PgStore

_HEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_MAX_CHUNK_TOKENS = 400
_EMBED_BATCH = 32


def chunk_body(title: str, body: str) -> list[tuple[str | None, str]]:
    """Split a document body into (heading, text) chunks by '##' headings, further splitting long
    sections on paragraph boundaries. Returns at least one chunk even for an empty body."""
    sections: list[tuple[str | None, str]] = []
    matches = list(_HEADING_RE.finditer(body))
    if not matches:
        sections.append((None, body.strip()))
    else:
        preamble = body[: matches[0].start()].strip()
        if preamble:
            sections.append((None, preamble))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            heading = m.group(1).strip()
            text = body[m.end() : end].strip()
            sections.append((heading, text))

    chunks: list[tuple[str | None, str]] = []
    for heading, text in sections:
        if not text:
            continue
        if estimate_tokens(text) <= _MAX_CHUNK_TOKENS:
            chunks.append((heading, text))
            continue
        buf: list[str] = []
        for para in text.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            candidate = "\n\n".join([*buf, para])
            if buf and estimate_tokens(candidate) > _MAX_CHUNK_TOKENS:
                chunks.append((heading, "\n\n".join(buf)))
                buf = [para]
            else:
                buf.append(para)
        if buf:
            chunks.append((heading, "\n\n".join(buf)))
    if not chunks:
        chunks.append((None, ""))
    return chunks


class Indexer:
    def __init__(self, store: PgStore, models: Any) -> None:
        self.store = store
        self.models = models

    async def index_objects(self, objects: dict[str, KnowledgeObject], only_paths: set[str] | None = None) -> int:
        """Upsert okf_objects, then (re)chunk+embed+upsert chunks for changed paths only. Returns count reindexed."""
        existing_hashes = await self.store.content_hashes()
        has_chunks = await self.store.paths_with_chunks()
        targets = {p: o for p, o in objects.items() if only_paths is None or p in only_paths}
        changed = {p: o for p, o in targets.items() if existing_hashes.get(p) != o.content_hash or p not in has_chunks}

        for obj in targets.values():
            await self.store.upsert_object(obj)

        if changed:
            await self._reembed(changed)

        for path, obj in targets.items():
            await self.store.replace_edges_from(path, self._edges_for(obj, objects))

        return len(changed)

    async def _reembed(self, changed: dict[str, KnowledgeObject]) -> None:
        all_texts: list[str] = []
        index: list[tuple[str, str | None, str, str]] = []  # path, heading, text, embed_text
        for path, obj in changed.items():
            for heading, text in chunk_body(obj.frontmatter.title, obj.body):
                embed_text = f"{obj.frontmatter.title}\n{text}" if text else obj.frontmatter.title
                index.append((path, heading, text, embed_text))
                all_texts.append(embed_text)

        vectors: list[list[float]] = []
        for i in range(0, len(all_texts), _EMBED_BATCH):
            batch = all_texts[i : i + _EMBED_BATCH]
            if not batch:
                continue
            from kairos_contracts.schema import EmbedRequest

            resp = await self.models.embed(EmbedRequest(texts=batch, input_type="document"))
            vectors.extend(resp.vectors)

        by_path: dict[str, list[tuple[str, int, str | None, str, list[float]]]] = {}
        counters: dict[str, int] = {}
        for (path, heading, text, _embed_text), vec in zip(index, vectors, strict=True):
            ord_ = counters.get(path, 0)
            counters[path] = ord_ + 1
            chunk_id = f"{path}#{ord_}"
            by_path.setdefault(path, []).append((chunk_id, ord_, heading, text, vec))

        for path in changed:
            await self.store.replace_chunks(path, by_path.get(path, []))

    def _edges_for(self, obj: KnowledgeObject, objects: dict[str, KnowledgeObject]) -> list[tuple[str, str, float]]:
        edges: list[tuple[str, str, float]] = []
        for dst in obj.links:
            edges.append((dst, "links_to", 1.0))
        for related in obj.frontmatter.related:
            dst = related if related.startswith("/org") else None
            if dst and dst.rstrip("/") not in {e[0] for e in edges}:
                edges.append((dst.rstrip("/"), "related_to", 1.0))
        if obj.frontmatter.owner:
            owner_path = f"/org/people/{obj.frontmatter.owner}"
            if owner_path in objects:
                edges.append((owner_path, "owned_by", 1.0))
        if obj.frontmatter.type == "project":
            for other in objects.values():
                if other.frontmatter.type == "decision" and other.path in obj.links:
                    edges.append((other.path, "decided_in", 1.0))
        return edges


__all__ = ["Indexer", "chunk_body"]
