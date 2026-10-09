"""AI syscall gateway: validate -> policy -> (human approval) -> transaction (blueprint §25, §31, §35)."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from kairos_contracts.schema import (
    Approval,
    ApprovalStatus,
    AuditKind,
    Decision,
    EventType,
    PolicyDecision,
    SyscallRequest,
    SyscallResult,
    SyscallStatus,
    ToolOperation,
)
from kairos_contracts.schema.common import new_id

from ..policy.engine import max_risk
from .sql_guard import check_sql

if TYPE_CHECKING:
    from ..context.agent_context import KernelAgentContext
    from ..kernel import Kernel

log = logging.getLogger("kairos.kernel.syscalls")

APPROVAL_TIMEOUT_S = 1800.0


class SyscallGateway:
    def __init__(self, kernel: Kernel, approval_timeout: float = APPROVAL_TIMEOUT_S) -> None:
        self.k = kernel
        self.approval_timeout = approval_timeout
        self._ops: dict[tuple[str, str], ToolOperation] | None = None

    async def operation(self, tool: str, operation: str) -> ToolOperation | None:
        if self._ops is None or (tool, operation) not in self._ops:
            specs = await self.k.services.require("tools").list_tools()
            self._ops = {(s.name, o.name): o for s in specs for o in s.operations}
        return self._ops.get((tool, operation))

    async def handle(self, req: SyscallRequest, ctx: KernelAgentContext) -> SyscallResult:
        k, task_id, pid = self.k, req.task_id, req.pid
        await k.emit(EventType.SYSCALL_REQUESTED, {"capability": req.capability, "tool": req.tool,
                                                  "operation": req.operation, "risk": req.risk.value},
                     task_id=task_id, pid=pid, correlation_id=req.syscall_id)
        await k.journal(task_id, AuditKind.SYSCALL, f"{req.capability} {req.tool}.{req.operation}", pid=pid,
                        actor=k.actor(pid), refs=[req.syscall_id, *req.evidence],
                        data={"resource": req.resource, "risk": req.risk.value, "justification": req.justification,
                              "arguments": req.arguments})
        if req.idempotency_key and (previous := k.store.idempotent(req.idempotency_key)) is not None:
            return previous

        op = await self.operation(req.tool, req.operation)
        if op is None:
            decision = PolicyDecision(decision=Decision.DENY, policy="kernel", matched_rules=["tool-registry"],
                                      reason=f"unknown tool operation {req.tool}.{req.operation}")
        elif op.capability != req.capability:
            decision = PolicyDecision(decision=Decision.DENY, policy="kernel", matched_rules=["capability-mismatch"],
                                      reason=f"{req.tool}.{req.operation} requires {op.capability}, not {req.capability}")
        elif req.tool == "db" and req.operation in ("query", "write") and not (sql := check_sql(req.operation,
                                                                                    str(req.arguments.get("sql", "")))).ok:
            decision = PolicyDecision(decision=Decision.DENY, policy="kernel.sql", matched_rules=["sql-guard"], reason=sql.reason)
        else:
            if req.tool == "db" and req.operation in ("query", "write"):  # the statement that runs is the checked one
                req = req.model_copy(update={"arguments": {**req.arguments, "sql": sql.sql}})
            req = req.model_copy(update={"risk": max_risk(req.risk, op.risk)})
            decision = await k.services.require("policy").evaluate(req, ctx.principal)

        await k.emit(EventType.SYSCALL_DECIDED, {"decision": decision.decision.value, "policy": decision.policy,
                                                "reason": decision.reason},
                     task_id=task_id, pid=pid, correlation_id=req.syscall_id)
        await k.journal(task_id, AuditKind.POLICY, f"{req.capability}: {decision.decision.value} ({decision.reason})",
                        pid=pid, actor="kernel.policy", refs=[req.syscall_id],
                        data={"decision": decision.decision.value, "policy": decision.policy,
                              "rules": decision.matched_rules})

        if decision.decision == Decision.DENY:
            result = SyscallResult(syscall_id=req.syscall_id, status=SyscallStatus.DENIED, decision=decision)
        elif decision.decision == Decision.REQUIRES_APPROVAL and not await self._approved(req, decision, ctx):
            result = SyscallResult(syscall_id=req.syscall_id, status=SyscallStatus.REJECTED, decision=decision)
        else:
            await k.quotas.charge_tool_call(pid)
            result = await k.transactions.run(req, decision)

        await k.emit(EventType.SYSCALL_COMPLETED, {"status": result.status.value}, task_id=task_id, pid=pid,
                     correlation_id=req.syscall_id)
        if req.idempotency_key and result.status == SyscallStatus.COMPLETED:
            k.store.put_idempotent(req.idempotency_key, result)
        return result

    async def _approved(self, req: SyscallRequest, decision: PolicyDecision, ctx: KernelAgentContext) -> bool:
        approval = Approval(approval_id=decision.approval_id or new_id("APR"), task_id=req.task_id, pid=req.pid,
                            agent=ctx.manifest.name, syscall=req, decision=decision)
        fut = await self.k.approvals.create(approval)
        try:
            async with ctx.waiting(f"approval:{approval.approval_id}"):
                status = await self._wait_for_decision(fut, req.task_id)
        except TimeoutError:
            await self.k.approvals.expire(approval.approval_id, "approval timed out")
            return False
        except asyncio.CancelledError:
            await self.k.approvals.expire(approval.approval_id, "process terminated")
            raise
        return status == ApprovalStatus.APPROVED

    async def _wait_for_decision(self, fut: asyncio.Future[ApprovalStatus], task_id: str) -> ApprovalStatus:
        # Parallel approvals of one task are decided one after another; each decision restarts the others' clocks,
        # so the last card in the queue doesn't expire while the human is still working through the earlier ones.
        deadline = time.monotonic() + self.approval_timeout
        while True:
            deadline = max(deadline, self.k.approvals.last_decision(task_id) + self.approval_timeout)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            try:
                return await asyncio.wait_for(asyncio.shield(fut), remaining)
            except TimeoutError:
                continue
