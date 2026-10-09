"""The db backend against the seeded kairos_demo_data (scripts/seed_demo_data.py). Skips when it isn't reachable.
The URL: KAIROS_DEMO_DATA_URL, else KAIROS_DATABASE_URL's server with the database swapped."""
import asyncio
import os
import sys
from pathlib import Path

import pytest
from kairos_contracts.schema import ToolInvocation
from kairos_contracts.testing.demo_data import EXPECTED_Q3_OVERPAID
from kairos_execution.connectors.db import DbBackend

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from seed_demo_data import target_url  # noqa: E402

OVERPAID = ("SELECT v.name, SUM(i.amount) - c.contract_value AS overpaid FROM vendors v "
            "JOIN contracts c ON c.vendor_id = v.vendor_id AND c.quarter = '2026-Q3' "
            "JOIN invoices i ON i.vendor_id = v.vendor_id AND i.status = 'paid' "
            "AND i.invoice_date BETWEEN '2026-07-01' AND '2026-09-30' "
            "GROUP BY v.name, c.contract_value HAVING SUM(i.amount) > c.contract_value LIMIT 200")


@pytest.fixture(scope="module")
def db():
    backend = DbBackend(target_url(os.getenv("KAIROS_TEST_DEMO_DATA_URL")))
    try:
        asyncio.run(backend._query("SELECT 1 FROM vendors LIMIT 1"))
    except Exception as e:
        pytest.skip(f"kairos_demo_data not reachable or not seeded: {type(e).__name__}")
    return backend


def _run(db, op, **args):
    return asyncio.run(db.execute(ToolInvocation(invocation_id="INV-1", syscall_id="SC-1", task_id="T-1", pid=101,
                                                 tool="db", operation=op, arguments=args)))


def test_the_vendors_question_on_postgres(db):
    r = _run(db, "query", sql=OVERPAID)
    assert r.status.value == "success" and r.output["columns"] == ["name", "overpaid"]
    assert {n: round(v, 2) for n, v in r.output["rows"]} == EXPECTED_Q3_OVERPAID


def test_queries_are_read_only_even_past_the_kernel(db):
    r = _run(db, "query", sql="DELETE FROM finance_notes WHERE note_id = 'nope'")
    assert r.status.value == "error" and "read-only" in r.error.message


def test_a_long_statement_times_out_clearly(db):
    r = _run(db, "query", sql="SELECT pg_sleep(7)")
    assert r.status.value == "error" and r.error.code == "TIMEOUT"


def test_a_write_with_placeholders(db):
    r = _run(db, "write", sql="INSERT INTO finance_notes VALUES (?, ?, ?, ?, ?)",
             params=["NOTE-live-test", "2026-10-01T00:00:00Z", "test", "live 100% test", "body"])
    assert r.status.value == "success" and r.output == {"rowcount": 1}
    _run(db, "write", sql="DELETE FROM finance_notes WHERE note_id = ?", params=["NOTE-live-test"])
