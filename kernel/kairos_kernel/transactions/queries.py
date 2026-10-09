"""Query tools, seen by the UI: a successful query operation becomes tool.query (what ran, rows, ms) and task.data (the
table), both correlated with the syscall. Only operations listed here are queries; everything else stays tool.*.

Owner: P1 — Kernel & Execution
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kairos_contracts.schema import Cell, SyscallRequest, TaskData, ToolQuery, ToolResult

# (query text, columns, rows) from the request and the tool's output
QueryView = tuple[str, list[str], list[list[Cell]]]

_CELL_CHARS = 200


def _cell(v: Any) -> Cell:
    if v is None or isinstance(v, bool | int | float):
        return v
    return str(v)[:_CELL_CHARS]


def _jira_search(req: SyscallRequest, output: dict[str, Any]) -> QueryView:
    issues = [i for i in output.get("issues", []) if isinstance(i, dict)]
    rows = [[_cell(i.get("key")), _cell(i.get("status")), _cell(i.get("summary"))] for i in issues]
    return f"project={req.arguments.get('project', '')}", ["key", "status", "summary"], rows


def _db_query(req: SyscallRequest, output: dict[str, Any]) -> QueryView:
    rows = [[_cell(v) for v in r] for r in output.get("rows", []) if isinstance(r, list | tuple)]
    return str(req.arguments.get("sql", "")), [str(c) for c in output.get("columns", [])], rows


QUERY_VIEWS: dict[tuple[str, str], Callable[[SyscallRequest, dict[str, Any]], QueryView]] = {
    ("jira", "search_issues"): _jira_search,
    ("db", "query"): _db_query,
}


def query_events(req: SyscallRequest, result: ToolResult, ms: float) -> tuple[ToolQuery, TaskData] | None:
    """The tool.query and task.data payloads for a successful query operation; None for anything else."""
    view = QUERY_VIEWS.get((req.tool, req.operation))
    if view is None or not isinstance(result.output, dict):
        return None
    query, columns, rows = view(req, result.output)
    name = f"{req.tool}.{req.operation}"
    return (ToolQuery(pid=req.pid, tool=name, query=query[:4000], rows=len(rows), ms=max(0, round(ms))),
            TaskData.capped(columns, rows, name))
