"""AI syscalls, policy decisions and approvals — the governed boundary between agents and the world."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from .common import ArtifactRef, Capability, Contract, ErrorInfo, Pid, Risk, TaskId, utcnow
from .tools import ToolResult


class SyscallStatus(StrEnum):
    COMPLETED = "completed"
    DENIED = "denied"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class SyscallRequest(Contract):
    """What an agent asks the kernel to do to the outside world (blueprint §35).

    `capability` is what policy checks; `tool` + `operation` is what the executor runs.
    """

    syscall_id: str = Field(description='"SC-..." — assigned by the caller via new_id("SC")')
    task_id: TaskId
    pid: Pid
    capability: Capability = Field(description="e.g. jira.write")
    tool: str = Field(description="Tool name from ToolExecutor.list_tools(), e.g. jira")
    operation: str = Field(description="Operation on that tool, e.g. update_issue")
    resource: str | None = Field(None, description="What is touched, e.g. project/APOLLO")
    arguments: dict[str, Any] = Field(default_factory=dict)
    arguments_ref: ArtifactRef | None = None
    risk: Risk = Risk.LOW
    justification: str = ""
    evidence: list[str] = Field(default_factory=list, description="/org paths supporting the action")
    idempotency_key: str | None = None


class Decision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


class PolicyDecision(Contract):
    decision: Decision
    policy: str = Field(description="Id of the policy document that decided")
    reason: str
    approval_id: str | None = None
    matched_rules: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(
        default_factory=dict, description='Extra limits for the executor, e.g. {"network_allow": [...]}'
    )


class SyscallResult(Contract):
    syscall_id: str
    status: SyscallStatus
    decision: PolicyDecision
    tool_result: ToolResult | None = None
    verified: bool | None = None
    error: ErrorInfo | None = None


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Approval(Contract):
    approval_id: str = Field(description='"APR-..."')
    task_id: TaskId
    pid: Pid
    agent: str
    syscall: SyscallRequest
    decision: PolicyDecision
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    comment: str | None = None


class ApprovalResolution(Contract):
    """Body of POST /approvals/{id}/approve|reject."""

    comment: str | None = None
