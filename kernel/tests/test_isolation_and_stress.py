"""Isolation guarantees between agents/tasks, syscall idempotency, and a concurrency stress run."""
import asyncio

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    A2AMessage,
    AgentState,
    MessageType,
    Risk,
    SyscallRequest,
    SyscallStatus,
    TaskCreate,
    TaskStatus,
)
from kairos_contracts.schema.common import new_id
from kairos_contracts.testing.fakes import user_principal
from kairos_kernel.config import KernelConfig
from kairos_kernel.testing import done, manifest, run, start_task


def test_agents_cannot_cross_task_boundaries(make_kernel):
    seen: dict = {}
    first_pid: dict = {}

    async def planner(goal, ctx):
        if goal == "victim":
            first_pid["pid"] = ctx.pid
            first_pid["artifact"] = await ctx.put_artifact("secret.txt", "classified", "text/plain")
            await asyncio.sleep(0.3)
            return done(ctx)
        while "pid" not in first_pid:
            await asyncio.sleep(0.01)
        for name, attempt in {
            "message_other_task": lambda: ctx.send(A2AMessage(message_id="MSG-x", task_id=ctx.task_id, sender_pid=ctx.pid,
                                                              receiver_pid=first_pid["pid"], sender="", receiver="",
                                                              type=MessageType.REQUEST, content="hi")),
            "read_other_artifact": lambda: ctx.get_artifact(first_pid["artifact"]),
            "wait_on_non_child": lambda: ctx.wait(first_pid["pid"]),
        }.items():
            try:
                await attempt()
                seen[name] = "ALLOWED"
            except KairosError as e:
                seen[name] = e.code
        return done(ctx)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent")])

    async def go():
        await k.boot()
        a = await start_task(k, goal="victim")
        b = await start_task(k, goal="attacker")
        await k.tasks.wait_terminal(a)
        await k.tasks.wait_terminal(b)
        await k.shutdown()

    run(go)
    assert seen == {"message_other_task": "CAPABILITY_DENIED", "read_other_artifact": "CAPABILITY_DENIED",
                    "wait_on_non_child": "PROCESS_NOT_FOUND"}


def test_syscall_ids_are_bound_to_the_calling_process(make_kernel):
    """An agent cannot forge task_id/pid on a syscall: the kernel overwrites them."""
    results = []

    async def planner(goal, ctx):
        res = await ctx.syscall(SyscallRequest(syscall_id=new_id("SC"), task_id="T-someoneelse", pid=1,
                                               capability="jira.read", tool="jira", operation="get_issue",
                                               arguments={"key": "APOLLO-12"}))
        results.append(res)
        return done(ctx)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent", tools=["jira.read"])])

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await start_task(k))
        tl = await k.audit.timeline(t.task_id)
        await k.shutdown()
        return t, tl

    t, tl = run(go)
    assert results[0].status == SyscallStatus.COMPLETED
    tool_entries = [e for e in tl.entries if e.kind.value == "tool"]
    assert tool_entries and tool_entries[0].task_id == t.task_id and tool_entries[0].pid == t.root_pid


def test_idempotent_syscall_executes_once(make_kernel):
    results = []

    async def planner(goal, ctx):
        for _ in range(2):
            results.append(await ctx.syscall(SyscallRequest(
                syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid, capability="jira.write", tool="jira",
                operation="update_issue", risk=Risk.MEDIUM, idempotency_key="apollo-12-at-risk",
                arguments={"key": "APOLLO-12", "comment": "once"})))
        return done(ctx)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent", tools=["jira.write"])])

    async def go():
        await k.boot()

        async def approve(ev):
            await k.approvals.resolve(ev.payload["approval_id"], True, "alice")

        k.bus.subscribe("approval.requested", approve)
        await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()

    run(go)
    assert results[0].status == results[1].status == SyscallStatus.COMPLETED
    assert results[1].syscall_id == results[0].syscall_id, "second call returned the stored result"
    assert k.services.tools.issues["APOLLO-12"]["comments"] == ["once"]
    assert len(k.approvals.list()) == 1


def test_stress_many_tasks_many_agents(make_kernel):
    async def planner(goal, ctx):
        pids = [await ctx.spawn("worker", f"{goal}/{i}") for i in range(3)]
        results = await asyncio.gather(*(ctx.wait(p) for p in pids))
        return done(ctx, ",".join(r.summary for r in results))

    async def worker(goal, ctx):
        await ctx.log(goal)
        await asyncio.sleep(0.01)
        return done(ctx, goal.rsplit("/", 1)[1])

    k = make_kernel({"planner-agent": planner, "worker": worker},
                    [manifest("planner-agent", agents=["worker"]), manifest("worker")],
                    config=KernelConfig(max_concurrent_tasks=4, policy_watch_interval_s=0))

    async def go():
        await k.boot()
        ids = [(await k.tasks.create(TaskCreate(goal=f"t{i}", metadata={"root_agent": "planner-agent"}),
                                     user_principal())).task_id for i in range(20)]
        tasks = [await k.tasks.wait_terminal(t, timeout=60) for t in ids]
        chains = [k.audit.verify_chain(t) for t in ids] if hasattr(k.audit, "verify_chain") else []
        await k.shutdown()
        return tasks, chains

    tasks, _ = run(go, timeout=90)
    assert all(t.status == TaskStatus.COMPLETED for t in tasks)
    assert all(sorted(t.result.summary.split(",")) == ["0", "1", "2"] for t in tasks)
    procs = k.procs.list()
    assert len(procs) == 80 and len({p.pid for p in procs}) == 80, "unique PIDs"
    assert all(p.state == AgentState.COMPLETED for p in procs)


def test_audit_chain_holds_under_concurrency(tmp_path):
    from kairos_contracts.testing.fakes import FakeAgentRegistry, fake_bundle
    from kairos_contracts.wiring import Settings
    from kairos_kernel.audit.log import SqliteAuditLog
    from kairos_kernel.kernel import Kernel
    from kairos_kernel.testing import ScriptedRuntime

    async def planner(goal, ctx):
        for i in range(10):
            await ctx.log(f"{i}")
            await ctx.checkpoint({"i": i})
        return done(ctx)

    settings = Settings(data_dir=tmp_path)
    bundle = fake_bundle(settings)
    bundle.audit = SqliteAuditLog(tmp_path / "audit.db")
    bundle.agent_runtime = ScriptedRuntime({"planner-agent": planner})
    bundle.agent_registry = FakeAgentRegistry(manifests=[manifest("planner-agent")])
    k = Kernel(settings, bundle, KernelConfig(max_concurrent_tasks=8, policy_watch_interval_s=0))

    async def go():
        await k.boot()
        ids = [await start_task(k, goal=f"g{i}") for i in range(8)]
        for t in ids:
            await k.tasks.wait_terminal(t)
        await k.shutdown()
        return ids

    ids = run(go)
    assert all(bundle.audit.verify_chain(t) for t in ids)
