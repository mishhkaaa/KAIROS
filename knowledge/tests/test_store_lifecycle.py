"""An unclosed PgStore must not block event-loop shutdown. Needs Postgres.

psycopg_pool's async workers swallow CancelledError by design, so a pool nobody closes keeps asyncio.run() from
returning. Services don't get a close() call from the kernel, so PgStore has to clean up after itself.
"""

import subprocess
import sys
import textwrap

import pytest
from kairos_contracts.wiring import Settings

from .test_contract import _postgres_reachable

SCRIPT = textwrap.dedent(
    """
    import asyncio, sys
    from kairos_knowledge.indexing.store import PgStore

    async def main():
        stores = [PgStore(sys.argv[1]) for _ in range(3)]
        # concurrent load makes each pool grow, so workers are mid-task when the loop shuts down
        await asyncio.gather(*(s.content_hashes() for s in stores for _ in range(12)))

    asyncio.run(main())
    print("exited")
    """
)


def test_unclosed_store_does_not_block_loop_shutdown():
    s = Settings.from_env(dotenv=None)
    if not _postgres_reachable(s.database_url):
        pytest.skip(f"Postgres unreachable at {s.database_url}")
    try:
        out = subprocess.run([sys.executable, "-c", SCRIPT, s.database_url], capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired:
        pytest.fail("asyncio.run() never returned: an unclosed PgStore pool blocked loop shutdown")
    assert out.returncode == 0, out.stderr[-2000:]
    assert "exited" in out.stdout
