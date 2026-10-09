"""Event bus envelope + the event type catalog (full producer/consumer table: shared/catalogs/events.yaml)."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from .common import Contract, Pid, TaskId, new_id, utcnow


class EventType(StrEnum):
    # tasks (P1)
    TASK_CREATED = "task.created"
    TASK_STATUS_CHANGED = "task.status_changed"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    # processes (P1)
    PROCESS_SPAWNED = "process.spawned"
    PROCESS_STATE_CHANGED = "process.state_changed"
    PROCESS_CHECKPOINTED = "process.checkpointed"
    PROCESS_USAGE = "process.usage"
    AGENT_LOG = "agent.log"                  # agent "thoughts"/progress lines for the UI
    # syscalls / governance (P1)
    SYSCALL_REQUESTED = "syscall.requested"
    SYSCALL_DECIDED = "syscall.decided"
    SYSCALL_COMPLETED = "syscall.completed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    TRANSACTION_COMMITTED = "transaction.committed"
    TRANSACTION_ROLLED_BACK = "transaction.rolled_back"
    POLICY_UPDATED = "policy.updated"
    AUDIT_APPENDED = "audit.appended"
    # IPC (P1 routes, P3 produces)
    IPC_MESSAGE = "ipc.message"
    # knowledge & memory (P2)
    KNOWLEDGE_CHANGED = "knowledge.changed"
    KNOWLEDGE_REINDEXED = "knowledge.reindexed"
    KNOWLEDGE_RETRIEVED = "knowledge.retrieved"
    INGEST_PROGRESS = "ingest.progress"
    MOUNT_SYNCED = "mount.synced"
    CONNECTOR_CHANGED = "connector.changed"
    MEMORY_INVALIDATED = "memory.invalidated"
    MEMORY_CONSOLIDATED = "memory.consolidated"
    # models (P3)
    MODEL_INVOKED = "model.invoked"
    # execution (P4)
    SANDBOX_STARTED = "sandbox.started"
    SANDBOX_DESTROYED = "sandbox.destroyed"
    SANDBOX_SCREENSHOT = "sandbox.screenshot"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    # system (P1/P4)
    SYSTEM_READY = "system.ready"
    SYSTEM_HEALTH = "system.health"
    CRON_TRIGGERED = "cron.triggered"
    # thought process (P3 agents via ctx.narrate; P1 for agent.created, tool.query, task.data)
    TASK_UNDERSTOOD = "task.understood"
    AGENT_PLANNED = "agent.planned"
    AGENT_CREATED = "agent.created"
    AGENT_THOUGHT = "agent.thought"
    TOOL_QUERY = "tool.query"
    TASK_DATA = "task.data"


class Event(Contract):
    event_id: str = Field(default_factory=lambda: new_id("EV"))
    type: str = Field(description="An EventType value; custom types must be namespaced x.<owner>.<name>")
    ts: datetime = Field(default_factory=utcnow)
    source: str = Field(description='Component or "pid:<n>", e.g. "kernel.scheduler", "knowledge.indexer"')
    org_id: str | None = None
    task_id: TaskId | None = None
    pid: Pid | None = None
    correlation_id: str | None = Field(None, description="e.g. syscall_id or approval_id")
    payload: dict[str, Any] = Field(default_factory=dict, description="See events.yaml for the payload model per type")


# --------------------------------------------------------------------------- thought-process payloads
# The run told as a story for the UI. Small and flat on purpose. Every text field is a short summary written by agent
# or kernel code: never raw model chain-of-thought and never retrieved document text (retrieved text is data).

MAX_THOUGHT_CHARS = 240
MAX_DATA_ROWS = 200

Cell = str | int | float | bool | None


class TaskUnderstood(Contract):
    """task.understood: what the planner took the goal to mean, before it assigns agents."""
    intent: str = Field(max_length=MAX_THOUGHT_CHARS, description='e.g. "investigate budget overrun and schedule slip"')
    entities: list[str] = Field(default_factory=list, max_length=20, description='e.g. ["Project Apollo", "APOLLO-12"]')
    capabilities_needed: list[str] = Field(default_factory=list, max_length=20, description="e.g. knowledge.search, jira.write")
    plan_summary: str = Field(max_length=MAX_THOUGHT_CHARS)


class AgentPlanned(Contract):
    """agent.planned: one agent the planner decided to create, before it exists (no pid yet)."""
    role: str = Field(description="Role template id; the matching agent.created carries it as `template`")
    why: str = Field(max_length=MAX_THOUGHT_CHARS)
    scope: list[str] = Field(default_factory=list, description="/org paths or globs it may read")
    capabilities: list[str] = Field(default_factory=list)


class AgentCreated(Contract):
    """agent.created: the kernel spawned an agent. `generated` is true for a manifest built for this task."""
    pid: int
    manifest_name: str
    template: str = Field(description="Role template id (equals agent.planned.role); the manifest name for fixed agents")
    generated: bool = False


class AgentThought(Contract):
    """agent.thought: one short visible step of an agent. `pid` is set by the kernel, not the agent."""
    pid: int | None = None
    step: str = Field(max_length=40, description='Short step label, e.g. "search", "plan", "synthesize"')
    text: str = Field(max_length=MAX_THOUGHT_CHARS, description="One sentence")


class ToolQuery(Contract):
    """tool.query: a query a tool ran for an agent (e.g. the SQL of db.query), with its row count and duration."""
    pid: int
    tool: str
    query: str = Field(max_length=4000)
    rows: int = Field(ge=0)
    ms: int = Field(ge=0)


class TaskData(Contract):
    """task.data: a table of results to show. At most MAX_DATA_ROWS rows; use TaskData.capped() to truncate."""
    columns: list[str]
    rows: list[list[Cell]] = Field(default_factory=list, max_length=MAX_DATA_ROWS)
    source: str = Field(description='Where the rows came from, e.g. "db.query" or "/org/finance/apollo-budget"')

    @classmethod
    def capped(cls, columns: list[str], rows: list[list[Cell]], source: str) -> TaskData:
        return cls(columns=columns, rows=[list(r) for r in rows[:MAX_DATA_ROWS]], source=source)


NarrationPayload = TaskUnderstood | AgentPlanned | AgentThought
"""What an agent may emit through ctx.narrate(); the kernel emits the other thought-process events itself."""

NARRATION_EVENTS: dict[type[Contract], EventType] = {
    TaskUnderstood: EventType.TASK_UNDERSTOOD,
    AgentPlanned: EventType.AGENT_PLANNED,
    AgentThought: EventType.AGENT_THOUGHT,
}

THOUGHT_EVENT_MODELS: dict[EventType, type[Contract]] = {
    EventType.TASK_UNDERSTOOD: TaskUnderstood,
    EventType.AGENT_PLANNED: AgentPlanned,
    EventType.AGENT_CREATED: AgentCreated,
    EventType.AGENT_THOUGHT: AgentThought,
    EventType.TOOL_QUERY: ToolQuery,
    EventType.TASK_DATA: TaskData,
}
"""Payload model per thought-process event type: validate with THOUGHT_EVENT_MODELS[type].model_validate(payload)."""
