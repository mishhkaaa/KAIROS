"""LIVE system test: every P1 component real, backed by real containers.

  redis:7-alpine        -> event bus mirror (durable history)
  kairos/mock-jira      -> jira tool over real HTTP
  Docker                -> sandbox manager
  policies/*.yaml       -> YAML policy engine
  SQLite                -> kernel state + hash-chained audit log
  filesystem            -> artifact store

Agents/knowledge/models stay on their fakes until P2/P3/P4 land (flip KAIROS_MODE_* then).
Skipped when Docker or the images are unavailable:
    docker build -t kairos/mock-jira:latest -f infra/compose/mock-jira.Dockerfile .
"""
import json
import subprocess
import time
import uuid

import httpx
import pytest
from kairos_contracts.wiring import COMPONENTS, Settings

P1_COMPONENTS = ["events", "policy", "audit", "artifacts", "tools", "sandbox"]


def _run(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True)


def _container(image: str, port: int) -> tuple[str, str]:
    name = f"kairos-live-{uuid.uuid4().hex[:6]}"
    started = _run("docker", "run", "-d", "--rm", "--name", name, "-p", f"127.0.0.1::{port}", image)
    if started.returncode != 0:
        pytest.skip(f"cannot start {image}: {started.stderr.strip()[:150]}")
    host_port = _run("docker", "port", name, f"{port}/tcp").stdout.strip().splitlines()[0].rsplit(":", 1)[1]
    return name, host_port


@pytest.fixture(scope="module")
def infra():
    if _run("docker", "info").returncode != 0:
        pytest.skip("docker not available")
    if _run("docker", "image", "inspect", "kairos/mock-jira:latest").returncode != 0:
        pytest.skip("build kairos/mock-jira first (see module docstring)")
    names = []
    try:
        redis_name, redis_port = _container("redis:7-alpine", 6379)
        names.append(redis_name)
        jira_name, jira_port = _container("kairos/mock-jira:latest", 8090)
        names.append(jira_name)
        jira_url = f"http://127.0.0.1:{jira_port}"
        deadline = time.monotonic() + 30
        while True:
            try:
                if httpx.get(f"{jira_url}/rest/api/2/issue/APOLLO-12", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                pytest.skip("mock-jira did not start")
            time.sleep(0.5)
        yield {"redis_url": f"redis://127.0.0.1:{redis_port}/0", "jira_url": jira_url}
    finally:
        for n in names:
            _run("docker", "rm", "-f", n)


def test_apollo_run_on_real_p1_stack(infra, tmp_path, monkeypatch):
    monkeypatch.setenv("KAIROS_EVENTS_REDIS", "auto")  # this test wants the mirror (on its own container)
    from fastapi.testclient import TestClient
    from kairos_kernel import factory
    from kairosd.wiring import build_services

    settings = Settings(data_dir=tmp_path, redis_url=infra["redis_url"], jira_url=infra["jira_url"])
    settings.modes = {c: ("real" if c in P1_COMPONENTS else "fake") for c in COMPONENTS}
    services = build_services(settings)
    assert {services.modes[a] for a in ("event_bus", "policy", "audit", "artifacts", "tools", "sandbox")} == {"real"}
    assert services.event_bus.mirror is not None, "redis mirror attached"

    with TestClient(factory.build_kernel_app(settings, services)) as client:
        components = {c["component"]: c["mode"] for c in client.get("/system/status").json()["components"]}
        assert components["policy"] == components["tools"] == components["sandbox"] == "real"

        task = client.post("/tasks", json={"goal": "Investigate why Project Apollo is over budget and behind schedule, "
                                                    "update the tracker, and prepare a recovery plan."}).json()
        seen = []
        with client.websocket_connect(f"/ws/events?task_id={task['task_id']}") as ws:
            while True:
                ev = json.loads(ws.receive_text())
                seen.append(ev["type"])
                if ev["type"] == "approval.requested":
                    assert ev["payload"]["policy"] == "project-updates-v1", "real YAML policy decided"
                    client.post(f"/approvals/{ev['payload']['approval_id']}/approve", json={"comment": "live test"})
                if ev["type"] in ("task.completed", "task.failed"):
                    break
        assert seen[-1] == "task.completed" and "transaction.committed" in seen

        issue = httpx.get(f"{infra['jira_url']}/rest/api/2/issue/APOLLO-12").json()
        comments = [c["body"] for c in issue["fields"]["comment"]["comments"]]
        assert any("KAIROS" in c for c in comments), "the approved action really changed the Jira container"

        timeline = client.get(f"/audit/{task['task_id']}").json()
        assert {"policy", "approval", "tool", "verify", "commit"} <= {e["kind"] for e in timeline["entries"]}
        assert services.audit.verify_chain(task["task_id"]), "audit hash chain intact"
        assert client.get(f"/tasks/{task['task_id']}").json()["result"]["actions"], "committed action recorded"

    import redis

    stream = redis.from_url(infra["redis_url"]).xrange("kairos:events")
    mirrored = [json.loads(fields[b"e"]) for _, fields in stream]
    assert any(e["type"] == "task.completed" and e["task_id"] == task["task_id"] for e in mirrored)
