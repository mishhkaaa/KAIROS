"""T7: the ingest pipeline over a scratch copy of the fixture bundle (shared/fixtures/okf is frozen). Needs Postgres."""

import asyncio
import shutil
from pathlib import Path

import pytest
from kairos_contracts.schema import IngestRequest, IngestSourceType, SearchQuery
from kairos_contracts.testing.fakes import (
    FIXTURE_OKF_DIR,
    FakeMarkdownConverter,
    FakeModelRouter,
    InMemoryEventBus,
    user_principal,
)
from kairos_contracts.wiring import Settings
from kairos_knowledge.firewall import ContextFirewall
from kairos_knowledge.indexing.store import PgStore
from kairos_knowledge.kfs import KnowledgeFS

from .test_contract import _postgres_reachable

SAMPLES = Path(__file__).parent / "samples" / "markdown"


@pytest.fixture
def bundle_dir(tmp_path):
    s = Settings.from_env(dotenv=None)
    if not _postgres_reachable(s.database_url):
        pytest.skip(f"Postgres unreachable at {s.database_url}")
    dst = tmp_path / "okf"
    shutil.copytree(FIXTURE_OKF_DIR, dst)
    return dst


def _fs(okf_dir: Path, bus: InMemoryEventBus, converters=None) -> KnowledgeFS:
    s = Settings.from_env(dotenv=None)
    models = FakeModelRouter()
    conv = [FakeMarkdownConverter()] if converters is None else converters
    return KnowledgeFS(okf_dir, PgStore(s.database_url), models, ContextFirewall(models=models), bus, conv)


def _collect(bus: InMemoryEventBus, pattern: str) -> list:
    got: list = []

    async def h(e):
        got.append(e)

    bus.subscribe(pattern, h)
    return got


def test_ingest_creates_files_index_rows_and_events(bundle_dir):
    async def go():
        bus = InMemoryEventBus()
        changed = _collect(bus, "knowledge.changed")
        fs = _fs(bundle_dir, bus)
        req = IngestRequest(source_type=IngestSourceType.DIRECTORY, uri=str(SAMPLES), target_path="/org/inbox")
        result = await fs.ingest(req)
        await asyncio.sleep(0.05)
        hits = await fs.search(SearchQuery(text="emergency support contract procurement"), user_principal())
        obj = await fs.read("/org/inbox/vendor-contract", user_principal())
        again = await fs.ingest(req)
        await asyncio.sleep(0.05)
        return result, changed, hits, obj, again

    result, changed, hits, obj, again = asyncio.run(go())
    assert result.created == ["/org/inbox/vendor-contract"] and not result.errors
    assert (bundle_dir / "inbox" / "vendor-contract.md").exists()
    assert obj.frontmatter.title == "Vendor Contract"  # FakeMarkdownConverter titles files from their name
    assert "/org/inbox/vendor-contract" in [h.path for h in hits.hits]
    assert [(e.payload["path"], e.payload["change"]) for e in changed] == [("/org/inbox/vendor-contract", "created")]
    assert again.skipped and not again.created and not again.updated, "re-ingesting identical content is a no-op"
    assert len(changed) == 1, "no knowledge.changed for an unchanged file"


def test_ingest_without_matching_converter_reports_error(bundle_dir):
    async def go():
        fs = _fs(bundle_dir, InMemoryEventBus(), converters=[])
        return await fs.ingest(IngestRequest(source_type=IngestSourceType.URL, uri="https://example.com/x"))

    result = asyncio.run(go())
    assert result.errors and not result.created


def test_reindex_drops_deleted_files(bundle_dir):
    async def go():
        bus = InMemoryEventBus()
        reindexed = _collect(bus, "knowledge.reindexed")
        fs = _fs(bundle_dir, bus)
        await fs.read("/org/projects/zeus", user_principal())
        (bundle_dir / "projects" / "zeus.md").unlink()
        count = await fs.reindex(["/org/projects/zeus"])
        await asyncio.sleep(0.05)
        row = await fs.store.get_object_row("/org/projects/zeus")
        return count, row, reindexed

    count, row, reindexed = asyncio.run(go())
    assert count == 0 and row is None
    assert reindexed and reindexed[0].payload == {"count": 0}
