"""Retrieval QA over data/okf with the REAL embedding model (nomic-embed-text via Ollama), hybrid and semantic-only.

test_retrieval_qa.py uses fake hash embeddings, so it can't tell whether the embedding side works; this one can.
It indexes into its own database (kairos_qa) and skips without Postgres or Ollama. Semantic-only is the sensitive
number: lexical search alone already answers most of these questions.
"""

import asyncio

import pytest
from kairos_contracts.schema import SearchMode, SearchQuery
from kairos_contracts.testing.fakes import user_principal
from kairos_contracts.wiring import ServiceBundle, Settings
from kairos_knowledge.firewall import ContextFirewall
from kairos_knowledge.indexing.store import PgStore
from kairos_knowledge.kfs import KnowledgeFS

from .test_contract import _postgres_reachable
from .test_recall_real_embeddings import _ensure_database, _ollama_ready
from .test_retrieval_qa import OKF, QA, load_questions

HYBRID_TARGET = 9      # of 10, expected[0] in the top 3
SEMANTIC_TARGET = 9    # of 10, embeddings alone (10/10, MRR 0.90 with the nomic task prefixes; MRR 0.83 without)


def run_qa(modes: list[SearchMode]) -> tuple[int, float, list[str]]:
    s = Settings.from_env()
    if not QA.exists() or not _postgres_reachable(s.database_url) or not _ollama_ready(s.ollama_url):
        pytest.skip("needs data/okf, Postgres and Ollama with nomic-embed-text")
    from kairos_models.factory import build_model_router

    _ensure_database(s.database_url, "kairos_qa")
    db = s.database_url.rsplit("/", 1)[0] + "/kairos_qa"
    questions = load_questions(QA)

    async def go():
        models = build_model_router(s, ServiceBundle(settings=s))
        fs = KnowledgeFS(OKF, PgStore(db), models, ContextFirewall(models=None))
        try:
            return [(q, exp, await fs.search(SearchQuery(text=q, top_k=10, modes=modes), user_principal())) for q, exp in questions]
        finally:
            await fs.aclose()

    passed, rr, lines = 0, 0.0, []
    for q, expected, ev in asyncio.run(go()):
        ranked = [h.path for h in ev.hits]
        rank = ranked.index(expected[0]) + 1 if expected[0] in ranked else None
        passed += bool(rank and rank <= 3)
        rr += 1 / rank if rank else 0.0
        lines.append(f"{'PASS' if rank and rank <= 3 else 'MISS'} rank={rank or '>10'} {q!r} -> {expected[0]}")
    return passed, rr / len(questions), lines


def test_hybrid_retrieval_with_real_embeddings():
    passed, mrr, lines = run_qa([SearchMode.LEXICAL, SearchMode.SEMANTIC, SearchMode.GRAPH])
    print(f"hybrid: {passed}/10 top-3, MRR {mrr:.2f}", *lines, sep="\n")
    assert passed >= HYBRID_TARGET


def test_semantic_retrieval_with_real_embeddings():
    passed, mrr, lines = run_qa([SearchMode.SEMANTIC])
    print(f"semantic only: {passed}/10 top-3, MRR {mrr:.2f}", *lines, sep="\n")
    assert passed >= SEMANTIC_TARGET
