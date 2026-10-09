"""Postgres/pgvector access layer shared by the indexer, retriever, graph and memory manager.

Owner: P2 — Knowledge, Memory & Console
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

logger = logging.getLogger("kairos.knowledge.store")

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
# How texts are presented to the embedding model (qd1: query/document task prefixes). It is part of the key stored in
# meta, so changing it drops the stored vectors and re-embeds everything, like a model change.
EMBED_SCHEME = "qd1"


def _to_psycopg_dsn(database_url: str) -> str:
    """SQLAlchemy-style 'postgresql+psycopg://...' -> plain 'postgresql://...' for psycopg."""
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@dataclass
class ChunkRow:
    chunk_id: str
    path: str
    ord: int
    heading: str | None
    text: str


_MAX_CONNECTIONS = 10
_LEXEME = re.compile(r"[a-z0-9]+")
_TITLE_BONUS = 0.5


class _Cursor:
    """Async view of a sync psycopg cursor; fetches run on a worker thread."""

    def __init__(self, cur: psycopg.Cursor) -> None:
        self._cur = cur

    async def fetchall(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._cur.fetchall)

    async def fetchone(self) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._cur.fetchone)


class _Connection:
    """Async view of a sync psycopg connection: every call runs on a worker thread (AGENTS.md rule 9), so the
    store works on any event loop. psycopg's own async mode can't run on Windows' ProactorEventLoop, which is
    uvicorn's default there and which Playwright and asyncio subprocesses need."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.raw = conn

    async def execute(self, query: str, params: Any = None) -> _Cursor:
        return _Cursor(await asyncio.to_thread(self.raw.execute, query, params))

    async def commit(self) -> None:
        await asyncio.to_thread(self.raw.commit)

    async def rollback(self) -> None:
        await asyncio.to_thread(self.raw.rollback)


class PgStore:
    """Thin async wrapper over the kairos Postgres schema (§6.3 of the P2 brief).

    Connections come from a minimal pool with no background tasks: idle connections behind a semaphore. Services
    get no close() call from the kernel, so nothing here may outlive the event loop (psycopg_pool's maintenance
    workers did, and kept asyncio.run() from returning). close() is still the tidy way to release connections.
    """

    def __init__(self, database_url: str) -> None:
        self.database_url = _to_psycopg_dsn(database_url)
        self._idle: list[_Connection] = []
        self._slots: asyncio.Semaphore | None = None
        self._vector_ready = False
        self._idf_cache: tuple[dict[str, float], float] | None = None
        self.dim: int | None = None

    def _connect_sync(self) -> psycopg.Connection:
        conn = psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=5)
        if not self._vector_ready:
            # register_vector needs the extension; on a brand-new database migrate() hasn't created it yet.
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.commit()
            self._vector_ready = True
        register_vector(conn)
        return conn

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[_Connection]:
        """One connection for a unit of work. Anything left uncommitted is rolled back when it's returned."""
        if self._slots is None:
            self._slots = asyncio.Semaphore(_MAX_CONNECTIONS)
        async with self._slots:
            conn = None
            while self._idle and conn is None:
                candidate = self._idle.pop()
                conn = None if candidate.raw.closed else candidate
            if conn is None:
                conn = _Connection(await asyncio.to_thread(self._connect_sync))
            try:
                yield conn
            finally:
                await asyncio.to_thread(self._release_sync, conn)

    def _release_sync(self, conn: _Connection) -> None:
        if conn.raw.closed:
            return
        try:
            if conn.raw.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                conn.raw.rollback()
        except psycopg.Error:
            conn.raw.close()
            return
        self._idle.append(conn)

    async def ping(self) -> bool:
        try:
            async with self.connection() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001 — connectivity probe, any failure means "unreachable"
            return False

    async def close(self) -> None:
        idle, self._idle = self._idle, []
        for conn in idle:
            await asyncio.to_thread(conn.raw.close)

    # --------------------------------------------------------------------- migration

    async def migrate(self, dim: int, model_name: str) -> None:
        """Idempotent. Drops embedding-bearing data and warns if the model/dim changed."""
        self.dim = dim
        async with self.connection() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute("CREATE TABLE IF NOT EXISTS meta(key text PRIMARY KEY, value text)")
            cur = await conn.execute("SELECT key, value FROM meta WHERE key IN ('embedding_model', 'embedding_dim')")
            existing = {r["key"]: r["value"] for r in await cur.fetchall()}
            dim_changed = existing.get("embedding_dim") not in (None, str(dim))
            model_changed = existing.get("embedding_model") not in (None, model_name)
            memories_existed = False
            if dim_changed or model_changed:
                logger.warning(
                    "embedding model/dim changed (%s/%s -> %s/%s); dropping embedding-bearing data",
                    existing.get("embedding_model"),
                    existing.get("embedding_dim"),
                    model_name,
                    dim,
                )
                tables = {
                    r["tablename"]
                    for r in await (await conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).fetchall()
                }
                memories_existed = "memories" in tables
                if "chunks" in tables:
                    await conn.execute("DROP TABLE chunks")
                if memories_existed:
                    await conn.execute("ALTER TABLE memories DROP COLUMN IF EXISTS embedding")

            sql = _SCHEMA_PATH.read_text(encoding="utf-8").replace("__DIM__", str(dim))
            await conn.execute(sql)

            if memories_existed:
                # memories already existed and lost its embedding column above; schema.sql's
                # CREATE TABLE IF NOT EXISTS was a no-op for it, so add the column back at the new dim.
                await conn.execute(f"ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding vector({dim})")

            await conn.execute(
                "INSERT INTO meta(key, value) VALUES ('embedding_model', %s), ('embedding_dim', %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (model_name, str(dim)),
            )
            await conn.commit()

    # --------------------------------------------------------------------- okf_objects

    async def upsert_object(self, obj: Any) -> None:
        fm = obj.frontmatter
        async with self.connection() as conn:
            await conn.execute(
                "INSERT INTO okf_objects(path, okf_file, type, title, privacy, trust, tags, frontmatter, body, "
                "content_hash, version, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,now()) "
                "ON CONFLICT (path) DO UPDATE SET okf_file=EXCLUDED.okf_file, type=EXCLUDED.type, "
                "title=EXCLUDED.title, privacy=EXCLUDED.privacy, trust=EXCLUDED.trust, tags=EXCLUDED.tags, "
                "frontmatter=EXCLUDED.frontmatter, body=EXCLUDED.body, content_hash=EXCLUDED.content_hash, "
                "version=okf_objects.version + 1, updated_at=now()",
                (
                    obj.path,
                    obj.okf_file,
                    fm.type,
                    fm.title,
                    fm.privacy.value,
                    fm.trust.value,
                    fm.tags,
                    fm.model_dump_json(),
                    obj.body,
                    obj.content_hash,
                ),
            )
            await conn.commit()

    async def delete_object(self, path: str) -> None:
        async with self.connection() as conn:
            await conn.execute("DELETE FROM okf_objects WHERE path = %s", (path,))  # chunks cascade
            await conn.execute("DELETE FROM edges WHERE src = %s OR dst = %s", (path, path))
            await conn.commit()

    async def get_object_rows(self, paths: list[str]) -> dict[str, dict[str, Any]]:
        if not paths:
            return {}
        async with self.connection() as conn:
            cur = await conn.execute("SELECT * FROM okf_objects WHERE path = ANY(%s)", (paths,))
            return {r["path"]: r for r in await cur.fetchall()}

    async def get_object_row(self, path: str) -> dict[str, Any] | None:
        async with self.connection() as conn:
            cur = await conn.execute("SELECT * FROM okf_objects WHERE path = %s", (path,))
            return await cur.fetchone()

    async def content_hashes(self) -> dict[str, str]:
        async with self.connection() as conn:
            cur = await conn.execute("SELECT path, content_hash FROM okf_objects")
            return {r["path"]: r["content_hash"] for r in await cur.fetchall()}

    async def paths_with_chunks(self) -> set[str]:
        async with self.connection() as conn:
            cur = await conn.execute("SELECT DISTINCT path FROM chunks")
            return {r["path"] for r in await cur.fetchall()}

    async def all_paths(self) -> list[str]:
        async with self.connection() as conn:
            cur = await conn.execute("SELECT path FROM okf_objects")
            return [r["path"] for r in await cur.fetchall()]

    # --------------------------------------------------------------------- chunks

    async def replace_chunks(self, path: str, chunks: list[tuple[str, int, str | None, str, list[float]]]) -> None:
        """chunks: (chunk_id, ord, heading, text, embedding)."""
        self._idf_cache = None
        async with self.connection() as conn:
            await conn.execute("DELETE FROM chunks WHERE path = %s", (path,))
            for chunk_id, ord_, heading, text, embedding in chunks:
                await conn.execute(
                    "INSERT INTO chunks(chunk_id, path, ord, heading, text, embedding) VALUES (%s,%s,%s,%s,%s,%s)",
                    (chunk_id, path, ord_, heading, text, embedding),
                )
            await conn.commit()

    async def _idf(self, conn: _Connection) -> tuple[dict[str, float], float]:
        """BM25-style IDF per lexeme over all chunks (ts_stat), cached until chunks change."""
        if self._idf_cache is None:
            n = (await (await conn.execute("SELECT count(*) AS n FROM chunks")).fetchone())["n"]
            rows = await (await conn.execute("SELECT word, ndoc FROM ts_stat('SELECT tsv FROM chunks')")).fetchall()
            idf = {r["word"]: math.log((n - r["ndoc"] + 0.5) / (r["ndoc"] + 0.5) + 1) for r in rows}
            self._idf_cache = (idf, math.log(n + 1.5))
        return self._idf_cache

    async def lexical_search(
        self, query_text: str, scope: list[str], types: list[str], tags: list[str], min_trust_values: list[str], limit: int = 50
    ) -> list[dict[str, Any]]:
        """Full-text search ranked by the IDF of the query lexemes each chunk contains (title matches count extra).

        websearch_to_tsquery ANDs every word, so a natural question ("what caused the ledger migration backfill to
        fail?") only matched chunks that contained all of them; plain OR + ts_rank has no IDF, so a word found in
        every document ("apollo") decided the ranking. Every value is still passed as a parameter."""
        async with self.connection() as conn:
            rows = await (
                await conn.execute("SELECT unnest(tsvector_to_array(to_tsvector('english', %s))) AS l", (query_text,))
            ).fetchall()
            lexemes = sorted({r["l"] for r in rows if _LEXEME.fullmatch(r["l"])})
            if not lexemes:
                return []
            idf, unseen = await self._idf(conn)
            where, params = self._base_where(scope, types, tags, min_trust_values)
            title_vec = "to_tsvector('english', coalesce(o.title, ''))"
            where.append(f"(c.tsv @@ to_tsquery('simple', %s) OR {title_vec} @@ to_tsquery('simple', %s))")
            any_term = " | ".join(lexemes)
            terms = " + ".join(
                f"%s * ((c.tsv @@ to_tsquery('simple', %s))::int + {_TITLE_BONUS} * ({title_vec} @@ to_tsquery('simple', %s))::int)"
                for _ in lexemes
            )
            term_params: list[Any] = []
            for lx in lexemes:
                term_params += [idf.get(lx, unseen), lx, lx]
            sql = (
                f"SELECT c.chunk_id, c.path, c.ord, c.heading, c.text, ({terms}) AS rank "
                "FROM chunks c JOIN okf_objects o ON o.path = c.path "
                f"WHERE {' AND '.join(where)} ORDER BY rank DESC, length(c.text) ASC LIMIT %s"
            )
            cur = await conn.execute(sql, (*term_params, *params, any_term, any_term, limit))
            return await cur.fetchall()

    async def semantic_search(
        self,
        query_vec: list[float],
        scope: list[str],
        types: list[str],
        tags: list[str],
        min_trust_values: list[str],
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        where, params = self._base_where(scope, types, tags, min_trust_values)
        sql = (
            "SELECT c.chunk_id, c.path, c.ord, c.heading, c.text, (c.embedding <=> %s) AS dist "
            "FROM chunks c JOIN okf_objects o ON o.path = c.path "
            f"WHERE {' AND '.join(where)} AND c.embedding IS NOT NULL ORDER BY c.embedding <=> %s LIMIT %s"
        )
        qv = Vector(query_vec)
        async with self.connection() as conn:
            cur = await conn.execute(sql, (qv, *params, qv, limit))
            return await cur.fetchall()

    def _base_where(
        self, scope: list[str], types: list[str], tags: list[str], min_trust_values: list[str]
    ) -> tuple[list[str], list[Any]]:
        where: list[str] = []
        params: list[Any] = []
        if scope:
            clauses = []
            for s in scope:
                s = s.rstrip("/")
                clauses.append("(o.path = %s OR o.path LIKE %s)")
                params.extend([s, s + "/%"])
            where.append("(" + " OR ".join(clauses) + ")")
        if types:
            where.append("o.type = ANY(%s)")
            params.append(types)
        if tags:
            where.append("o.tags && %s")
            params.append(tags)
        if min_trust_values:
            where.append("o.trust = ANY(%s)")
            params.append(min_trust_values)
        if not where:
            where.append("TRUE")
        return where, params

    # --------------------------------------------------------------------- edges

    async def replace_edges_from(self, src: str, edges: list[tuple[str, str, float]]) -> None:
        """edges: (dst, relation, weight) — all outgoing edges of `src` are replaced."""
        async with self.connection() as conn:
            await conn.execute("DELETE FROM edges WHERE src = %s", (src,))
            for dst, relation, weight in edges:
                await conn.execute(
                    "INSERT INTO edges(src, dst, relation, weight) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (src, dst, relation) DO UPDATE SET weight = EXCLUDED.weight",
                    (src, dst, relation, weight),
                )
            await conn.commit()

    async def neighbors(self, paths: list[str], relations: list[str] | None = None) -> list[dict[str, Any]]:
        if not paths:
            return []
        where = "(src = ANY(%s) OR dst = ANY(%s))"
        params: list[Any] = [paths, paths]
        if relations:
            where += " AND relation = ANY(%s)"
            params.append(relations)
        async with self.connection() as conn:
            cur = await conn.execute(f"SELECT src, dst, relation, weight FROM edges WHERE {where}", params)
            return await cur.fetchall()


__all__ = ["PgStore", "ChunkRow"]
