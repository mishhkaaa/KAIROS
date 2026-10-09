"""Recall of paraphrased memories with the real embedding model. Needs Postgres and Ollama with the embedding model
pulled; skips otherwise. Talks to Ollama's HTTP API directly (P3's router is another split's package)."""

import asyncio
from uuid import uuid4

import httpx
import pytest
from kairos_contracts.schema import EmbedResponse, MemoryKind, MemoryQuery, MemoryRecord, MemoryScope
from kairos_contracts.schema.common import new_id
from kairos_contracts.wiring import Settings
from kairos_knowledge.indexing.store import PgStore
from kairos_knowledge.memory import MemoryManager

from .test_contract import _postgres_reachable

MODEL = "nomic-embed-text"


class _OllamaEmbeddings:
    def __init__(self, url: str) -> None:
        self.url = url

    async def embed(self, request):
        async with httpx.AsyncClient(base_url=self.url, timeout=120) as c:
            r = await c.post("/api/embed", json={"model": MODEL, "input": request.texts})
            r.raise_for_status()
            vecs = r.json()["embeddings"]
        return EmbedResponse(model=MODEL, dim=len(vecs[0]), vectors=vecs)


def _ollama_ready(url: str) -> bool:
    try:
        tags = httpx.get(f"{url}/api/tags", timeout=2).json().get("models", [])
    except httpx.HTTPError:
        return False
    return any(m["name"].split(":")[0] == MODEL for m in tags)


def _ensure_database(database_url: str, name: str) -> None:
    """Create `name` on the same server if it's missing (a fresh setup has only the configured database)."""
    import psycopg

    from .test_contract import _to_psycopg_dsn

    with psycopg.connect(_to_psycopg_dsn(database_url), autocommit=True, connect_timeout=2) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            conn.execute(f'CREATE DATABASE "{name}"')


def test_paraphrase_without_shared_words_is_recalled():
    s = Settings.from_env()  # .env points tests at the test server; without it this silently skipped when run alone
    if not _postgres_reachable(s.database_url) or not _ollama_ready(s.ollama_url):
        pytest.skip(f"needs Postgres and Ollama with {MODEL}")
    # its own database: 768-dim real embeddings must not flip the 64-dim test database back and forth
    db = s.database_url.rsplit("/", 1)[0] + "/kairos_real"
    _ensure_database(s.database_url, "kairos_real")
    org = f"org-{uuid4().hex[:8]}"

    def rec(content: str) -> MemoryRecord:
        return MemoryRecord(
            memory_id=new_id("MEM"),
            kind=MemoryKind.EPISODIC,
            scope=MemoryScope.AGENT,
            org_id=org,
            owner="finance-agent",
            content=content,
            derived_from=[],
        )

    async def go():
        m = MemoryManager(PgStore(db), _OllamaEmbeddings(s.ollama_url))
        near, far = rec("AWS bill doubled after the migration"), rec("lunch menu rotation for the cafeteria")
        await m.store(near)
        await m.store(far)
        got = await m.recall(MemoryQuery(text="cloud overrun", org_id=org))
        await m.pg.close()
        return near, far, [r.memory_id for r in got]

    near, far, ids = asyncio.run(go())
    assert near.memory_id in ids, "a paraphrase with no shared words must be recalled"
    assert far.memory_id not in ids
