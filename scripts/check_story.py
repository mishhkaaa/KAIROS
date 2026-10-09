"""Check a run's thought-process story (contract 0.10.0): the events the desktop tells the run with arrive in order.

    uv run python scripts/check_story.py T-xxxx [--gateway URL]     # a finished task on a running kairosd
    uv run python scripts/check_story.py mock                       # the mock gateway's Apollo replay, in-process

Reads the task's events through /ws/events (the gateway replays a task's history first) and checks:
  - one task.understood, before every agent.planned, and all of them before the first agent the planner creates;
  - every created agent: process.spawned, then its agent.created, and the created templates follow the planned roles;
  - every tool.query is followed by its task.data (same correlation id);
  - the agent that requests the approval is created before it; the planner's synthesis thought comes after it is
    resolved and before the task ends;
  - every agent.thought carries its own process's pid.
Real runs interleave the specialists and say more than the mock, so the rules are about order, not an exact sequence.
Prints the story, then one line: "PASS  story order" or "FAIL  story order: ...". The exit code is 1 on FAIL.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

STORY = {"task.understood", "agent.planned", "agent.created", "agent.thought", "tool.query", "task.data"}
MARKERS = {"process.spawned", "approval.requested", "approval.resolved", "task.completed", "task.failed"}
H = {"X-Kairos-User": "alice", "X-Kairos-Org": "acme"}

Event = dict[str, Any]


def check(events: list[Event]) -> list[str]:
    """What is out of order in a run's events; empty when the story holds."""
    evs = [e for e in events if e["type"] in STORY | MARKERS]
    types = [e["type"] for e in evs]
    problems: list[str] = []

    def need(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    understood = [i for i, t in enumerate(types) if t == "task.understood"]
    planned = [i for i, t in enumerate(types) if t == "agent.planned"]
    children = [i for i, e in enumerate(evs) if e["type"] == "process.spawned" and e["payload"].get("ppid") is not None]
    need(len(understood) == 1, f"one task.understood (got {len(understood)})")
    need(bool(planned), "at least one agent.planned")
    if understood and planned:
        need(understood[0] < planned[0], "task.understood before agent.planned")
    if planned and children:
        need(planned[-1] < children[0], "every agent.planned before the first created agent")
    for i in children:
        pid = evs[i]["pid"]
        nxt = next((e for e in evs[i + 1:] if e["pid"] == pid), None)
        need(nxt is not None and nxt["type"] == "agent.created" and nxt["payload"].get("pid") == pid,
             f"pid {pid}: agent.created right after its process.spawned")
    roles = [evs[i]["payload"]["role"] for i in planned]
    templates = [e["payload"]["template"] for e in evs if e["type"] == "agent.created"]
    need(roles == templates, f"created {templates} in the planned order {roles}")
    for i, e in enumerate(evs):
        if e["type"] == "tool.query":
            data = next((x for x in evs[i + 1:] if x["type"] == "task.data"), None)
            need(data is not None and data["correlation_id"] == e["correlation_id"],
                 f"tool.query {e['correlation_id']} followed by its task.data")
    if "approval.requested" in types:
        approval = types.index("approval.requested")
        asker = evs[approval]["pid"]  # the agent that requests the approval (action-agent, writer, ...)
        created = [i for i, e in enumerate(evs) if e["type"] == "agent.created" and e["payload"].get("pid") == asker]
        need(bool(created) and created[0] < approval, f"pid {asker} created before it requests the approval")
        synth = [i for i, e in enumerate(evs) if e["type"] == "agent.thought" and e["payload"].get("step") == "synthesize"]
        resolved = types.index("approval.resolved") if "approval.resolved" in types else len(types)
        end = next((i for i, t in enumerate(types) if t in ("task.completed", "task.failed")), len(types))
        need(bool(synth) and resolved < synth[0] < end, "the synthesis thought after the approval, before the task ends")
    need(all(e["payload"].get("pid") == e["pid"] for e in evs if e["type"] == "agent.thought"), "thoughts carry their own pid")
    return problems


def _detail(t: str, p: dict[str, Any]) -> str:
    if t == "task.understood":
        return str(p.get("intent"))
    if t in ("agent.planned", "agent.created"):
        return str(p.get("role") or p.get("template"))
    if t == "agent.thought":
        return f"{p.get('step')}: {p.get('text')}"
    if t == "tool.query":
        return f"{p.get('tool')} {p.get('query')} ({p.get('rows')} rows, {p.get('ms')} ms)"
    return f"{len(p.get('rows', []))} rows from {p.get('source')}"


def story_lines(events: list[Event]) -> list[str]:
    lines = []
    for e in events:
        p, t = e["payload"], e["type"]
        if t in STORY:
            detail = _detail(t, p)
            lines.append(f"  {e['pid'] or '-':>4} {t:16} {detail}")
        elif t in MARKERS - {"process.spawned"}:
            lines.append(f"  ---- {t}")
    return lines


def report(events: list[Event], out=None) -> bool:
    """Prints the story and the verdict line; True when it passes."""
    out = out or sys.stdout
    for line in story_lines(events):
        print(line, file=out)
    problems = check(events)
    print(f"PASS  story order ({len(events)} events)" if not problems else f"FAIL  story order: {'; '.join(problems)}", file=out)
    return not problems


def mock_events(goal: str = "Investigate Apollo") -> list[Event]:
    """The mock gateway's Apollo replay, approved as it reaches the approval."""
    from fastapi.testclient import TestClient
    from kairos_contracts.api.mock_gateway import build_mock_app

    with TestClient(build_mock_app(replay_speed=1000)) as client:
        task = client.post("/tasks", json={"goal": goal}).json()
        seen: list[Event] = []
        with client.websocket_connect(f"/ws/events?task_id={task['task_id']}") as ws:
            while True:
                ev = json.loads(ws.receive_text())
                seen.append(ev)
                if ev["type"] == "approval.requested":
                    client.post(f"/approvals/{ev['payload']['approval_id']}/approve", json={})
                if ev["type"] in ("task.completed", "task.failed"):
                    return seen


async def _fetch(gateway: str, task_id: str, quiet_s: float) -> list[Event]:
    import websockets

    url = gateway.replace("http", "ws", 1).rstrip("/") + f"/ws/events?task_id={task_id}"
    seen: list[Event] = []
    async with websockets.connect(url, max_size=None, additional_headers=H) as ws:
        while True:  # a finished task's history arrives at once; silence means it is all here
            try:
                seen.append(json.loads(await asyncio.wait_for(ws.recv(), quiet_s)))
            except TimeoutError:
                return seen


def fetch(gateway: str, task_id: str, quiet_s: float = 3.0) -> list[Event]:
    return asyncio.run(_fetch(gateway, task_id, quiet_s))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_id", help='a task id, or "mock" for the mock gateway replay')
    ap.add_argument("--gateway", default=os.getenv("KAIROS_URL", "http://127.0.0.1:8080"))
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    events = mock_events() if a.task_id == "mock" else fetch(a.gateway, a.task_id)
    return 0 if report(events) else 1


if __name__ == "__main__":
    sys.exit(main())
