"""Scheduler: concurrency limits, priority order, preemption, queue cancellation."""
import asyncio

from kairos_contracts.schema import AgentState, Priority, TaskCreate, TaskStatus
from kairos_contracts.testing.fakes import user_principal
from kairos_kernel.config import KernelConfig
from kairos_kernel.testing import done, eventually, manifest, run


async def create(k, goal, priority=Priority.NORMAL):
    t = await k.tasks.create(TaskCreate(goal=goal, priority=priority, metadata={"root_agent": "planner-agent"}),
                             user_principal())
    return t.task_id


def test_concurrency_limit_and_all_tasks_finish(make_kernel):
    live, peak = {"n": 0}, {"n": 0}

    async def agent(goal, ctx):
        live["n"] += 1
        peak["n"] = max(peak["n"], live["n"])
        await ctx.log(goal)
        await asyncio.sleep(0.05)
        live["n"] -= 1
        return done(ctx, goal)

    k = make_kernel({"planner-agent": agent}, [manifest("planner-agent")],
                    config=KernelConfig(max_concurrent_tasks=2, policy_watch_interval_s=0))

    async def go():
        await k.boot()
        ids = [await create(k, f"task {i}") for i in range(6)]
        results = [await k.tasks.wait_terminal(t) for t in ids]
        await k.shutdown()
        return results

    results = run(go)
    assert all(t.status == TaskStatus.COMPLETED for t in results)
    assert peak["n"] == 2, "never more than max_concurrent_tasks roots at once"


def test_high_priority_jumps_the_queue(make_kernel):
    order = []

    async def agent(goal, ctx):
        order.append(goal)
        await asyncio.sleep(0.05)
        return done(ctx)

    k = make_kernel({"planner-agent": agent}, [manifest("planner-agent")],
                    config=KernelConfig(max_concurrent_tasks=1, preemption=False, policy_watch_interval_s=0))

    async def go():
        await k.boot()
        first = await create(k, "first")
        await eventually(lambda: order == ["first"])
        normal = await create(k, "normal")
        high = await create(k, "high", Priority.HIGH)
        for t in (first, normal, high):
            await k.tasks.wait_terminal(t)
        await k.shutdown()

    run(go)
    assert order == ["first", "high", "normal"]


def test_high_priority_preempts_background(make_kernel):
    finished = []

    async def agent(goal, ctx):
        steps = 60 if goal == "background" else 2
        for _ in range(steps):
            await ctx.log(f"{goal} step")
            await asyncio.sleep(0.01)
        finished.append(goal)
        return done(ctx, goal)

    k = make_kernel({"planner-agent": agent}, [manifest("planner-agent")],
                    config=KernelConfig(max_concurrent_tasks=1, policy_watch_interval_s=0))

    async def go():
        await k.boot()
        bg = await create(k, "background", Priority.BACKGROUND)
        await eventually(lambda: k.tasks.get(bg).root_pid is not None)
        await asyncio.sleep(0.05)
        hi = await create(k, "urgent", Priority.HIGH)
        await eventually(lambda: k.procs.get(k.tasks.get(bg).root_pid).state == AgentState.PAUSED)
        hi_t = await k.tasks.wait_terminal(hi)
        bg_t = await k.tasks.wait_terminal(bg)
        tl = await k.audit.timeline(bg)
        await k.shutdown()
        return hi_t, bg_t, tl

    hi_t, bg_t, tl = run(go)
    assert finished == ["urgent", "background"], "urgent finished while background was paused"
    assert hi_t.status == bg_t.status == TaskStatus.COMPLETED
    summaries = [e.summary for e in tl.entries]
    assert any(s.startswith("Preempted by high-priority task") for s in summaries)
    assert "Resumed after preemption" in summaries


def test_cancel_while_queued_never_starts(make_kernel):
    started = []

    async def agent(goal, ctx):
        started.append(goal)
        await asyncio.sleep(0.1)
        return done(ctx)

    k = make_kernel({"planner-agent": agent}, [manifest("planner-agent")],
                    config=KernelConfig(max_concurrent_tasks=1, policy_watch_interval_s=0))

    async def go():
        await k.boot()
        a = await create(k, "a")
        b = await create(k, "b")
        await k.tasks.cancel(b)
        await k.tasks.wait_terminal(a)
        await asyncio.sleep(0.1)
        await k.shutdown()
        return k.tasks.get(b)

    b = run(go)
    assert b.status == TaskStatus.CANCELLED and started == ["a"]
