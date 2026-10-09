"""Contract tests for P2 — run against shared/fixtures/okf. SKIP until implemented."""

import pytest
from kairos_contracts.testing import contracts as c
from kairos_contracts.testing.fakes import FIXTURE_OKF_DIR, FakeModelRouter, InMemoryEventBus
from kairos_contracts.wiring import ServiceBundle, Settings
from kairos_knowledge import factory
from kairos_knowledge.indexing.store import _to_psycopg_dsn


def _postgres_reachable(database_url: str) -> bool:
    """Synchronous, event-loop-agnostic probe: `make()` can be called from inside an already-running
    loop (some contract tests build the service inside their own `async def go()`), so this must not
    touch asyncio at all."""
    import psycopg

    try:
        with psycopg.connect(_to_psycopg_dsn(database_url), connect_timeout=2):
            return True
    except Exception:  # noqa: BLE001 — any connection failure means "unreachable"
        return False


def _build(fn):
    s = Settings.from_env(dotenv=None)
    s.okf_dir = FIXTURE_OKF_DIR
    if not _postgres_reachable(s.database_url):
        pytest.skip(
            f"Postgres unreachable at {s.database_url} — run `docker compose -f infra/compose/docker-compose.yml up -d postgres`"
        )
    b = ServiceBundle(settings=s, models=FakeModelRouter(), event_bus=InMemoryEventBus())
    try:
        b.firewall = factory.build_context_firewall(s, b)
    except NotImplementedError:
        pass
    try:
        return fn(s, b)
    except NotImplementedError as e:
        pytest.skip(f"not implemented yet: {e}")


class TestKnowledge(c.KnowledgeServiceContract):
    def make(self):
        return _build(factory.build_knowledge_service)


class TestFirewall(c.ContextFirewallContract):
    def make(self):
        return _build(factory.build_context_firewall)


class TestMemory(c.MemoryServiceContract):
    def make(self):
        return _build(factory.build_memory_service)
