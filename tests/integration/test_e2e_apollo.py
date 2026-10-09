"""End-to-end demo scenario (blueprint §47) through the REAL gateway, whatever mix of fake/real services is wired.

    KAIROS_DEFAULT_MODE=fake  uv run pytest tests/integration      # kernel on all fakes
    KAIROS_DEFAULT_MODE=real  uv run pytest tests/integration      # full system (needs compose up)

Skips until P1's build_kernel_app exists. This test is the integration gate: it must pass before every merge to main
once the kernel lands.
"""
import json
import tempfile
from pathlib import Path

import pytest
from kairos_contracts.wiring import Settings

pytest.importorskip("kairosd")


def _app():
    from kairos_kernel import factory
    from kairosd.wiring import build_services

    settings = Settings.from_env()
    settings.data_dir = Path(tempfile.mkdtemp(prefix="kairos-e2e-"))  # fresh kernel state per run
    try:
        return factory.build_kernel_app(settings, build_services(settings))
    except NotImplementedError as e:
        pytest.skip(f"kernel not implemented yet: {e}")


def test_apollo_run_with_approval():
    from fastapi.testclient import TestClient

    with TestClient(_app()) as client:
        task = client.post("/tasks", json={"goal": "Investigate why Project Apollo is over budget and behind schedule, "
                                                    "update the tracker, and prepare a recovery plan."}).json()
        seen: list[str] = []
        with client.websocket_connect(f"/ws/events?task_id={task['task_id']}") as ws:
            while True:
                ev = json.loads(ws.receive_text())
                seen.append(ev["type"])
                if ev["type"] == "approval.requested":
                    client.post(f"/approvals/{ev['payload']['approval_id']}/approve", json={"comment": "ok"})
                if ev["type"] in ("task.completed", "task.failed"):
                    break

        assert "process.spawned" in seen and "knowledge.retrieved" in seen
        assert "approval.requested" in seen and "transaction.committed" in seen
        assert seen[-1] == "task.completed"

        procs = client.get("/agents", params={"task_id": task["task_id"]}).json()
        assert len(procs) >= 3, "planner + at least two specialists"
        timeline = client.get(f"/audit/{task['task_id']}").json()
        kinds = {e["kind"] for e in timeline["entries"]}
        assert {"task", "spawn", "policy", "approval", "tool", "commit"} <= kinds
