"""The kernel's SQL checks for the db tool (contract 0.12.0): conservative, since no SQL parser is a dependency."""
import pytest
from kairos_kernel.syscalls.sql_guard import MAX_ROWS, check_sql

GOOD = "SELECT name FROM vendors WHERE category = 'cloud'"


def test_a_select_gets_a_limit():
    g = check_sql("query", GOOD)
    assert g.ok and g.sql == f"{GOOD} LIMIT {MAX_ROWS}"
    assert check_sql("query", GOOD + " LIMIT 5;").sql == GOOD + " LIMIT 5"
    assert check_sql("query", GOOD + " LIMIT 5000").sql == f"{GOOD} LIMIT {MAX_ROWS}"
    assert check_sql("query", "WITH x AS (SELECT 1 AS a) SELECT a FROM x").ok


def test_a_limit_it_cannot_read_is_wrapped():
    sql = "SELECT * FROM (SELECT name FROM vendors LIMIT 3) v ORDER BY name"
    assert check_sql("query", sql).sql == f"SELECT * FROM ({sql}) AS q LIMIT {MAX_ROWS}"


@pytest.mark.parametrize("sql, why", [
    ("SELECT 1; SELECT 2", "one statement"),
    ("SELECT 1; DROP TABLE vendors", "one statement"),
    ("DROP TABLE vendors", "DROP"),
    ("CREATE TABLE x (a int)", "CREATE"),
    ("ALTER TABLE vendors ADD COLUMN x int", "ALTER"),
    ("TRUNCATE invoices", "TRUNCATE"),
    ("SELECT * INTO copy FROM vendors", "INTO"),
    ("WITH d AS (DELETE FROM invoices RETURNING *) SELECT * FROM d", "DELETE"),
    ("UPDATE invoices SET amount = 0 WHERE invoice_id = 'x'", "read-only"),
    ("SELECT pg_sleep(60)", "pg_sleep"),
    ("SELECT * FROM vendors -- sneaky", "comment"),
    ("SELECT * FROM vendors /* x */", "comment"),
    ("SELECT $$x$$", "$"),
    ("SELECT * FROM vendors FOR UPDATE", "FOR UPDATE"),
    ("", "empty"),
])
def test_queries_that_are_refused(sql, why):
    g = check_sql("query", sql)
    assert not g.ok and why.lower() in g.reason.lower(), g.reason


def test_keywords_inside_strings_are_data():
    assert check_sql("query", "SELECT name FROM vendors WHERE name = 'DROP; TABLE --x'").ok


def test_writes():
    ins = "INSERT INTO finance_notes (note_id, subject) VALUES (?, ?)"
    assert check_sql("write", ins).ok and check_sql("write", ins).sql == ins  # no LIMIT on a write
    assert check_sql("write", "UPDATE finance_notes SET subject = 'x' WHERE note_id = 'N-1'").ok
    for sql, why in [("DELETE FROM finance_notes", "WHERE"), ("UPDATE invoices SET amount = 0", "WHERE"),
                     ("SELECT * FROM vendors", "INSERT, UPDATE or DELETE"), ("DROP TABLE finance_notes", "DROP"),
                     ("INSERT INTO a VALUES (1); DELETE FROM b WHERE 1=1", "one statement")]:
        g = check_sql("write", sql)
        assert not g.ok and why.lower() in g.reason.lower(), (sql, g.reason)
