"""`jira` tool backend over the (mock) Jira REST API. Reversible updates: rollback restores fields and removes comments.

jira_url is operator-configured (Settings.jira_url), so it is a trusted endpoint; network_allow constrains
agent-chosen destinations (browser/sandbox), not connectors. jira_url="inprocess" runs the mock in-process.
"""
from __future__ import annotations

from typing import Any

import httpx
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    Risk,
    ToolInvocation,
    ToolOperation,
    ToolResult,
    ToolResultStatus,
    ToolSpec,
    ToolTransport,
    VerificationCheck,
    VerificationResult,
)

from ..tools.base import err, ok, require, status_check, token

SPEC = ToolSpec(name="jira", description="Issue tracker (Jira REST v2; mock-jira in the demo)", transport=ToolTransport.HTTP,
                operations=[
    ToolOperation(name="get_issue", capability="jira.read", description="Read an issue by key",
                  input_schema={"type": "object", "required": ["key"], "properties": {"key": {"type": "string"}}}),
    ToolOperation(name="search_issues", capability="jira.read", description="List issues of a project",
                  input_schema={"type": "object", "properties": {"project": {"type": "string"}}}),
    ToolOperation(name="update_issue", capability="jira.write", description="Update fields and/or add a comment",
                  input_schema={"type": "object", "required": ["key"], "properties": {
                      "key": {"type": "string"}, "fields": {"type": "object"}, "comment": {"type": "string"}}},
                  risk=Risk.MEDIUM, reversible=True),
])


def flatten(issue: dict[str, Any]) -> dict[str, Any]:
    f = issue.get("fields", {})
    comments = f.get("comment", {}).get("comments", [])
    return {"key": issue["key"], "summary": f.get("summary"), "status": (f.get("status") or {}).get("name"),
            "labels": f.get("labels", []), "assignee": (f.get("assignee") or {}).get("displayName"),
            "duedate": f.get("duedate"), "description": f.get("description"),
            "comments": [c.get("body") for c in comments]}


def to_jira_fields(fields: dict[str, Any]) -> dict[str, Any]:
    out = dict(fields)
    if "status" in out and isinstance(out["status"], str):
        out["status"] = {"name": out["status"]}
    if "assignee" in out and isinstance(out["assignee"], str):
        out["assignee"] = {"displayName": out["assignee"]}
    return out


class JiraBackend:
    name = "jira"

    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        if base_url == "inprocess":
            from .jira_mock import create_app

            transport, base_url = httpx.ASGITransport(app=create_app()), "http://mock-jira"
        self.client = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=10)
        self._undo: dict[str, dict[str, Any]] = {}

    def spec(self) -> ToolSpec:
        return SPEC

    async def _get(self, key: str) -> dict[str, Any]:
        try:
            r = await self.client.get(f"/rest/api/2/issue/{key}")
        except httpx.HTTPError as e:
            raise KairosError("TOOL_FAILED", f"jira unreachable: {e}") from e
        if r.status_code == 404:
            raise KairosError("NOT_FOUND", f"issue {key}")
        r.raise_for_status()
        return r.json()

    async def execute(self, inv: ToolInvocation) -> ToolResult:
        a = inv.arguments
        try:
            if inv.operation == "get_issue":
                require(a, "key")
                return ok(inv, flatten(await self._get(a["key"])))
            if inv.operation == "search_issues":
                r = await self.client.get("/rest/api/2/search", params={"jql": f"project={a.get('project', '')}"})
                r.raise_for_status()
                return ok(inv, {"issues": [flatten(i) for i in r.json()["issues"]]})
            if inv.operation == "update_issue":
                return await self._update(inv)
            return err(inv, "NOT_FOUND", f"unknown jira operation {inv.operation}")
        except KairosError as e:
            return err(inv, e.code, e.message)
        except httpx.HTTPError as e:
            return err(inv, "TOOL_FAILED", f"jira request failed: {e}")

    async def _update(self, inv: ToolInvocation) -> ToolResult:
        a = inv.arguments
        require(a, "key")
        key, fields = a["key"], a.get("fields") or {}
        before = await self._get(key)
        undo: dict[str, Any] = {"key": key, "fields": {k: before["fields"].get(k) for k in to_jira_fields(fields)},
                                "comment_id": None}
        if fields:
            r = await self.client.put(f"/rest/api/2/issue/{key}", json={"fields": to_jira_fields(fields)})
            r.raise_for_status()
        if a.get("comment"):
            r = await self.client.post(f"/rest/api/2/issue/{key}/comment", json={"body": a["comment"]})
            r.raise_for_status()
            undo["comment_id"] = r.json()["id"]
        rb = token()
        self._undo[rb] = undo
        return ok(inv, flatten(await self._get(key)), rollback_token=rb)

    async def verify(self, inv: ToolInvocation, result: ToolResult) -> VerificationResult:
        if result.status != ToolResultStatus.SUCCESS or inv.operation != "update_issue":
            return status_check(inv, result)
        try:
            now = flatten(await self._get(inv.arguments["key"]))
        except KairosError as e:
            return status_check(inv, result, [VerificationCheck(name="reread", passed=False, detail=e.message)])
        checks = [VerificationCheck(name=f"field:{k}", passed=now.get(k) == v, detail=str(now.get(k)))
                  for k, v in (inv.arguments.get("fields") or {}).items()]
        if inv.arguments.get("comment"):
            checks.append(VerificationCheck(name="comment", passed=inv.arguments["comment"] in now["comments"]))
        return status_check(inv, result, checks)

    async def rollback(self, inv: ToolInvocation, result: ToolResult) -> bool:
        undo = self._undo.pop(result.rollback_token or "", None)
        if undo is None:
            return False
        try:
            if undo["fields"]:
                (await self.client.put(f"/rest/api/2/issue/{undo['key']}", json={"fields": undo["fields"]})).raise_for_status()
            if undo["comment_id"]:
                (await self.client.delete(f"/rest/api/2/issue/{undo['key']}/comment/{undo['comment_id']}")).raise_for_status()
        except httpx.HTTPError:
            return False
        return True
