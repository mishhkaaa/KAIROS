"""Every gateway route, including error codes and ErrorInfo bodies."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient
from kairos_contracts.api import route_signatures
from kairos_contracts.api.mock_gateway import build_mock_app
from kairos_contracts.schema import Risk, SyscallRequest
from kairos_contracts.schema.common import new_id
from kairos_kernel.gateway.app import create_app
from kairos_kernel.testing import done, manifest


def wait_for(fn, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


@pytest.fixture
def client(make_kernel):
    gate = {"release": None}

    async def planner(goal, ctx):
        if goal == "spawn":
            child = await ctx.spawn("worker", "work")
            return await ctx.wait(child)
        if goal == "approve-me":
            res = await ctx.syscall(SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid,
                                                   capability="jira.write", tool="jira", operation="update_issue",
                                                   risk=Risk.MEDIUM, arguments={"key": "APOLLO-12", "comment": "hi"}))
            return done(ctx, res.status.value)
        if goal == "long":
            for _ in range(500):
                await ctx.log("tick")
                await asyncio.sleep(0.01)
        await ctx.put_artifact("report.md", "# report", "text/markdown")
        return done(ctx, f"done: {goal}")

    async def worker(goal, ctx):
        await asyncio.sleep(0.05)
        return done(ctx, "worker done")

    k = make_kernel({"planner-agent": planner, "worker": worker},
                    [manifest("planner-agent", agents=["worker"], tools=["jira.write"]), manifest("worker")])
    with TestClient(create_app(k)) as c:
        c.kernel = k
        c.gate = gate
        yield c


def post_task(client, goal, **kw):
    r = client.post("/tasks", json={"goal": goal, "metadata": {"root_agent": "planner-agent"}, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def finished(client, task_id):
    return wait_for(lambda: (t := client.get(f"/tasks/{task_id}").json())["status"] in ("completed", "failed", "cancelled")
                    and t)


def test_route_set_matches_contract(client):
    assert route_signatures(build_mock_app()) <= route_signatures(client.app)


def test_system_routes(client):
    assert client.get("/health").json() == {"ok": True}
    status = client.get("/system/status").json()
    assert status["ready"] and {c["component"] for c in status["components"]} >= {"kernel", "tools", "knowledge"}
    res = client.get("/system/resources").json()
    assert res["gpu"]["name"] == "Fake RTX" and "tokens_last_minute" in res
    assert {m["name"] for m in client.get("/models").json()} == {"fake-chat", "fake-embed"}


def test_task_lifecycle_routes(client):
    t = post_task(client, "hello", priority="high")
    assert t["status"] == "queued" and t["priority"] == "high" and t["user_id"] == "alice"
    t = finished(client, t["task_id"])
    assert t["status"] == "completed" and t["result"]["summary"] == "done: hello"
    assert t["result"]["artifacts"] == [f"artifact://{t['task_id']}/report.md"]
    assert client.get(f"/tasks/{t['task_id']}/artifacts").json() == t["result"]["artifacts"]
    report = client.get(f"/tasks/{t['task_id']}/artifacts/report.md")
    assert report.status_code == 200 and report.text == "# report"
    assert report.headers["content-type"].startswith("text/markdown") and report.headers["x-content-type-options"] == "nosniff"
    missing = client.get(f"/tasks/{t['task_id']}/artifacts/nope.md")
    assert missing.status_code == 404 and missing.json()["code"] == "ARTIFACT_NOT_FOUND"
    assert client.get(f"/tasks/{t['task_id']}/artifacts/..%2F..%2Fsecrets").status_code in (400, 404)
    assert t["task_id"] in [x["task_id"] for x in client.get("/tasks", params={"status": "completed"}).json()]
    err = client.get("/tasks/T-missing")
    assert err.status_code == 404 and err.json() == {"code": "TASK_NOT_FOUND", "message": "T-missing", "retriable": False,
                                                     "details": {}}
    assert client.post("/tasks", json={"goal": ""}).status_code == 422


def test_identity_headers(client):
    t = client.post("/tasks", json={"goal": "who", "metadata": {"root_agent": "planner-agent"}},
                    headers={"X-Kairos-User": "bob", "X-Kairos-Org": "globex"}).json()
    assert t["user_id"] == "bob" and t["org_id"] == "globex"


def test_process_routes_and_controls(client):
    t = post_task(client, "long")
    root = wait_for(lambda: client.get(f"/tasks/{t['task_id']}").json()["root_pid"])
    assert client.get(f"/agents/{root}").json()["agent"] == "planner-agent"
    assert client.get("/agents", params={"task_id": t["task_id"]}).json()[0]["pid"] == root
    assert client.get("/agents/tree", params={"task_id": t["task_id"]}).json()[0]["pid"] == root
    assert client.post(f"/agents/{root}/pause").json()["state"] == "PAUSED"
    assert wait_for(lambda: client.get(f"/tasks/{t['task_id']}").json()["status"] == "paused")
    assert client.post(f"/agents/{root}/resume").json()["state"] == "RUNNING"
    cp = client.post(f"/agents/{root}/checkpoint").json()
    assert cp["pid"] == root and cp["checkpoint_id"].startswith("CKPT-")
    assert [c["pid"] for c in client.post(f"/tasks/{t['task_id']}/checkpoint").json()] == [root]
    assert client.post(f"/agents/{root}/kill").json()["state"] == "TERMINATED"
    assert finished(client, t["task_id"])["status"] == "cancelled"
    assert client.post(f"/agents/{root}/pause").status_code == 409
    assert client.get("/agents/99999").status_code == 404


def test_cancel_and_resume_task(client):
    t = post_task(client, "long")
    wait_for(lambda: client.get(f"/tasks/{t['task_id']}").json()["root_pid"])
    assert client.post(f"/tasks/{t['task_id']}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/tasks/{t['task_id']}/resume").json()["status"] == "cancelled"
    assert client.post("/tasks/T-missing/cancel").status_code == 404


def test_spawn_route(client):
    t = post_task(client, "long")
    root = wait_for(lambda: client.get(f"/tasks/{t['task_id']}").json()["root_pid"])
    child = client.post("/agents/spawn", json={"agent": "worker", "goal": "extra", "task_id": t["task_id"], "ppid": root})
    assert child.status_code == 201 and child.json()["ppid"] == root
    denied = client.post("/agents/spawn", json={"agent": "planner-agent", "goal": "x", "task_id": t["task_id"], "ppid": root})
    assert denied.status_code == 403 and denied.json()["code"] == "CAPABILITY_DENIED"
    assert client.post("/agents/spawn", json={"agent": "ghost", "goal": "x", "task_id": t["task_id"]}).status_code == 404
    client.post(f"/tasks/{t['task_id']}/cancel")


def test_approval_routes(client):
    t = post_task(client, "approve-me")
    pending = wait_for(lambda: client.get("/approvals", params={"status": "pending"}).json())
    approval = pending[0]
    assert approval["syscall"]["capability"] == "jira.write" and approval["task_id"] == t["task_id"]
    assert client.get(f"/tasks/{t['task_id']}").json()["status"] == "waiting_approval"
    ok = client.post(f"/approvals/{approval['approval_id']}/approve", json={"comment": "go"},
                     headers={"X-Kairos-User": "carol"}).json()
    assert ok["status"] == "approved" and ok["resolved_by"] == "carol" and ok["comment"] == "go"
    again = client.post(f"/approvals/{approval['approval_id']}/reject")
    assert again.status_code == 409 and again.json()["code"] == "APPROVAL_ALREADY_RESOLVED"
    assert client.post("/approvals/APR-missing/approve").status_code == 404
    assert finished(client, t["task_id"])["result"]["summary"] == "completed"
    timeline = client.get(f"/audit/{t['task_id']}").json()
    assert timeline["stats"]["approvals"] == 1 and timeline["goal"] == "approve-me"


def test_reject_route(client):
    t = post_task(client, "approve-me")
    approval = wait_for(lambda: client.get("/approvals", params={"status": "pending"}).json())[0]
    assert client.post(f"/approvals/{approval['approval_id']}/reject").json()["status"] == "rejected"
    assert finished(client, t["task_id"])["result"]["summary"] == "rejected"


def test_registry_policy_sandbox_routes(client):
    assert {m["name"] for m in client.get("/registry/agents").json()} == {"planner-agent", "worker"}
    assert "jira" in {s["name"] for s in client.get("/registry/tools").json()}
    assert "project-updates-v1" in {p["policy"] for p in client.get("/policies").json()}
    assert client.get("/sandboxes").json() == []


def test_knowledge_and_memory_routes(client):
    hits = client.get("/knowledge/search", params={"q": "Apollo budget overrun"}).json()["hits"]
    assert hits and hits[0]["path"] == "/org/finance/apollo-budget"
    assert "/org/projects" in {e["path"] for e in client.get("/knowledge/tree").json()["entries"]}
    assert client.get("/knowledge/object", params={"path": "/org/projects/apollo"}).json()["frontmatter"]["title"] == "Project Apollo"
    assert client.get("/knowledge/object", params={"path": "/org/finance/payroll-2026"}).status_code == 403
    assert client.get("/knowledge/object", params={"path": "/org/nope"}).status_code == 404
    assert client.get("/knowledge/graph", params={"path": "/org/projects/apollo"}).json()["edges"]
    assert client.post("/knowledge/validate").json()["files_checked"] > 5
    assert client.post("/knowledge/reindex").json()["indexed"] > 5
    assert client.post("/knowledge/ingest", json={"source_type": "url", "uri": "https://x"}).json()["skipped"]
    assert client.get("/memory").json() == []


def test_websocket_filters_and_live_stream(client):
    t = post_task(client, "spawn")
    with client.websocket_connect(f"/ws/events?task_id={t['task_id']}&types=process.spawned,task.completed") as ws:
        seen = []
        while True:
            ev = json.loads(ws.receive_text())
            seen.append((ev["type"], ev["payload"].get("agent")))
            if ev["type"] == "task.completed":
                break
    worker = f"worker@{t['task_id']}"  # children are generated from their template, per task
    assert seen == [("process.spawned", "planner-agent"), ("process.spawned", worker), ("task.completed", None)]
