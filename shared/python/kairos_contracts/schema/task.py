"""Tasks: the unit of work a user submits. One task == one run (task_id doubles as run id)."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from .common import (
    ArtifactRef,
    Contract,
    ErrorInfo,
    PathGlob,
    Pid,
    Priority,
    PrivacyLevel,
    ResourceQuota,
    ResourceUsage,
    TaskId,
    utcnow,
)


class TaskStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_TASK_STATUSES = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}


class TaskCreate(Contract):
    """Body of POST /tasks. org_id/user_id come from the auth headers, not the body."""

    goal: str = Field(min_length=1)
    session_id: str | None = None
    priority: Priority = Priority.NORMAL
    privacy: PrivacyLevel = PrivacyLevel.INTERNAL
    data_scope: list[PathGlob] = Field(default_factory=lambda: ["/org/**"])
    approval_policy: str = "default"
    quota: ResourceQuota | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskResult(Contract):
    summary: str = Field(description="Markdown answer shown to the user")
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list, description="/org paths used")
    actions: list[str] = Field(default_factory=list, description="syscall_ids committed")
    usage: ResourceUsage = Field(default_factory=ResourceUsage)


class Task(Contract):
    task_id: TaskId
    org_id: str
    user_id: str
    session_id: str | None = None
    goal: str
    priority: Priority = Priority.NORMAL
    privacy: PrivacyLevel = PrivacyLevel.INTERNAL
    data_scope: list[PathGlob] = Field(default_factory=lambda: ["/org/**"])
    approval_policy: str = "default"
    quota: ResourceQuota = Field(default_factory=ResourceQuota)
    status: TaskStatus = TaskStatus.QUEUED
    root_pid: Pid | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    result: TaskResult | None = None
    error: ErrorInfo | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
