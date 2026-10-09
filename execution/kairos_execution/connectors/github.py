"""`github` tool backend: read repos/issues/PRs, create issues and comments.

Tokens are stored in the token vault (vault.py) per-org, never logged or sent to agents.
github_token="inprocess" runs the mock in dev mode.
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

SPEC = ToolSpec(
    name="github",
    description="GitHub REST API (repos, issues, PRs, comments). "
                "github.read is read-only; github.write creates issues and comments and requires approval.",
    transport=ToolTransport.HTTP,
    operations=[
        ToolOperation(
            name="list_repos",
            capability="github.read",
            description="List repositories for the authenticated user or org",
            input_schema={"type": "object", "properties": {"org": {"type": "string"}}},
        ),
        ToolOperation(
            name="get_issue",
            capability="github.read",
            description="Read a GitHub issue",
            input_schema={
                "type": "object",
                "required": ["owner", "repo", "number"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "number": {"type": "integer"},
                },
            },
        ),
        ToolOperation(
            name="list_issues",
            capability="github.read",
            description="List issues for a repository",
            input_schema={
                "type": "object",
                "required": ["owner", "repo"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"]},
                },
            },
        ),
        ToolOperation(
            name="get_file",
            capability="github.read",
            description="Read a file from a repository",
            input_schema={
                "type": "object",
                "required": ["owner", "repo", "path"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "path": {"type": "string"},
                    "ref": {"type": "string"},
                },
            },
        ),
        ToolOperation(
            name="create_issue",
            capability="github.write",
            description="Create a new issue",
            input_schema={
                "type": "object",
                "required": ["owner", "repo", "title"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                },
            },
            risk=Risk.MEDIUM,
            reversible=False,
        ),
        ToolOperation(
            name="create_comment",
            capability="github.write",
            description="Add a comment to an issue or PR",
            input_schema={
                "type": "object",
                "required": ["owner", "repo", "number", "body"],
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "number": {"type": "integer"},
                    "body": {"type": "string"},
                },
            },
            risk=Risk.MEDIUM,
            reversible=True,
        ),
    ],
)


class GitHubBackend:
    name = "github"

    def __init__(self, token_or_mode: str = "inprocess") -> None:
        self._undo: dict[str, dict[str, Any]] = {}
        self.client: httpx.AsyncClient
        self.configure(None if token_or_mode == "inprocess" else token_or_mode)

    @property
    def live(self) -> bool:
        return self._token is not None

    def configure(self, token: str | None) -> None:
        """Switch between the built-in mock (no token) and the real API. The gateway calls this when an org connects
        or disconnects GitHub; the token stays inside this backend and the vault, never in an invocation or a log."""
        self._token = token
        self.client = httpx.AsyncClient(
            base_url="https://api.github.com",
            transport=None if token else _MockTransport(),
            headers={"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {token}"} if token else {})},
            timeout=15,
        )

    def spec(self) -> ToolSpec:
        return SPEC

    async def execute(self, inv: ToolInvocation) -> ToolResult:
        a = inv.arguments
        try:
            if inv.operation == "list_repos":
                org = a.get("org")
                path = f"/orgs/{org}/repos" if org else "/user/repos"
                r = await self.client.get(path, params={"per_page": 20})
                r.raise_for_status()
                repos = [{"name": rp["name"], "full_name": rp["full_name"], "description": rp.get("description"),
                          "open_issues": rp.get("open_issues_count", 0)} for rp in r.json()]
                return ok(inv, {"repos": repos})

            if inv.operation == "get_issue":
                require(a, "owner", "repo", "number")
                r = await self.client.get(f"/repos/{a['owner']}/{a['repo']}/issues/{a['number']}")
                if r.status_code == 404:
                    raise KairosError("NOT_FOUND", f"issue #{a['number']}")
                r.raise_for_status()
                return ok(inv, _flatten_issue(r.json()))

            if inv.operation == "list_issues":
                require(a, "owner", "repo")
                r = await self.client.get(f"/repos/{a['owner']}/{a['repo']}/issues",
                                          params={"state": a.get("state", "open"), "per_page": 20})
                r.raise_for_status()
                return ok(inv, {"issues": [_flatten_issue(i) for i in r.json()]})

            if inv.operation == "get_file":
                require(a, "owner", "repo", "path")
                params = {"ref": a["ref"]} if a.get("ref") else {}
                r = await self.client.get(f"/repos/{a['owner']}/{a['repo']}/contents/{a['path']}", params=params)
                if r.status_code == 404:
                    raise KairosError("NOT_FOUND", f"{a['path']}")
                r.raise_for_status()
                body = r.json()
                import base64
                content = base64.b64decode(body.get("content", "")).decode("utf-8", errors="replace") if body.get("encoding") == "base64" else ""
                return ok(inv, {"path": body["path"], "sha": body["sha"], "content": content})

            if inv.operation == "create_issue":
                require(a, "owner", "repo", "title")
                payload: dict[str, Any] = {"title": a["title"]}
                if a.get("body"):
                    payload["body"] = a["body"]
                if a.get("labels"):
                    payload["labels"] = a["labels"]
                r = await self.client.post(f"/repos/{a['owner']}/{a['repo']}/issues", json=payload)
                r.raise_for_status()
                return ok(inv, _flatten_issue(r.json()))

            if inv.operation == "create_comment":
                require(a, "owner", "repo", "number", "body")
                r = await self.client.post(f"/repos/{a['owner']}/{a['repo']}/issues/{a['number']}/comments",
                                           json={"body": a["body"]})
                r.raise_for_status()
                comment = r.json()
                rb = token()
                self._undo[rb] = {"owner": a["owner"], "repo": a["repo"], "comment_id": comment["id"]}
                return ok(inv, {"id": comment["id"], "body": comment["body"]}, rollback_token=rb)

            return err(inv, "NOT_FOUND", f"unknown github operation {inv.operation}")
        except KairosError as e:
            return err(inv, e.code, e.message)
        except httpx.HTTPError as e:
            return err(inv, "TOOL_FAILED", f"github request failed: {e}")

    async def verify(self, inv: ToolInvocation, result: ToolResult) -> VerificationResult:
        if result.status != ToolResultStatus.SUCCESS or inv.operation != "create_comment":
            return status_check(inv, result)
        # Re-read the comment to verify it exists
        undo = self._undo.get(result.rollback_token or "")
        if not undo:
            return status_check(inv, result)
        try:
            r = await self.client.get(f"/repos/{undo['owner']}/{undo['repo']}/issues/comments/{undo['comment_id']}")
            exists = r.status_code == 200
            return status_check(inv, result, [VerificationCheck(name="comment_exists", passed=exists)])
        except httpx.HTTPError as e:
            return status_check(inv, result, [VerificationCheck(name="comment_exists", passed=False, detail=str(e))])

    async def rollback(self, inv: ToolInvocation, result: ToolResult) -> bool:
        undo = self._undo.pop(result.rollback_token or "", None)
        if undo is None:
            return False
        try:
            r = await self.client.delete(f"/repos/{undo['owner']}/{undo['repo']}/issues/comments/{undo['comment_id']}")
            return r.status_code in (204, 404)
        except httpx.HTTPError:
            return False


def _flatten_issue(i: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": i["number"],
        "title": i["title"],
        "state": i["state"],
        "body": i.get("body"),
        "html_url": i.get("html_url"),
        "labels": [lb["name"] for lb in i.get("labels", [])],
        "assignee": (i.get("assignee") or {}).get("login"),
        "created_at": i.get("created_at"),
    }


class _MockTransport(httpx.AsyncBaseTransport):
    """In-process stand-in for GitHub (dev and the demo): the demo company's repository, and it remembers what is written,
    so verification and rollback behave like the real API."""

    ISSUES = [
        {"number": 12, "title": "Backfill failed on duplicate reconciliation ids", "state": "open",
         "body": "The APOLLO-12 migration backfill stopped at 38% on duplicate recon_id values.", "labels": [{"name": "apollo"}]},
        {"number": 31, "title": "Upgrade to PayCo SDK v5 (blocked on certification)", "state": "open",
         "body": "PayCo moved v5 GA to 2026-10-20; the certification blocks our release.", "labels": [{"name": "vendor"}]},
    ]
    README = "\n".join([
        "# reconciliation",
        "",
        "Acme's payment reconciliation pipeline (Project Apollo).",
        "",
        "- `backfill/`: the migration backfill",
        "- `sdk/`: the PayCo SDK integration",
        "",
    ])

    def __init__(self) -> None:
        self.comments: dict[int, dict[str, Any]] = {}
        self.created: list[dict[str, Any]] = []

    def _issue(self, i: dict[str, Any]) -> dict[str, Any]:
        return {"html_url": f"https://github.com/acme/reconciliation/issues/{i['number']}", "assignee": None,
                "created_at": "2026-09-01T09:00:00Z", **i}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        import base64 as _b64
        import json as _json

        path, method = request.url.path, request.method
        if path.endswith("/issues") and method == "GET":
            return httpx.Response(200, json=[self._issue(i) for i in self.ISSUES + self.created])
        if path.endswith("/issues") and method == "POST":
            body = _json.loads(request.content)
            issue = {"number": 100 + len(self.created), "title": body.get("title", ""), "state": "open", "body": body.get("body", ""),
                     "labels": [{"name": n} for n in body.get("labels", [])]}
            self.created.append(issue)
            return httpx.Response(201, json=self._issue(issue))
        if "/issues/comments/" in path:
            cid = int(path.rsplit("/", 1)[-1])
            if method == "DELETE":
                return httpx.Response(204 if self.comments.pop(cid, None) else 404)
            return httpx.Response(200, json=self.comments[cid]) if cid in self.comments else httpx.Response(404, json={"message": "Not Found"})
        if path.endswith("/comments") and method == "POST":
            cid = 12345 + len(self.comments)
            self.comments[cid] = {"id": cid, "body": _json.loads(request.content).get("body", "")}
            return httpx.Response(201, json=self.comments[cid])
        if "/issues/" in path and method == "GET":
            number = int(path.rsplit("/", 1)[-1])
            found = next((i for i in self.ISSUES + self.created if i["number"] == number), None)
            return httpx.Response(200, json=self._issue(found)) if found else httpx.Response(404, json={"message": "Not Found"})
        if path.endswith("/repos"):
            return httpx.Response(200, json=[{"name": "reconciliation", "full_name": "acme/reconciliation",
                                              "description": "Payment reconciliation pipeline (Project Apollo)", "open_issues_count": 2}])
        if "/contents/" in path:
            return httpx.Response(200, json={"path": path.split("/contents/")[-1], "sha": "a1b2c3", "encoding": "base64",
                                             "content": _b64.b64encode(self.README.encode()).decode()})
        return httpx.Response(404, json={"message": "Not Found"})
