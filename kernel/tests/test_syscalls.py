"""Syscall path: policy decisions, approvals, transactions (commit / rollback), unknown tools."""
from kairos_contracts.schema import (
    ApprovalStatus,
    Risk,
    SyscallRequest,
    SyscallStatus,
    TaskStatus,
    ToolResult,
    VerificationResult,
)
from kairos_contracts.schema.common import new_id
from kairos_contracts.testing.fakes import FakeToolExecutor
from kairos_kernel.testing import done, manifest, run, start_task


def update_issue(ctx, **fields) -> SyscallRequest:
    return SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid, capability="jira.write",
                          tool="jira", operation="update_issue", risk=Risk.MEDIUM,
                          arguments={"key": "APOLLO-12", "fields": fields or {"status": "At Risk"}})


def actor_script(results: list):
    async def actor(goal, ctx):
        res = await ctx.syscall(update_issue(ctx))
        results.append(res)
        return done(ctx, res.status.value)

    return actor


def _kernel(make_kernel, results, **overrides):
    return make_kernel({"planner-agent": actor_script(results)},
                       [manifest("planner-agent", tools=["jira.read", "jira.write"])], **overrides)


def _auto_resolve(k, approve: bool):
    async def handler(ev):
        await k.approvals.resolve(ev.payload["approval_id"], approve, "alice", "test")

    k.bus.subscribe("approval.requested", handler)


def test_approved_syscall_commits(make_kernel):
    results: list = []
    k = _kernel(make_kernel, results)

    async def go():
        await k.boot()
        _auto_resolve(k, True)
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t

    t = run(go)
    assert results[0].status == SyscallStatus.COMPLETED and results[0].verified
    assert k.services.tools.issues["APOLLO-12"]["status"] == "At Risk"
    assert t.result.actions == [results[0].syscall_id]
    types = [e.type for e in k.services.event_bus.history if e.task_id == t.task_id]
    order = ["syscall.requested", "syscall.decided", "approval.requested", "approval.resolved", "tool.started",
             "tool.completed", "transaction.committed", "syscall.completed"]
    assert [x for x in types if x in order] == order
    assert k.approvals.list()[0].status == ApprovalStatus.APPROVED


def test_rejected_syscall_does_not_execute(make_kernel):
    results: list = []
    k = _kernel(make_kernel, results)

    async def go():
        await k.boot()
        _auto_resolve(k, False)
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t

    t = run(go)
    assert results[0].status == SyscallStatus.REJECTED
    assert k.services.tools.issues["APOLLO-12"]["status"] == "In Progress"
    assert t.status == TaskStatus.COMPLETED and t.result.actions == []


def test_waiting_for_approval_is_visible_in_task_status(make_kernel):
    results: list = []
    k = _kernel(make_kernel, results)
    seen: list = []

    async def go():
        await k.boot()

        async def on_request(ev):
            seen.append(ev.payload["approval_id"])

        k.bus.subscribe("approval.requested", on_request)
        tid = await start_task(k)
        from kairos_kernel.testing import eventually

        await eventually(lambda: k.tasks.get(tid).status == TaskStatus.WAITING_APPROVAL)
        proc = k.procs.get(k.tasks.get(tid).root_pid)
        assert proc.waiting_on == f"approval:{seen[0]}"
        await k.approvals.resolve(seen[0], True, "alice")
        t = await k.tasks.wait_terminal(tid)
        await k.shutdown()
        return t

    assert run(go).status == TaskStatus.COMPLETED


def test_parallel_approvals_do_not_expire_while_a_human_works_through_them(make_kernel):
    """Three approvals arrive at once; a human decides one every 0.6 s. With a 1 s timeout, the third would expire
    at 1 s if each clock ran from its request; a decision in the same task restarts the others' clocks."""
    import asyncio

    from kairos_kernel.config import KernelConfig

    results: list = []

    async def actor(goal, ctx):
        results.extend(await asyncio.gather(*(ctx.syscall(update_issue(ctx)) for _ in range(3))))
        return done(ctx)

    k = make_kernel({"planner-agent": actor}, [manifest("planner-agent", tools=["jira.read", "jira.write"])],
                    config=KernelConfig(policy_watch_interval_s=0, approval_timeout_s=1.0))

    async def go():
        await k.boot()
        tid = await start_task(k)
        from kairos_kernel.testing import eventually

        await eventually(lambda: len(k.approvals.list(ApprovalStatus.PENDING)) == 3)
        for a in k.approvals.list(ApprovalStatus.PENDING):
            await asyncio.sleep(0.6)
            await k.approvals.resolve(a.approval_id, True, "alice")
        await k.tasks.wait_terminal(tid)
        await k.shutdown()

    run(go)
    assert [r.status for r in results] == [SyscallStatus.COMPLETED] * 3


def test_unanswered_approval_still_expires(make_kernel):
    from kairos_kernel.config import KernelConfig

    results: list = []
    k = _kernel(make_kernel, results, config=KernelConfig(policy_watch_interval_s=0, approval_timeout_s=0.3))

    async def go():
        await k.boot()
        await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()

    run(go)
    assert results[0].status == SyscallStatus.REJECTED
    assert k.approvals.list()[0].status == ApprovalStatus.EXPIRED


class _ErroringTool(FakeToolExecutor):
    async def execute(self, invocation) -> ToolResult:
        from kairos_contracts.schema import ErrorInfo, ToolResultStatus

        return ToolResult(invocation_id=invocation.invocation_id, status=ToolResultStatus.ERROR,
                          error=ErrorInfo(code="TOOL_FAILED", message="jira answered 503: maintenance window"))


def test_tool_error_message_reaches_the_audit(make_kernel):
    results: list = []
    k = _kernel(make_kernel, results, tools=_ErroringTool())

    async def go():
        await k.boot()
        _auto_resolve(k, True)
        t = await k.tasks.wait_terminal(await start_task(k))
        tl = await k.audit.timeline(t.task_id)
        await k.shutdown()
        return tl

    tl = run(go)
    assert results[0].status == SyscallStatus.FAILED
    tool = [e for e in tl.entries if e.kind.value == "tool"][0]
    assert "maintenance window" in tool.summary
    assert tool.data["error"] == {"code": "TOOL_FAILED", "message": "jira answered 503: maintenance window"}


class _FailingVerify(FakeToolExecutor):
    async def verify(self, invocation, result: ToolResult) -> VerificationResult:
        return VerificationResult(invocation_id=invocation.invocation_id, passed=False)


def test_failed_verification_rolls_back(make_kernel):
    results: list = []
    tools = _FailingVerify()
    k = _kernel(make_kernel, results, tools=tools)

    async def go():
        await k.boot()
        _auto_resolve(k, True)
        await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()

    run(go)
    assert results[0].status == SyscallStatus.ROLLED_BACK
    assert tools.issues["APOLLO-12"]["status"] == "In Progress", "rollback restored the issue"
    assert k.services.event_bus.of_type("transaction.rolled_back")


def test_unknown_tool_and_capability_mismatch_are_denied(make_kernel):
    results: list = []

    async def actor(goal, ctx):
        bad_tool = SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid, capability="jira.write",
                                  tool="jira", operation="drop_project")
        mismatch = SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid, capability="jira.read",
                                  tool="jira", operation="update_issue", arguments={"key": "APOLLO-12"})
        results.extend([await ctx.syscall(bad_tool), await ctx.syscall(mismatch)])
        return done(ctx)

    k = make_kernel({"planner-agent": actor}, [manifest("planner-agent", tools=["jira.read", "jira.write"])])

    async def go():
        await k.boot()
        await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()

    run(go)
    assert [r.status for r in results] == [SyscallStatus.DENIED, SyscallStatus.DENIED]
    assert "unknown tool" in results[0].decision.reason and "requires jira.write" in results[1].decision.reason


def test_audit_timeline_covers_the_whole_syscall(make_kernel):
    results: list = []
    k = _kernel(make_kernel, results)

    async def go():
        await k.boot()
        _auto_resolve(k, True)
        t = await k.tasks.wait_terminal(await start_task(k))
        tl = await k.audit.timeline(t.task_id)
        await k.shutdown()
        return tl

    tl = run(go)
    kinds = {e.kind.value for e in tl.entries}
    assert {"task", "spawn", "syscall", "policy", "approval", "tool", "verify", "commit"} <= kinds
    assert tl.stats.approvals == 1 and tl.stats.tool_calls == 1 and tl.goal == "test goal"
