"""Agent processes: PID, lifecycle state machine, process tree, checkpoints."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from .common import (
    ArtifactRef,
    Capability,
    Contract,
    ErrorInfo,
    KnowledgePath,
    PathGlob,
    Pid,
    ResourceQuota,
    ResourceUsage,
    TaskId,
    utcnow,
)


class AgentState(StrEnum):
    CREATED = "CREATED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    PAUSED = "PAUSED"
    CHECKPOINTING = "CHECKPOINTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    TERMINATED = "TERMINATED"


S = AgentState
ALLOWED_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    S.CREATED: {S.INITIALIZING, S.TERMINATED},
    S.INITIALIZING: {S.READY, S.FAILED, S.TERMINATED},
    S.READY: {S.RUNNING, S.TERMINATED},
    S.RUNNING: {S.WAITING, S.PAUSED, S.CHECKPOINTING, S.COMPLETED, S.FAILED, S.TERMINATED},
    S.WAITING: {S.RUNNING, S.TERMINATED},
    S.PAUSED: {S.RUNNING, S.TERMINATED},
    S.CHECKPOINTING: {S.RUNNING, S.FAILED},
    S.FAILED: {S.RETRYING, S.TERMINATED},
    S.RETRYING: {S.RUNNING, S.TERMINATED},
    S.COMPLETED: set(),
    S.TERMINATED: set(),
}
"""Blueprint §10 state machine, plus `-> TERMINATED` from every live state so ai-kill always works.
The kernel MUST reject any transition not listed here; the UI may rely on it."""

TERMINAL_STATES = {S.COMPLETED, S.TERMINATED}


def can_transition(src: AgentState, dst: AgentState) -> bool:
    return dst in ALLOWED_TRANSITIONS[src]


class AgentProcess(Contract):
    pid: Pid
    ppid: Pid | None = None
    task_id: TaskId
    owner: str = Field(description="user_id the process acts on behalf of")
    agent: str = Field(description="Manifest name, e.g. finance-agent")
    agent_version: str = "0.1.0"
    state: AgentState = AgentState.CREATED
    goal: str = ""
    model: str | None = Field(None, description="Last model the router picked for this pid")
    memory_mounts: list[KnowledgePath] = Field(default_factory=list)
    capabilities: list[Capability] = Field(default_factory=list)
    quota: ResourceQuota = Field(default_factory=ResourceQuota)
    usage: ResourceUsage = Field(default_factory=ResourceUsage)
    workspace: str | None = Field(None, description="Host path of the ephemeral workspace")
    checkpoint_id: str | None = None
    attempt_count: int = 0
    last_error: ErrorInfo | None = None
    waiting_on: str | None = Field(None, description='e.g. "approval:APR-882", "pid:103", "ipc"')
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ProcessTreeNode(Contract):
    pid: Pid
    agent: str
    state: AgentState
    children: list[ProcessTreeNode] = Field(default_factory=list)


class SpawnRequest(Contract):
    """Body of POST /agents/spawn and the argument of AgentContext.spawn()."""

    agent: str
    goal: str
    task_id: TaskId
    ppid: Pid | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[Capability] | None = Field(
        None, description="Optional narrowing; can never exceed the child's manifest. The parent controls WHICH agents it may spawn (its manifest.capabilities.agents), not their capabilities"
    )
    scope: list[PathGlob] | None = Field(
        None, description="Optional narrowing of the child's /org scope (its template's memory mounts); never widens (0.11.0)"
    )
    why: str | None = Field(None, max_length=240, description="Why the parent creates this agent, for the audit and the UI")


class Checkpoint(Contract):
    checkpoint_id: str
    pid: Pid
    task_id: TaskId
    created_at: datetime = Field(default_factory=utcnow)
    agent_state: dict[str, Any] = Field(default_factory=dict, description="Opaque, from the agent")
    memory_refs: list[str] = Field(default_factory=list)
    artifact: ArtifactRef | None = None
