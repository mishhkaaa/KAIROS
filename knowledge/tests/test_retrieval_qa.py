"""T10: retrieval QA over P4's demo bundle (data/okf) with P4's questions (data/qa.yaml). Needs Postgres.

Format (P4): questions: [{q: str, expected: [path, ...]}]; a question passes when expected[0] is in the top 3.
Skips on branches without P4's data, so it stays green everywhere else.
"""

import asyncio
from pathlib import Path

import pytest
import yaml
from kairos_contracts.schema import SearchQuery
from kairos_contracts.testing.fakes import FakeModelRouter, user_principal
from kairos_contracts.wiring import REPO_ROOT, Settings
from kairos_knowledge.firewall import ContextFirewall
from kairos_knowledge.indexing.store import PgStore
from kairos_knowledge.kfs import KnowledgeFS

from .test_contract import _postgres_reachable

OKF = REPO_ROOT / "data" / "okf"
QA = REPO_ROOT / "data" / "qa.yaml"
TARGET = 9


def load_questions(path: Path) -> list[tuple[str, list[str]]]:
    """Tolerant: accepts {questions: [...]} or a bare list, `q`/`question`, and `expected` as a list or a string."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = raw.get("questions", []) if isinstance(raw, dict) else raw or []
    out = []
    for item in items:
        q = item.get("q") or item.get("question")
        expected = item.get("expected") or item.get("expected_top3") or []
        expected = [expected] if isinstance(expected, str) else list(expected)
        if q and expected:
            out.append((q, [e.rstrip("/") for e in expected]))
    return out


def test_retrieval_qa_on_demo_bundle():
    if not QA.exists() or not OKF.exists() or sum(1 for _ in OKF.rglob("*.md")) < 30:
        pytest.skip("P4's demo bundle (data/okf, data/qa.yaml) isn't on this branch")
    s = Settings.from_env()  # .env points tests at the test server
    if not _postgres_reachable(s.database_url):
        pytest.skip(f"Postgres unreachable at {s.database_url}")
    questions = load_questions(QA)
    assert len(questions) >= 10, f"expected 10 questions in {QA}, parsed {len(questions)}"

    async def go():
        models = FakeModelRouter()
        fs = KnowledgeFS(OKF, PgStore(s.database_url), models, ContextFirewall(models=models))
        try:
            return [(q, exp, await fs.search(SearchQuery(text=q, top_k=10), user_principal())) for q, exp in questions]
        finally:
            await fs.aclose()

    passed, lines = 0, []
    for q, expected, ev in asyncio.run(go()):
        ranked = [h.path for h in ev.hits]
        rank = ranked.index(expected[0]) + 1 if expected[0] in ranked else None
        ok = rank is not None and rank <= 3
        passed += ok
        lines.append(f"{'PASS' if ok else 'MISS'} rank={rank or '>10'} q={q!r}\n     expected={expected[0]} top3={ranked[:3]}")
    report = f"retrieval QA: {passed}/{len(questions)} (target {TARGET})\n" + "\n".join(lines)
    print(report)
    assert passed >= TARGET, report
