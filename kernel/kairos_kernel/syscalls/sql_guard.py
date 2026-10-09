"""SQL checks for the db tool (contract 0.12.0), run by the kernel before policy and before any statement reaches the
database. No SQL parser is a dependency, so the checks are conservative: anything they cannot read with confidence
(comments, dollar quoting, a second statement) is refused, with a reason the agent can act on.

Owner: P1 — Kernel & Execution

db.query: one SELECT (or WITH ... SELECT), no data-modifying keyword anywhere, no DDL, no SELECT INTO / FOR UPDATE,
          no server functions (pg_*, dblink, lo_*), and a LIMIT of at most MAX_ROWS (added, lowered, or the statement
          is wrapped when its LIMIT cannot be read).
db.write: one INSERT, UPDATE or DELETE (UPDATE and DELETE need a WHERE), no DDL. Policy makes it wait for a person.
The backend adds its own guards: a read-only transaction for queries and a statement timeout.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_ROWS = 200
MAX_CHARS = 4000

# Refused anywhere in the statement. Session and server commands (SET, COPY, DO, CALL, LOCK, ...) are refused by the
# first-word rule: a query must start with SELECT or WITH, a write with INSERT, UPDATE or DELETE (one statement only).
_DDL = ("CREATE", "DROP", "ALTER", "TRUNCATE", "GRANT", "REVOKE", "VACUUM", "REINDEX", "CLUSTER", "ATTACH", "DETACH",
        "PRAGMA")
_WRITES = ("INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "REPLACE")
_FUNCS = re.compile(r"\b(pg_\w+|dblink\w*|lo_\w+|current_setting|set_config|txid_\w+)\s*\(", re.I)
_STRING = re.compile(r"'(?:[^']|'')*'")
_LIMIT_TAIL = re.compile(r"\bLIMIT\s+(\d+)(\s+OFFSET\s+\d+)?\s*$", re.I)


@dataclass(frozen=True)
class SqlCheck:
    ok: bool
    sql: str = ""
    reason: str = ""


def _refuse(reason: str) -> SqlCheck:
    return SqlCheck(False, reason=f"SQL refused by the kernel: {reason}")


def check_sql(operation: str, sql: str) -> SqlCheck:
    """The statement to run (possibly with a LIMIT added), or why it is refused."""
    sql = (sql or "").strip()
    if not sql:
        return _refuse("empty statement")
    if len(sql) > MAX_CHARS:
        return _refuse(f"longer than {MAX_CHARS} characters")
    sql = sql.rstrip().rstrip(";").rstrip()
    if sql.count("'") % 2:
        return _refuse("unbalanced quote")
    bare = _STRING.sub("''", sql)  # keywords inside string literals are data
    if "--" in bare or "/*" in bare or "#" in bare:
        return _refuse("comments are not allowed")
    if "$" in bare or "\\" in bare:
        return _refuse("$ quoting and backslashes are not allowed")
    if ";" in bare:
        return _refuse("exactly one statement is allowed")
    words = [w.upper() for w in re.findall(r"[A-Za-z_]+", bare)]
    if not words:
        return _refuse("no statement")
    if ddl := next((w for w in words if w in _DDL), None):
        return _refuse(f"{ddl} is not allowed (no DDL)")
    if m := _FUNCS.search(bare):
        return _refuse(f"{m.group(1)}() is not allowed")

    if operation == "query":
        if words[0] not in ("SELECT", "WITH"):
            return _refuse("db.query is read-only: the statement must be a SELECT")
        if re.search(r"\bFOR\s+(UPDATE|SHARE|NO\s+KEY|KEY)\b", bare, re.I):
            return _refuse("FOR UPDATE / FOR SHARE is not allowed")
        if w := next((w for w in words if w in _WRITES), None):
            return _refuse(f"db.query is read-only: {w} is not allowed")
        if "INTO" in words:
            return _refuse("SELECT INTO is not allowed")
        return SqlCheck(True, sql=_with_limit(sql, bare))

    if operation == "write":
        if words[0] not in ("INSERT", "UPDATE", "DELETE"):
            return _refuse("db.write takes one INSERT, UPDATE or DELETE")
        if words[0] in ("UPDATE", "DELETE") and "WHERE" not in words:
            return _refuse(f"{words[0]} needs a WHERE clause")
        if "WITH" in words[:1]:
            return _refuse("WITH is not allowed in a write")
        return SqlCheck(True, sql=sql)

    return _refuse(f"unknown db operation {operation!r}")


def _with_limit(sql: str, bare: str) -> str:
    tail = _LIMIT_TAIL.search(bare)
    if tail:
        n = int(tail.group(1))
        if n <= MAX_ROWS:
            return sql
        start = _LIMIT_TAIL.search(sql)
        if start:  # the same tail in the original text (literals cannot contain a trailing LIMIT n)
            return sql[:start.start()].rstrip() + f" LIMIT {MAX_ROWS}" + (start.group(2) or "")
    if not re.search(r"\bLIMIT\b", bare, re.I):
        return f"{sql} LIMIT {MAX_ROWS}"
    return f"SELECT * FROM ({sql}) AS q LIMIT {MAX_ROWS}"  # a LIMIT we cannot read: bound the whole result instead
