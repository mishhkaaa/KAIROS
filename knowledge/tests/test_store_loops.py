"""PgStore must work on any asyncio event loop: on Windows, kairosd's loop is uvicorn's ProactorEventLoop, which
Playwright and asyncio subprocesses (P4's GPU probe) need. Needs Postgres."""

import asyncio
import sys

import pytest
from kairos_contracts.wiring import Settings
from kairos_knowledge.indexing.store import PgStore

from .test_contract import _postgres_reachable

LOOPS = [asyncio.SelectorEventLoop] + ([asyncio.ProactorEventLoop] if sys.platform == "win32" else [])


@pytest.mark.parametrize("loop_factory", LOOPS, ids=lambda f: f.__name__)
def test_store_round_trip_on_every_loop(loop_factory):
    url = Settings.from_env(dotenv=None).database_url
    if not _postgres_reachable(url):
        pytest.skip(f"Postgres unreachable at {url}")

    async def go():
        store = PgStore(url)
        try:
            async with store.connection() as conn:
                cur = await conn.execute("SELECT %s::int + 1 AS n", (41,))
                row = await cur.fetchone()
            return row["n"], await store.ping()
        finally:
            await store.close()

    assert asyncio.run(go(), loop_factory=loop_factory) == (42, True)
