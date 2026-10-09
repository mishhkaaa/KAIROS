"""Mock Jira REST service for the demo (docker compose service `mock-jira`, or `uv run kairos-mock-jira`).

Speaks a small, Jira-shaped subset of REST v2. State lives in memory; POST /_reset reseeds it.
"""
from __future__ import annotations

import copy
import itertools
import os

from fastapi import Body, FastAPI, HTTPException, Response
from kairos_contracts.schema.common import utcnow

SEED: dict[str, dict] = {
    "APOLLO-12": {"summary": "Payments DB migration", "status": {"name": "In Progress"}, "labels": ["migration"],
                  "assignee": {"displayName": "Priya"}, "duedate": "2026-08-01",
                  "description": "Ledger schema change needs a full backfill. First attempt failed on duplicate "
                                 "reconciliation ids."},
    "APOLLO-31": {"summary": "Vendor SDK upgrade", "status": {"name": "Blocked"}, "labels": ["vendor"],
                  "assignee": {"displayName": "Marco"}, "duedate": "2026-08-20",
                  "description": "Blocked on vendor certification. Support ticket open."},
    "ZEUS-7": {"summary": "Warehouse cost dashboard", "status": {"name": "Done"}, "labels": ["analytics"],
               "assignee": {"displayName": "Marco"}, "duedate": "2026-07-15", "description": "Shipped."},
    "ZEUS-9": {"summary": "Per-team query budgets", "status": {"name": "Blocked"}, "labels": ["warehouse", "cost"],
               "assignee": {"displayName": "Marco"}, "duedate": "2026-08-29",
               "description": "Cost guardrails. Blocked on the warehouse role migration; three weeks behind schedule."},
    "ZEUS-11": {"summary": "Q4 budget risk and warehouse renewal", "status": {"name": "In Progress"},
                "labels": ["budget", "warehouse"], "assignee": {"displayName": "Ananya"}, "duedate": "2026-10-15",
                "description": "Tracking issue for the Zeus Q4 budget risk ahead of the steering committee."},
}


def create_app() -> FastAPI:
    app = FastAPI(title="mock-jira", version="0.1.0")
    state: dict = {}
    ids = itertools.count(10000)

    def reset() -> None:
        state.clear()
        for key, fields in SEED.items():
            state[key] = {"key": key, "fields": copy.deepcopy(fields), "comments": []}

    reset()

    def issue_json(issue: dict) -> dict:
        return {"key": issue["key"], "fields": {**issue["fields"], "comment": {"comments": issue["comments"],
                                                                                "total": len(issue["comments"])}}}

    def get(key: str) -> dict:
        if key not in state:
            raise HTTPException(404, detail={"errorMessages": [f"Issue {key} does not exist"]})
        return state[key]

    @app.get("/rest/api/2/issue/{key}")
    async def get_issue(key: str) -> dict:
        return issue_json(get(key))

    @app.put("/rest/api/2/issue/{key}", status_code=204)
    async def update_issue(key: str, body: dict = Body(...)) -> Response:
        get(key)["fields"].update(body.get("fields", {}))
        return Response(status_code=204)

    @app.post("/rest/api/2/issue/{key}/comment", status_code=201)
    async def add_comment(key: str, body: dict = Body(...)) -> dict:
        comment = {"id": str(next(ids)), "body": body.get("body", ""), "created": utcnow().isoformat()}
        get(key)["comments"].append(comment)
        return comment

    @app.delete("/rest/api/2/issue/{key}/comment/{comment_id}", status_code=204)
    async def delete_comment(key: str, comment_id: str) -> Response:
        issue = get(key)
        issue["comments"] = [c for c in issue["comments"] if c["id"] != comment_id]
        return Response(status_code=204)

    @app.get("/rest/api/2/search")
    async def search(jql: str = "") -> dict:
        project = jql.split("=", 1)[1].strip().strip('"') if jql.lower().startswith("project") and "=" in jql else ""
        issues = [issue_json(i) for k, i in state.items() if not project or k.startswith(f"{project}-")]
        return {"issues": issues, "total": len(issues)}

    @app.post("/_reset", status_code=204)
    async def _reset() -> Response:
        reset()
        return Response(status_code=204)

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.getenv("MOCK_JIRA_PORT", "8090")))


if __name__ == "__main__":
    main()
