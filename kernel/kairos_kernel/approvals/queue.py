"""Human approval queue. A syscall waiting for approval awaits a Future that the API resolves."""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import Approval, ApprovalStatus, AuditKind, EventType
from kairos_contracts.schema.common import utcnow

if TYPE_CHECKING:
    from ..kernel import Kernel


class ApprovalQueue:
    def __init__(self, kernel: Kernel) -> None:
        self.k = kernel
        self._approvals: dict[str, Approval] = {}
        self._futures: dict[str, asyncio.Future[ApprovalStatus]] = {}
        self._last_decision: dict[str, float] = {}  # task_id -> monotonic time of the last human decision

    def load(self, approvals: list[Approval]) -> None:
        for a in approvals:
            self._approvals[a.approval_id] = a

    def get(self, approval_id: str) -> Approval:
        a = self._approvals.get(approval_id)
        if a is None:
            raise KairosError("APPROVAL_NOT_FOUND", approval_id)
        return a

    def list(self, status: ApprovalStatus | None = None, task_id: str | None = None) -> list[Approval]:
        return [a for a in sorted(self._approvals.values(), key=lambda a: a.requested_at)
                if (status is None or a.status == status) and (task_id is None or a.task_id == task_id)]

    def last_decision(self, task_id: str) -> float:
        return self._last_decision.get(task_id, 0.0)

    def _save(self, a: Approval) -> Approval:
        self._approvals[a.approval_id] = a
        self.k.store.put_approval(a)
        return a

    async def create(self, approval: Approval) -> asyncio.Future[ApprovalStatus]:
        self._save(approval)
        fut = asyncio.get_running_loop().create_future()
        self._futures[approval.approval_id] = fut
        await self.k.emit(EventType.APPROVAL_REQUESTED,
                          {"approval_id": approval.approval_id, "capability": approval.syscall.capability,
                           "tool": approval.syscall.tool, "operation": approval.syscall.operation,
                           "risk": approval.syscall.risk.value, "policy": approval.decision.policy},
                          task_id=approval.task_id, pid=approval.pid, correlation_id=approval.approval_id)
        return fut

    async def resolve(self, approval_id: str, approved: bool, by: str, comment: str | None = None) -> Approval:
        a = self.get(approval_id)
        if a.status != ApprovalStatus.PENDING:
            raise KairosError("APPROVAL_ALREADY_RESOLVED", f"{approval_id} is {a.status.value}")
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        self._last_decision[a.task_id] = time.monotonic()
        return await self._close(a, status, by, comment)

    async def expire(self, approval_id: str, reason: str = "expired") -> None:
        a = self._approvals.get(approval_id)
        if a is not None and a.status == ApprovalStatus.PENDING:
            await self._close(a, ApprovalStatus.EXPIRED, "kernel", reason)

    async def _close(self, a: Approval, status: ApprovalStatus, by: str, comment: str | None) -> Approval:
        a = self._save(a.model_copy(update={"status": status, "resolved_at": utcnow(), "resolved_by": by, "comment": comment}))
        fut = self._futures.pop(a.approval_id, None)
        if fut is not None and not fut.done():
            fut.set_result(status)
        await self.k.emit(EventType.APPROVAL_RESOLVED, {"approval_id": a.approval_id, "status": status.value,
                                                       "resolved_by": by, "comment": comment},
                          task_id=a.task_id, pid=a.pid, correlation_id=a.approval_id)
        actor = f"user:{by}" if by != "kernel" else "kernel.approvals"
        await self.k.journal(a.task_id, AuditKind.APPROVAL, f"{status.value.capitalize()} {a.approval_id}", pid=a.pid,
                             actor=actor, refs=[a.approval_id, a.syscall.syscall_id], data={"comment": comment})
        return a
