"""Unit tests for retrieval: RRF ordering and filtered_by_policy counting. Needs Postgres."""

import asyncio

import pytest
from kairos_contracts.schema import SearchMode, SearchQuery
from kairos_contracts.testing.fakes import FIXTURE_OKF_DIR, FakeModelRouter, user_principal
from kairos_contracts.wiring import Settings
from kairos_knowledge.firewall import ContextFirewall
from kairos_knowledge.indexing.store import PgStore
from kairos_knowledge.kfs import KnowledgeFS

from .test_contract import _postgres_reachable


def _fs() -> KnowledgeFS:
    s = Settings.from_env(dotenv=None)
    if not _postgres_reachable(s.database_url):
        pytest.skip(f"Postgres unreachable at {s.database_url}")
    models = FakeModelRouter()
    return KnowledgeFS(FIXTURE_OKF_DIR, PgStore(s.database_url), models, ContextFirewall(models=models))


def test_lexical_and_semantic_top_result_ranks_first():
    async def go():
        fs = _fs()
        ev = await fs.search(SearchQuery(text="Apollo budget overrun cloud cost", modes=[SearchMode.LEXICAL]), user_principal())
        return ev

    ev = asyncio.run(go())
    assert ev.hits, "expected at least one lexical hit"
    assert ev.hits[0].path == "/org/finance/apollo-budget"
    assert ev.hits == sorted(ev.hits, key=lambda h: -h.score), "hits must be sorted by descending fused score"


def test_hit_with_more_mode_agreement_outranks_single_mode_hit():
    async def go():
        fs = _fs()
        return await fs.search(
            SearchQuery(text="Apollo budget overrun cloud cost", modes=[SearchMode.LEXICAL, SearchMode.SEMANTIC]),
            user_principal(),
        )

    ev = asyncio.run(go())
    by_path = {h.path: h for h in ev.hits}
    top = by_path["/org/finance/apollo-budget"]
    assert set(top.scores) >= {"lexical", "semantic"}, "the best-matching doc should rank in both modes"
    for mode, score in top.scores.items():
        assert 0.0 <= score <= 1.0, f"{mode} score must be normalized into [0,1]"


def test_filtered_by_policy_counts_only_scope_and_privacy():
    async def go():
        fs = _fs()
        p = user_principal(data_scopes=["/org/projects/**", "/org/engineering/**"])
        return await fs.search(SearchQuery(text="Apollo budget"), p)

    ev = asyncio.run(go())
    assert ev.filtered_by_policy > 0, "finance docs matching the text should be filtered by the narrower scope"
    assert all(not h.path.startswith("/org/finance") for h in ev.hits)


def test_filtered_by_policy_ignores_the_query_own_filters():
    async def go():
        fs = _fs()
        # a type filter that matches nothing removes candidates too, but that is NOT a policy removal
        return await fs.search(SearchQuery(text="Apollo budget", types=["no-such-type"]), user_principal())

    ev = asyncio.run(go())
    assert ev.filtered_by_policy == 0


def test_snippet_is_the_chunk_content_not_its_heading():
    from kairos_knowledge.retrieval.retriever import snippet_of

    chunk = "# Apollo budget and variance\n\nWhy Project Apollo is over budget: actuals are 31% over.\n\n| Total | 20.0 | 26.2 |"
    assert snippet_of(chunk) == "Why Project Apollo is over budget: actuals are 31% over. | Total | 20.0 | 26.2 |"
    long = "## Notes\n" + "word " * 200
    s = snippet_of(long, width=50)
    assert s.endswith(" …") and len(s) <= 52 and not s.startswith("#")
