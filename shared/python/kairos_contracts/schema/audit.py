"""Audit journal / provenance timeline (blueprint §33)."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from .common import Contract, Pid, TaskId, utcnow


class AuditKind(StrEnum):
    TASK = "task"
    SPAWN = "spawn"
    STATE = "state"
    MODEL = "model"
    KNOWLEDGE = "knowledge"
    MEMORY = "memory"
    IPC = "ipc"
    SYSCALL = "syscall"
    POLICY = "policy"
    APPROVAL = "approval"
    TOOL = "tool"
    VERIFY = "verify"
    COMMIT = "commit"
    ROLLBACK = "rollback"


class AuditEntry(Contract):
    seq: int = Field(0, description="Monotonic per task; assigned by the AuditLog")
    entry_id: str
    ts: datetime = Field(default_factory=utcnow)
    task_id: TaskId
    pid: Pid | None = None
    actor: str = Field(description='"user:alice", "agent:finance-agent#102", "kernel.policy"')
    kind: AuditKind
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    refs: list[str] = Field(default_factory=list, description="/org paths, artifact refs, syscall/approval ids")
    prev_hash: str | None = Field(None, description="Hash chain for tamper evidence (stretch)")
    hash: str | None = None


class TimelineStats(Contract):
    agents: int = 0
    models: list[str] = Field(default_factory=list)
    knowledge_objects: int = 0
    ipc_messages: int = 0
    tool_calls: int = 0
    privileged_syscalls: int = 0
    approvals: int = 0
    rollbacks: int = 0


class RunTimeline(Contract):
    task_id: TaskId
    goal: str
    entries: list[AuditEntry]
    stats: TimelineStats = Field(default_factory=TimelineStats)
    chain_verified: bool | None = Field(
        None,
        description="True when the audit log recomputed every entry's hash and each prev_hash links to its predecessor; "
        "False when that check fails; None when the log keeps no hash chain",
    )
