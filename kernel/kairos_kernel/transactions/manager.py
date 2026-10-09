"""Transactional actions: execute -> verify -> commit | rollback (blueprint §31)."""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from kairos_contracts.schema import (
    AuditKind,
    ErrorInfo,
    EventType,
    PolicyDecision,
    SyscallRequest,
    SyscallResult,
    SyscallStatus,
    ToolInvocation,
    ToolResult,
    ToolResultStatus,
)
from kairos_contracts.schema.common import new_id

from .queries import query_events

if TYPE_CHECKING:
    from ..kernel import Kernel

log = logging.getLogger("kairos.kernel.transactions")


class TransactionManager:
    def __init__(self, kernel: Kernel) -> None:
        self.k = kernel

    async def run(self, req: SyscallRequest, decision: PolicyDecision) -> SyscallResult:
        k, tools = self.k, self.k.services.require("tools")
        task_id, pid, sid = req.task_id, req.pid, req.syscall_id
        inv = ToolInvocation(invocation_id=new_id("INV"), syscall_id=sid, task_id=task_id, pid=pid, tool=req.tool,
                             operation=req.operation, arguments=req.arguments, arguments_ref=req.arguments_ref,
                             constraints=decision.constraints)
        await k.emit(EventType.TOOL_STARTED, {"tool": req.tool, "operation": req.operation}, task_id=task_id, pid=pid,
                     correlation_id=sid)
        started = time.monotonic()
        try:
            result = await tools.execute(inv)
        except Exception as e:  # executors shouldn't raise, but the kernel must survive if one does
            log.exception("tool executor raised")
            result = ToolResult(invocation_id=inv.invocation_id, status=ToolResultStatus.ERROR,
                                error=ErrorInfo(code="TOOL_FAILED", message=f"{type(e).__name__}: {e}", retriable=True))
        await k.emit(EventType.TOOL_COMPLETED, {"tool": req.tool, "operation": req.operation,
                                               "status": result.status.value}, task_id=task_id, pid=pid, correlation_id=sid)
        if result.status == ToolResultStatus.SUCCESS and (story := query_events(req, result, (time.monotonic() - started) * 1000)):
            for type_, payload in zip((EventType.TOOL_QUERY, EventType.TASK_DATA), story, strict=True):
                await k.emit(type_, payload.model_dump(mode="json"), task_id=task_id, pid=pid, correlation_id=sid)
        summary, data = f"{req.tool}.{req.operation} → {result.status.value}", {"arguments": req.arguments,
                                                                                "output": result.output}
        if result.error is not None:
            summary += f": {result.error.message}"
            data["error"] = {"code": result.error.code, "message": result.error.message}
        await k.journal(task_id, AuditKind.TOOL, summary, pid=pid, actor="kernel.syscall",
                        refs=[sid, inv.invocation_id, *result.artifacts], data=data)
        if result.status != ToolResultStatus.SUCCESS:
            return SyscallResult(syscall_id=sid, status=SyscallStatus.FAILED, decision=decision, tool_result=result,
                                 error=result.error or ErrorInfo(code="TOOL_FAILED", message="tool returned an error"))

        verification = await tools.verify(inv, result)
        await k.journal(task_id, AuditKind.VERIFY, "Post-condition passed" if verification.passed else "Post-condition FAILED",
                        pid=pid, actor="kernel.transactions", refs=[sid],
                        data={"checks": [c.model_dump(mode="json") for c in verification.checks]})
        if verification.passed:
            k.tasks.add_action(task_id, sid)
            await k.emit(EventType.TRANSACTION_COMMITTED, {"verified": True}, task_id=task_id, pid=pid, correlation_id=sid)
            await k.journal(task_id, AuditKind.COMMIT, f"Committed {sid}", pid=pid, actor="kernel.transactions", refs=[sid])
            return SyscallResult(syscall_id=sid, status=SyscallStatus.COMPLETED, decision=decision, tool_result=result,
                                 verified=True)

        rolled_back = await tools.rollback(inv, result)
        failed = [c.name for c in verification.checks if not c.passed]
        reason = f"post-condition failed: {', '.join(failed)}" + ("" if rolled_back else " (rollback not possible)")
        await k.emit(EventType.TRANSACTION_ROLLED_BACK, {"reason": reason}, task_id=task_id, pid=pid, correlation_id=sid)
        await k.journal(task_id, AuditKind.ROLLBACK, f"Rolled back {sid}", pid=pid, actor="kernel.transactions",
                        refs=[sid], data={"reason": reason, "rolled_back": rolled_back})
        return SyscallResult(syscall_id=sid, status=SyscallStatus.ROLLED_BACK, decision=decision, tool_result=result,
                             verified=False, error=ErrorInfo(code="TOOL_FAILED", message=reason))
