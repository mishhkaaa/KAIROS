"""T8: editing an OKF file → knowledge.changed → memory.invalidated (+ reindex). Needs Postgres."""

import asyncio
import shutil
from uuid import uuid4

import pytest
from kairos_contracts.schema import MemoryKind, MemoryRecord, MemoryScope, SearchQuery
from kairos_contracts.schema.common import new_id
from kairos_contracts.testing.fakes import FIXTURE_OKF_DIR, FakeModelRouter, InMemoryEventBus, user_principal
from kairos_contracts.wiring import ServiceBundle, Settings
from kairos_knowledge import factory
from kairos_knowledge.coherence import watch_bundle

from .test_contract import _postgres_reachable


@pytest.fixture
def services(tmp_path):
    s = Settings.from_env(dotenv=None)
    if not _postgres_reachable(s.database_url):
        pytest.skip(f"Postgres unreachable at {s.database_url}")
    s.okf_dir = tmp_path / "okf"
    shutil.copytree(FIXTURE_OKF_DIR, s.okf_dir)
    b = ServiceBundle(settings=s, models=FakeModelRouter(), event_bus=InMemoryEventBus())
    b.firewall = factory.build_context_firewall(s, b)
    b.knowledge = factory.build_knowledge_service(s, b)
    b.memory = factory.build_memory_service(s, b)  # also starts coherence
    return s, b


async def _wait_for(events: list, pred, timeout: float = 10.0):
    async def poll():
        while not any(pred(e) for e in events):
            await asyncio.sleep(0.05)

    await asyncio.wait_for(poll(), timeout)
    return next(e for e in events if pred(e))


def test_manual_edit_invalidates_dependent_memories_and_reindexes(services):
    s, b = services
    # A document of this run's own: memories persist in the test database, and each run leaves a re-derived memory
    # resting on the document it edited, so with a fixed path (policies/security) every later run invalidated one more.
    name = f"key-rotation-{uuid4().hex[:8]}"
    doc_path = f"/org/policies/{name}"
    security = s.okf_dir / "policies" / f"{name}.md"
    security.write_text("---\ntype: policy\ntitle: Key rotation\ndescription: How often keys rotate\ntrust: verified\n---\n\n"
                        "# Key rotation\n\nQuasarcrypt keys rotate every 90 days.\n", encoding="utf-8")

    async def go():
        seen: list = []

        async def h(e):
            seen.append(e)

        b.event_bus.subscribe("*", h)
        b.models.responses["rests on documents that have since changed"] = "Quasarcrypt keys now rotate every 30 days."
        await b.knowledge.read(doc_path, user_principal())  # load + index the scratch bundle
        summary = MemoryRecord(
            memory_id=new_id("MEM"),
            kind=MemoryKind.SEMANTIC,
            scope=MemoryScope.AGENT,
            org_id="acme",
            owner="finance-agent",
            content="security policy summary",
            derived_from=[doc_path],
        )
        derived = summary.model_copy(
            update={"memory_id": new_id("MEM"), "owner": "compliance-agent", "derived_from": [summary.memory_id]}
        )
        await b.memory.store(summary)
        await b.memory.store(derived)

        stop = asyncio.Event()
        watcher = asyncio.create_task(watch_bundle(s.okf_dir, b.event_bus, stop, debounce_ms=100))
        await asyncio.sleep(0.5)  # let the watcher arm before editing
        security.write_text(
            security.read_text(encoding="utf-8") + "\n## v2\n\nQuasarcrypt keys rotate every 30 days.\n", encoding="utf-8"
        )

        changed = await _wait_for(seen, lambda e: e.type == "knowledge.changed" and e.payload["path"] == doc_path)
        invalidated = await _wait_for(
            seen, lambda e: e.type == "memory.invalidated" and e.payload["source"] == doc_path
        )
        await _wait_for(seen, lambda e: e.type == "knowledge.reindexed")
        hits = await b.knowledge.search(SearchQuery(text="Quasarcrypt keys rotate"), user_principal())
        await _wait_for(seen, lambda e: e.type == "memory.consolidated" and e.source == "memory.reconsolidate")
        async with b.memory.pg.connection() as conn:
            cur = await conn.execute("SELECT * FROM memories WHERE %s = ANY(tags)", (f"replaces:{summary.memory_id}",))
            redone = await cur.fetchall()
            cur = await conn.execute("SELECT count(*) AS n FROM memories WHERE %s = ANY(tags)", (f"replaces:{derived.memory_id}",))
            redone_derived = (await cur.fetchone())["n"]
        stop.set()
        await watcher
        return summary, derived, changed, invalidated, hits, redone, redone_derived

    summary, derived, changed, invalidated, hits, redone, redone_derived = asyncio.run(go())
    assert changed.payload["change"] == "updated"
    assert set(invalidated.payload["invalidated"]) == {summary.memory_id, derived.memory_id}
    assert invalidated.payload["affected_agents"] == ["compliance-agent", "finance-agent"]
    assert hits.hits and hits.hits[0].path == doc_path, "the edit is searchable after coherence reindexed it"
    # re-consolidation: the memory resting on the edited document is re-derived from its new text
    assert invalidated.payload["reconsolidation_queued"] is True
    [new] = redone
    assert new["content"] == "Quasarcrypt keys now rotate every 30 days." and not new["stale"]
    assert new["owner"] == "finance-agent" and new["derived_from"] == [doc_path] and "reconsolidated" in new["tags"]
    assert redone_derived == 0, "a memory derived only from other memories has no document to re-derive from"


def test_knowledge_watch_setting_starts_the_watcher(tmp_path):
    base = Settings.from_env(dotenv=None)
    if not _postgres_reachable(base.database_url):
        pytest.skip(f"Postgres unreachable at {base.database_url}")

    class WatchSettings(Settings):  # stands in for Settings once the knowledge_watch contract lands
        knowledge_watch: bool = True

    s = WatchSettings(database_url=base.database_url, okf_dir=tmp_path / "okf")
    shutil.copytree(FIXTURE_OKF_DIR, s.okf_dir)
    b = ServiceBundle(settings=s, models=FakeModelRouter(), event_bus=InMemoryEventBus())
    b.firewall = factory.build_context_firewall(s, b)
    knowledge = factory.build_knowledge_service(s, b)

    async def go():
        seen: list = []

        async def h(e):
            seen.append(e)

        b.event_bus.subscribe("knowledge.changed", h)
        await knowledge.read("/org/projects/zeus", user_principal())  # first call starts the watcher
        await asyncio.sleep(0.8)
        (s.okf_dir / "projects" / "zeus.md").write_text("---\ntype: project\ntitle: Zeus\n---\nPaused.\n", encoding="utf-8")
        try:
            return await _wait_for(seen, lambda e: e.payload["path"] == "/org/projects/zeus")
        finally:
            await knowledge.aclose()

    assert asyncio.run(go()).payload["change"] == "updated"


def test_watcher_is_off_by_default(services):
    s, b = services
    assert getattr(s, "knowledge_watch", False) is False
    assert b.knowledge.watch is False
