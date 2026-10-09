"""Thought-process events (0.10.0): payload models, the Apollo example stream, ctx.narrate on the fake, the mock replay."""
import asyncio
import json

import pytest
from kairos_contracts import examples
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    MAX_DATA_ROWS,
    THOUGHT_EVENT_MODELS,
    AgentPlanned,
    AgentThought,
    EventType,
    TaskData,
    TaskUnderstood,
    ToolQuery,
)
from kairos_contracts.testing.fakes import FakeAgentContext
from pydantic import ValidationError

STORY = [EventType.TASK_UNDERSTOOD, EventType.AGENT_PLANNED, EventType.AGENT_CREATED, EventType.AGENT_THOUGHT,
         EventType.TOOL_QUERY, EventType.TASK_DATA]


def test_every_thought_event_type_has_a_payload_model():
    assert set(THOUGHT_EVENT_MODELS) == set(STORY)


def test_example_stream_payloads_validate():
    evs = examples.events()
    assert {e.type for e in evs} >= {t.value for t in STORY}
    for e in evs:
        if e.type in THOUGHT_EVENT_MODELS:
            THOUGHT_EVENT_MODELS[EventType(e.type)].model_validate(e.payload)


def test_example_stream_tells_the_story_in_order():
    evs = examples.events()
    assert [e.ts for e in evs] == sorted(e.ts for e in evs)
    first = {t: next(i for i, e in enumerate(evs) if e.type == t) for t in STORY}
    assert first[EventType.TASK_UNDERSTOOD] < first[EventType.AGENT_PLANNED] < first[EventType.AGENT_CREATED]
    assert first[EventType.TOOL_QUERY] < first[EventType.TASK_DATA]
    planned = [e.payload["role"] for e in evs if e.type == EventType.AGENT_PLANNED]
    created = [e for e in evs if e.type == EventType.AGENT_CREATED]
    spawned = {e.pid: e.payload["agent"] for e in evs if e.type == EventType.PROCESS_SPAWNED}
    assert [c.payload["template"] for c in created] == planned  # each planned agent is created, in plan order
    for c in created:
        assert spawned[c.payload["pid"]] == c.payload["manifest_name"] and c.pid == c.payload["pid"]
    for e in evs:
        if e.type == EventType.AGENT_THOUGHT:
            assert e.payload["pid"] == e.pid


def test_payloads_stay_small():
    with pytest.raises(ValidationError):
        AgentThought(step="plan", text="x" * 241)
    with pytest.raises(ValidationError):
        AgentThought(step="x" * 41, text="ok")
    with pytest.raises(ValidationError):
        TaskUnderstood(intent="x" * 241, plan_summary="ok")
    with pytest.raises(ValidationError):
        ToolQuery(pid=101, tool="db.query", query="select 1", rows=-1, ms=0)
    with pytest.raises(ValidationError):
        AgentPlanned(role="finance-agent", why="ok", surprise=1)  # flat and closed: no extra fields


def test_task_data_is_capped_at_200_rows():
    rows = [[i, f"v{i}", i * 1.5, None] for i in range(MAX_DATA_ROWS + 50)]
    with pytest.raises(ValidationError):
        TaskData(columns=["id", "vendor", "amount", "note"], rows=rows, source="db.query")
    capped = TaskData.capped(["id", "vendor", "amount", "note"], rows, "db.query")
    assert len(capped.rows) == MAX_DATA_ROWS == 200 and capped.rows[0] == [0, "v0", 0.0, None]


def test_fake_context_narrates_and_stamps_the_pid():
    ctx = FakeAgentContext(pid=107)
    asyncio.run(ctx.narrate(AgentThought(pid=999, step="plan", text="Planning 4 steps.")))
    asyncio.run(ctx.narrate(TaskUnderstood(intent="investigate", plan_summary="four agents")))
    assert ctx.narrations[0].pid == 107  # an agent cannot speak for another pid
    assert isinstance(ctx.narrations[1], TaskUnderstood)
    with pytest.raises(KairosError) as e:  # kernel-only events cannot be narrated by an agent
        asyncio.run(ctx.narrate(ToolQuery(pid=107, tool="db.query", query="select 1", rows=1, ms=1)))
    assert e.value.code == "BAD_REQUEST"


def test_mock_gateway_replays_the_story_before_the_approval():
    from fastapi.testclient import TestClient
    from kairos_contracts.api.mock_gateway import build_mock_app

    with TestClient(build_mock_app(replay_speed=1000)) as client:
        task = client.post("/tasks", json={"goal": "Investigate Apollo"}).json()
        with client.websocket_connect(f"/ws/events?task_id={task['task_id']}") as ws:
            seen = []
            while True:
                ev = json.loads(ws.receive_text())
                seen.append(ev)
                if ev["type"] == "approval.requested":
                    client.post(f"/approvals/{ev['payload']['approval_id']}/approve", json={})
                if ev["type"] == "task.completed":
                    break
    types = [e["type"] for e in seen]
    approval = types.index("approval.requested")
    for t in STORY:
        assert t.value in types[:approval], t
    assert all(e["task_id"] == task["task_id"] for e in seen)
    assert types.index("agent.thought", approval) < types.index("task.completed")  # the planner's closing thought
