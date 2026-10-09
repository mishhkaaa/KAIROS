"""Contract 0.12.0 (db tool): the demo dataset, the db tool spec and the fake db backend."""
import asyncio

from kairos_contracts.schema import ToolInvocation
from kairos_contracts.testing import demo_data
from kairos_contracts.testing.fakes import FAKE_TOOL_SPECS, FakeToolExecutor
from kairos_contracts.util import APPROVAL_REQUIRED
from kairos_contracts.wiring import Settings

OVERPAID = """SELECT v.name, SUM(i.amount) - c.contract_value AS overpaid
FROM vendors v JOIN contracts c ON c.vendor_id = v.vendor_id AND c.quarter = '2026-Q3'
JOIN invoices i ON i.vendor_id = v.vendor_id AND i.status = 'paid' AND i.invoice_date BETWEEN '2026-07-01' AND '2026-09-30'
GROUP BY v.name, c.contract_value HAVING SUM(i.amount) > c.contract_value LIMIT 200"""


def _run(ex, op, **args):
    tool, operation = op.split(".")
    return asyncio.run(ex.execute(ToolInvocation(invocation_id="INV-1", syscall_id="SC-1", task_id="T-1", pid=101,
                                                 tool=tool, operation=operation, arguments=args)))


def test_the_db_tool_spec():
    db = next(s for s in FAKE_TOOL_SPECS if s.name == "db")
    assert {o.name: o.capability for o in db.operations} == {"schema": "db.query", "query": "db.query", "write": "db.write"}
    assert "db.write" in APPROVAL_REQUIRED and "db.query" not in APPROVAL_REQUIRED
    assert Settings().demo_data_url.endswith("/kairos_demo_data")


def test_the_fake_db_answers_the_vendors_question_from_the_seed():
    ex = FakeToolExecutor()
    r = _run(ex, "db.query", sql=OVERPAID)
    assert r.output["columns"] == ["name", "overpaid"]
    assert {n: round(v, 2) for n, v in r.output["rows"]} == demo_data.EXPECTED_Q3_OVERPAID
    assert {t["name"] for t in _run(ex, "db.schema").output["tables"]} == set(demo_data.TABLES)


def test_the_fake_db_writes_notes_and_reports_bad_sql():
    ex = FakeToolExecutor()
    w = _run(ex, "db.write", sql="INSERT INTO finance_notes VALUES (?, ?, ?, ?, ?)",
             params=["NOTE-1", "2026-10-01T00:00:00Z", "writer", "Q3 overpayments", "body"])
    assert w.output == {"rowcount": 1}
    assert _run(ex, "db.query", sql="SELECT subject FROM finance_notes").output["rows"] == [["Q3 overpayments"]]
    bad = _run(ex, "db.query", sql="SELEKT nonsense")
    assert bad.status.value == "error" and bad.error.code == "BAD_REQUEST"
