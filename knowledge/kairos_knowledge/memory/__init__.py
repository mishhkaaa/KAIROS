"""Memory manager (blueprint §19-20): working / episodic / semantic memory.

Owner: P2 — Knowledge, Memory & Console

TODO:
  - [x] store/recall with embeddings (Postgres table memories)
  - [x] build_working_set: LOAD + EVICT under a token budget; quote flagged evidence as untrusted data
  - [x] summarize, consolidate(task_id), rehydrate(pid)
"""

from __future__ import annotations

import json
from typing import Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    Event,
    EventType,
    EvidenceSet,
    InvalidationReport,
    MemoryQuery,
    MemoryRecord,
    WorkingSet,
    WorkingSetItem,
)
from kairos_contracts.schema.common import new_id, utcnow
from kairos_contracts.util import estimate_tokens

from ..indexing.store import EMBED_SCHEME, PgStore

# A memory with no word in common with the query is recalled only if its cosine similarity reaches this.
# Tuned on nomic-embed-text (768-dim): related paraphrases 0.375-0.839 (median 0.51), unrelated pairs 0.320-0.408.
RECALL_KEYWORD_GATE_COSINE = 0.42

_INVALIDATE_CTE = """
WITH RECURSIVE dep(id) AS (
  SELECT memory_id FROM memories WHERE %s = ANY(derived_from)
  UNION SELECT m.memory_id FROM memories m JOIN dep ON dep.id = ANY(m.derived_from))
UPDATE memories SET stale = true WHERE memory_id IN (SELECT id FROM dep) AND NOT stale
RETURNING memory_id, owner;
"""

RECONSOLIDATE_PROMPT = (
    "A finding an agent stored earlier rests on documents that have since changed. Rewrite the finding so it matches "
    "the current documents: one or two sentences, keep figures the documents still support, correct the ones they no "
    "longer support, and add nothing they don't say. Reply with the finding only.\n\n"
    "Earlier finding:\n{finding}\n\nCurrent documents:\n{documents}"
)


class MemoryManager:
    def __init__(self, store: PgStore, models: Any, event_bus: Any = None) -> None:
        self.pg = store
        self.models = models
        self.bus = event_bus
        self._migrated = False
        # Set by the factory when coherence runs: invalidations then say a re-consolidation is queued, and coherence
        # calls reconsolidate() once the changed document has been reindexed.
        self.reconsolidate_stale = False

    async def _ensure_ready(self) -> None:
        if self._migrated:
            return
        if self.models is not None:
            from kairos_contracts.schema import EmbedRequest

            probe = await self.models.embed(EmbedRequest(texts=["_dimension_probe_"], input_type="document"))
            dim, model_name = probe.dim, f"{probe.model}+{EMBED_SCHEME}"
        else:
            dim, model_name = 64, "none"
        await self.pg.migrate(dim, model_name)
        self._migrated = True

    async def _embed(self, text: str, input_type: str) -> list[float] | None:
        if self.models is None:
            return None
        from kairos_contracts.schema import EmbedRequest

        return (await self.models.embed(EmbedRequest(texts=[text], input_type=input_type))).vectors[0]

    async def store(self, record: MemoryRecord) -> str:
        await self._ensure_ready()
        vec = await self._embed(record.summary or record.content, "document")
        async with self.pg.connection() as conn:
            await conn.execute(
                "INSERT INTO memories(memory_id, kind, scope, org_id, owner, task_id, content, summary, "
                "derived_from, tags, importance, stale, created_at, last_used_at, embedding) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (memory_id) DO UPDATE SET kind=EXCLUDED.kind, scope=EXCLUDED.scope, "
                "org_id=EXCLUDED.org_id, owner=EXCLUDED.owner, task_id=EXCLUDED.task_id, content=EXCLUDED.content, "
                "summary=EXCLUDED.summary, derived_from=EXCLUDED.derived_from, tags=EXCLUDED.tags, "
                "importance=EXCLUDED.importance, stale=EXCLUDED.stale, embedding=EXCLUDED.embedding",
                (
                    record.memory_id,
                    record.kind.value,
                    record.scope.value,
                    record.org_id,
                    record.owner,
                    record.task_id,
                    record.content,
                    record.summary,
                    record.derived_from,
                    record.tags,
                    record.importance,
                    record.stale,
                    record.created_at,
                    record.last_used_at,
                    vec,
                ),
            )
            await conn.commit()
        return record.memory_id

    async def recall(self, query: MemoryQuery) -> list[MemoryRecord]:
        await self._ensure_ready()
        qvec = await self._embed(query.text, "query") if query.text else None
        where = ["org_id = %s", "kind = ANY(%s)", "scope = ANY(%s)"]
        params: list[Any] = [query.org_id, [k.value for k in query.kinds], [s.value for s in query.scopes]]
        if query.owner:
            where.append("owner = %s")
            params.append(query.owner)
        if query.task_id:
            where.append("task_id = %s")
            params.append(query.task_id)
        if not query.include_stale:
            where.append("NOT stale")
        sql = f"SELECT * FROM memories WHERE {' AND '.join(where)}"
        async with self.pg.connection() as conn:
            cur = await conn.execute(sql, params)
            rows = await cur.fetchall()

        q_terms = set(_terms(query.text))
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            keyword_overlap = 0.0
            if q_terms:
                doc_terms = set(_terms((row["content"] or "") + " " + " ".join(row["tags"] or [])))
                keyword_overlap = len(q_terms & doc_terms) / len(q_terms)
            cosine = 0.0
            if qvec is not None and row.get("embedding") is not None:
                emb = row["embedding"]
                cosine = _cosine(qvec, emb.to_list() if hasattr(emb, "to_list") else list(emb))
            if q_terms and keyword_overlap == 0.0 and cosine < RECALL_KEYWORD_GATE_COSINE:
                continue  # neither a shared word nor strong similarity: not relevant, however much memory exists
            score = 0.6 * cosine + 0.3 * keyword_overlap + 0.1 * (row["importance"] or 0.0)
            scored.append((score, row))
        scored.sort(key=lambda x: -x[0])
        top = scored[: query.top_k]

        ids = [row["memory_id"] for _, row in top]
        if ids:
            async with self.pg.connection() as conn:
                await conn.execute("UPDATE memories SET last_used_at = %s WHERE memory_id = ANY(%s)", (utcnow(), ids))
                await conn.commit()
        return [_row_to_record(row) for _, row in top]

    async def build_working_set(
        self, pid: int, goal: str, evidence: EvidenceSet, memories: list[MemoryRecord], token_budget: int
    ) -> WorkingSet:
        await self._ensure_ready()
        ws = WorkingSet(pid=pid, token_budget=token_budget)

        def add(item: WorkingSetItem) -> None:
            if ws.tokens_used + item.tokens <= token_budget or item.pinned:
                ws.items.append(item)
                ws.tokens_used += item.tokens

        add(WorkingSetItem(ref="inline", source="plan", content=goal, tokens=estimate_tokens(goal), pinned=True))
        for h in evidence.hits:
            text = h.body or h.snippet
            if h.firewall_flags:
                text = f"<untrusted-data flags={','.join(h.firewall_flags)}>\n{text}\n</untrusted-data>"
            add(WorkingSetItem(ref=h.path, source="evidence", content=text, tokens=estimate_tokens(text)))
        for m in memories:
            text = m.summary or m.content
            add(WorkingSetItem(ref=m.memory_id, source="memory", content=text, tokens=estimate_tokens(text)))

        async with self.pg.connection() as conn:
            await conn.execute(
                "INSERT INTO working_sets(pid, data, updated_at) VALUES (%s,%s,%s) "
                "ON CONFLICT (pid) DO UPDATE SET data = EXCLUDED.data, updated_at = EXCLUDED.updated_at",
                (pid, ws.model_dump_json(), utcnow()),
            )
            await conn.commit()
        return ws

    async def summarize(self, memory_ids: list[str]) -> MemoryRecord:
        await self._ensure_ready()
        async with self.pg.connection() as conn:
            cur = await conn.execute("SELECT * FROM memories WHERE memory_id = ANY(%s)", (memory_ids,))
            rows = await cur.fetchall()
        if not rows:
            raise KairosError("NOT_FOUND", f"no memories {memory_ids}")
        rows_by_id = {r["memory_id"]: r for r in rows}
        ordered = [rows_by_id[i] for i in memory_ids if i in rows_by_id]
        first = ordered[0]
        content = " / ".join((r["summary"] or r["content"]) for r in ordered)[:2000]

        if self.models is not None:
            from kairos_contracts.schema import ChatMessage, ModelRequest, Role
            from kairos_contracts.schema.common import PrivacyLevel
            from kairos_contracts.schema.inference import TaskClass

            resp = await self.models.generate(
                ModelRequest(
                    messages=[ChatMessage(role=Role.USER, content=f"Summarize concisely:\n{content}")],
                    task_class=TaskClass.SUMMARIZATION,
                    privacy=PrivacyLevel.INTERNAL,
                )
            )
            content = resp.content[:2000] or content

        rec = MemoryRecord(
            memory_id=new_id("MEM"),
            kind=first["kind"],
            scope=first["scope"],
            org_id=first["org_id"],
            owner=first["owner"],
            content=content,
            derived_from=memory_ids,
        )
        await self.store(rec)
        return rec

    async def consolidate(self, task_id: str) -> list[MemoryRecord]:
        await self._ensure_ready()
        async with self.pg.connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM memories WHERE task_id = %s AND kind = 'episodic' AND importance >= 0.5", (task_id,)
            )
            rows = await cur.fetchall()

        by_owner: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_owner.setdefault(row["owner"], []).append(row)

        out: list[MemoryRecord] = []
        for owner, owner_rows in by_owner.items():
            derived_from = [r["memory_id"] for r in owner_rows]
            derived_from += [p for r in owner_rows for p in (r["derived_from"] or [])]
            content = " / ".join((r["summary"] or r["content"]) for r in owner_rows)[:2000]
            if self.models is not None:
                from kairos_contracts.schema import ChatMessage, ModelRequest, Role
                from kairos_contracts.schema.common import PrivacyLevel
                from kairos_contracts.schema.inference import TaskClass

                resp = await self.models.generate(
                    ModelRequest(
                        messages=[ChatMessage(role=Role.USER, content=f"Summarize as a durable fact:\n{content}")],
                        task_class=TaskClass.SUMMARIZATION,
                        privacy=PrivacyLevel.INTERNAL,
                    )
                )
                content = resp.content[:2000] or content
            rec = MemoryRecord(
                memory_id=new_id("MEM"),
                kind="semantic",
                scope=owner_rows[0]["scope"],
                org_id=owner_rows[0]["org_id"],
                owner=owner,
                task_id=task_id,
                content=content,
                derived_from=sorted(set(derived_from)),
            )
            await self.store(rec)
            out.append(rec)

        if self.bus is not None and out:
            await self.bus.publish(
                Event(type=EventType.MEMORY_CONSOLIDATED, source="memory.manager", payload={"created": len(out)})
            )
        return out

    async def invalidate(self, source: str) -> InvalidationReport:
        await self._ensure_ready()
        async with self.pg.connection() as conn:
            cur = await conn.execute(_INVALIDATE_CTE, (source,))
            rows = await cur.fetchall()
            await conn.commit()
        stale = [r["memory_id"] for r in rows]
        report = InvalidationReport(source=source, invalidated=stale, affected_agents=sorted({r["owner"] for r in rows}),
                                    reconsolidation_queued=self.reconsolidate_stale and bool(stale))
        if self.bus is not None and stale:
            await self.bus.publish(
                Event(type=EventType.MEMORY_INVALIDATED, source="memory.manager", payload=report.model_dump(mode="json"))
            )
        return report

    async def reconsolidate(self, memory_ids: list[str]) -> list[MemoryRecord]:
        """Re-derive stale memories from the current text of their /org sources (blueprint §21: invalidation and
        recomputation). Each gets a new memory with the same owner, task, kind and sources, tagged reconsolidated and
        replaces:<old id>; the stale one stays for history. Memories without /org sources are left as they are."""
        await self._ensure_ready()
        if self.models is None or not memory_ids:
            return []
        async with self.pg.connection() as conn:
            cur = await conn.execute("SELECT * FROM memories WHERE memory_id = ANY(%s) AND stale", (memory_ids,))
            rows = await cur.fetchall()
        from kairos_contracts.schema import ChatMessage, ModelRequest, Role
        from kairos_contracts.schema.common import PrivacyLevel
        from kairos_contracts.schema.inference import TaskClass

        out: list[MemoryRecord] = []
        for row in rows:
            sources = [p for p in (row["derived_from"] or []) if p.startswith("/org")]
            docs = await self.pg.get_object_rows(sources)
            if not docs:
                continue
            documents = "\n\n".join(f"[{p}]\n{(docs[p]['body'] or '')[:1500]}" for p in sources if p in docs)
            resp = await self.models.generate(ModelRequest(
                messages=[ChatMessage(role=Role.USER, content=RECONSOLIDATE_PROMPT.format(
                    finding=row["summary"] or row["content"], documents=documents))],
                task_class=TaskClass.SUMMARIZATION, privacy=PrivacyLevel.INTERNAL, max_tokens=300))
            content = (resp.content or "").strip()[:2000]
            if not content:
                continue
            rec = MemoryRecord(
                memory_id=new_id("MEM"), kind=row["kind"], scope=row["scope"], org_id=row["org_id"], owner=row["owner"],
                task_id=row["task_id"], content=content, derived_from=sources, importance=row["importance"] or 0.5,
                tags=[*(t for t in (row["tags"] or []) if not t.startswith("replaces:")), "reconsolidated", f"replaces:{row['memory_id']}"],
            )
            await self.store(rec)
            out.append(rec)
        if self.bus is not None and out:
            await self.bus.publish(Event(type=EventType.MEMORY_CONSOLIDATED, source="memory.reconsolidate",
                                         payload={"created": len(out)}))
        return out

    async def rehydrate(self, pid: int) -> WorkingSet | None:
        await self._ensure_ready()
        async with self.pg.connection() as conn:
            cur = await conn.execute("SELECT data FROM working_sets WHERE pid = %s", (pid,))
            row = await cur.fetchone()
        if row is None:
            return None
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)
        return WorkingSet.model_validate(data)


def _terms(text: str) -> list[str]:
    return [t for t in text.lower().split() if t]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))


def _row_to_record(row: dict[str, Any]) -> MemoryRecord:
    return MemoryRecord(
        memory_id=row["memory_id"],
        kind=row["kind"],
        scope=row["scope"],
        org_id=row["org_id"],
        owner=row["owner"],
        task_id=row["task_id"],
        content=row["content"],
        summary=row["summary"],
        derived_from=row["derived_from"] or [],
        tags=row["tags"] or [],
        importance=row["importance"] if row["importance"] is not None else 0.5,
        stale=row["stale"],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
    )


__all__ = ["MemoryManager"]
