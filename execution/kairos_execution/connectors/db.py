"""The db tool (contract 0.12.0): the demo company database (Settings.demo_data_url, `kairos_demo_data`).

Owner: P1 — Kernel & Execution

The kernel has already checked the statement (kernel/kairos_kernel/syscalls/sql_guard.py) and, for db.write, a person
has approved it. This backend adds its own guards: every query runs in a READ ONLY transaction with a statement
timeout, results are cut at MAX_ROWS, and a write runs in its own transaction with the same timeout. `?` placeholders
(what agents write, and what SQLite in fake mode takes) become psycopg's `%s`.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import decimal
import logging
import re
from typing import Any

from kairos_contracts.schema import ToolInvocation, ToolOperation, ToolResult, ToolSpec, ToolTransport, VerificationResult
from kairos_contracts.schema.common import Risk
from kairos_contracts.testing import demo_data

from ..tools.base import err, ok, require, status_check

log = logging.getLogger("kairos.execution.db")

MAX_ROWS = 200
STATEMENT_TIMEOUT_MS = 5000

SPEC = ToolSpec(name="db", description="Demo company database (read-only queries; writes need approval)",
                transport=ToolTransport.NATIVE, operations=[
    ToolOperation(name="schema", capability="db.query", description="Tables, columns and notes of the database",
                  input_schema={"type": "object", "properties": {}}),
    ToolOperation(name="query", capability="db.query", description="Run one read-only SELECT (LIMIT <= 200)",
                  input_schema={"type": "object", "required": ["sql"], "properties": {"sql": {"type": "string"}}}),
    ToolOperation(name="write", capability="db.write", description="Run one INSERT/UPDATE/DELETE with parameters",
                  input_schema={"type": "object", "required": ["sql"], "properties": {
                      "sql": {"type": "string"}, "params": {"type": "array"}}}, risk=Risk.HIGH),
])


def _plain(v: Any) -> Any:
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, dt.date | dt.datetime):
        return v.isoformat()
    return v


def _psycopg_params(sql: str) -> str:
    """`?` placeholders outside string literals -> `%s` (and a literal % -> %%, since psycopg formats the string)."""
    parts = re.split(r"('(?:[^']|'')*')", sql)
    return "".join(p if i % 2 else p.replace("%", "%%").replace("?", "%s") for i, p in enumerate(parts))


class DbBackend:
    name = "db"

    def __init__(self, url: str) -> None:
        self.url = url.replace("postgresql+psycopg://", "postgresql://", 1)

    def spec(self) -> ToolSpec:
        return SPEC

    def _connect(self):
        # Sync psycopg in a worker thread: its async mode needs a selector event loop, and on Windows kairosd runs on
        # the proactor loop.
        import psycopg

        return psycopg.connect(self.url, connect_timeout=5)

    async def execute(self, inv: ToolInvocation) -> ToolResult:
        a = inv.arguments
        try:
            if inv.operation == "schema":
                return ok(inv, demo_data.schema_doc())
            if inv.operation == "query":
                require(a, "sql")
                return ok(inv, await self._query(str(a["sql"])))
            if inv.operation == "write":
                require(a, "sql")
                return ok(inv, await self._write(str(a["sql"]), list(a.get("params") or [])))
            return err(inv, "NOT_FOUND", f"unknown db operation {inv.operation}")
        except Exception as e:  # executors report errors, never raise
            name = type(e).__name__
            if name in ("QueryCanceled", "LockNotAvailable"):
                return err(inv, "TIMEOUT", f"the statement ran longer than {STATEMENT_TIMEOUT_MS} ms")
            if name in ("OperationalError", "ConnectionTimeout"):
                return err(inv, "TOOL_FAILED", f"cannot reach the demo database: {e}", retriable=True)
            if getattr(e, "code", None) and hasattr(e, "to_info"):
                return err(inv, e.code, e.message)
            return err(inv, "BAD_REQUEST", f"SQL error: {str(e).strip()[:400]}")

    async def _query(self, sql: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._query_sync, sql)

    async def _write(self, sql: str, params: list[Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self._write_sync, sql, params)

    def _query_sync(self, sql: str) -> dict[str, Any]:
        with self._connect() as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
                cur.execute(_psycopg_params(sql))
                columns = [d.name for d in cur.description or []]
                rows = [[_plain(v) for v in r] for r in cur.fetchmany(MAX_ROWS)]
            conn.rollback()  # nothing to keep: the transaction was read-only anyway
        return {"columns": columns, "rows": rows}

    def _write_sync(self, sql: str, params: list[Any]) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
                cur.execute(_psycopg_params(sql), params or None)
                rowcount = cur.rowcount
            conn.commit()
        return {"rowcount": rowcount}

    async def verify(self, inv: ToolInvocation, result: ToolResult) -> VerificationResult:
        return status_check(inv, result)

    async def rollback(self, inv: ToolInvocation, result: ToolResult) -> bool:
        return False  # a committed write has no generic undo; approval is the guard
