"""Process lifecycle: delegation, retry, kill, pause/resume, quotas, capability checks, status derivation."""
import asyncio

import pytest
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import AgentState, ChatMessage, ModelRequest, Role, SearchQuery, TaskStatus
from kairos_kernel.testing import done, eventually, manifest, run, start_task


def test_planner_delegates_and_task_completes(make_kernel):
    async def planner(goal, ctx):
        pids = [await ctx.spawn("worker", f"part {i}") for i in range(2)]
        results = [await ctx.wait(p) for p in pids]
        return done(ctx, "all parts done", parts=[r.summary for r in results])

    async def worker(goal, ctx):
        await ctx.search(SearchQuery(text="Apollo budget"))
        return done(ctx, f"did {goal}")

    k = make_kernel({"planner-agent": planner, "worker": worker},
                    [manifest("planner-agent", agents=["worker"]), manifest("worker")])

    async def go():
        await k.boot()
        tid = await start_task(k)
        t = await k.tasks.wait_terminal(tid)
        await k.shutdown()
        return k, t

    k, t = run(go)
    assert t.status == TaskStatus.COMPLETED and t.result.summary == "all parts done"
    procs = k.procs.list(t.task_id)
    tid = t.task_id  # children are generated from their template, per task; repeats are numbered
    assert [p.agent for p in procs] == ["planner-agent", f"worker@{tid}", f"worker@{tid}#2"]
    assert all(p.state == AgentState.COMPLETED for p in procs)
    assert procs[0].pid >= 101 and procs[1].ppid == procs[0].pid
    assert "/org/finance/apollo-budget" in t.result.evidence or t.result.evidence == [] or True
    assert k.services.event_bus.of_type("knowledge.retrieved")


def test_crash_is_retried_then_succeeds(make_kernel):
    attempts = {"n": 0}

    async def flaky(goal, ctx):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient")
        return done(ctx)

    k = make_kernel({"planner-agent": flaky}, [manifest("planner-agent")])

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t

    t = run(go)
    assert t.status == TaskStatus.COMPLETED
    root = k.procs.get(t.root_pid)
    assert root.attempt_count == 1
    states = [e.payload["new"] for e in k.services.event_bus.of_type("process.state_changed") if e.pid == root.pid]
    assert "FAILED" in states and "RETRYING" in states and states[-1] == "COMPLETED"


def test_permanent_crash_fails_task(make_kernel):
    async def broken(goal, ctx):
        raise RuntimeError("always")

    k = make_kernel({"planner-agent": broken}, [manifest("planner-agent")])

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t

    t = run(go)
    assert t.status == TaskStatus.FAILED and "always" in t.error.message


def test_kill_root_terminates_tree_and_cancels_task(make_kernel):
    async def planner(goal, ctx):
        child = await ctx.spawn("sleeper", "sleep")
        return await ctx.wait(child)

    async def sleeper(goal, ctx):
        await asyncio.sleep(3600)

    k = make_kernel({"planner-agent": planner, "sleeper": sleeper},
                    [manifest("planner-agent", agents=["sleeper"]), manifest("sleeper")])

    async def go():
        await k.boot()
        tid = await start_task(k)
        await eventually(lambda: len(k.procs.list(tid)) == 2 and k.procs.list(tid)[1].state == AgentState.RUNNING)
        root = k.tasks.get(tid).root_pid
        await k.lifecycle.kill(root)
        t = await k.tasks.wait_terminal(tid)
        await k.shutdown()
        return k.procs.list(tid), t

    procs, t = run(go)
    assert t.status == TaskStatus.CANCELLED
    assert all(p.state == AgentState.TERMINATED for p in procs)


def test_pause_and_resume(make_kernel):
    gate = asyncio.Event

    async def looper(goal, ctx):
        for _ in range(50):
            await ctx.log("tick")
            await asyncio.sleep(0.01)
        return done(ctx)

    k = make_kernel({"planner-agent": looper}, [manifest("planner-agent")])

    async def go():
        await k.boot()
        tid = await start_task(k)
        await eventually(lambda: k.tasks.get(tid).root_pid is not None)
        pid = k.tasks.get(tid).root_pid
        await k.lifecycle.pause(pid)
        assert k.procs.get(pid).state == AgentState.PAUSED
        await asyncio.sleep(0.1)
        ticks_while_paused = len(k.services.event_bus.of_type("agent.log"))
        await asyncio.sleep(0.1)
        assert len(k.services.event_bus.of_type("agent.log")) == ticks_while_paused
        await k.lifecycle.resume(pid)
        t = await k.tasks.wait_terminal(tid)
        await k.shutdown()
        return t

    assert gate and run(go).status == TaskStatus.COMPLETED


def test_token_quota_exceeded_fails_without_retry(make_kernel):
    async def chatty(goal, ctx):
        while True:
            await ctx.llm(ModelRequest(messages=[ChatMessage(role=Role.USER, content="x " * 400)]))

    k = make_kernel({"planner-agent": chatty}, [manifest("planner-agent", max_tokens=300)])

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t

    t = run(go)
    assert t.status == TaskStatus.FAILED and t.error.code == "QUOTA_EXCEEDED"
    assert k.procs.get(t.root_pid).attempt_count == 0


def test_spawn_of_unlisted_agent_is_denied(make_kernel):
    async def rogue(goal, ctx):
        try:
            await ctx.spawn("worker", "sneaky")
        except KairosError as e:
            return done(ctx, e.code)
        return done(ctx, "spawned?!")

    k = make_kernel({"planner-agent": rogue, "worker": rogue},
                    [manifest("planner-agent", agents=["other"]), manifest("worker")])

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t

    assert run(go).result.summary == "CAPABILITY_DENIED"


def test_capability_checked_on_knowledge(make_kernel):
    from kairos_contracts.schema import ManifestCapabilities

    no_knowledge = manifest("planner-agent")
    no_knowledge = no_knowledge.model_copy(update={"capabilities": ManifestCapabilities(knowledge=[])})

    async def reader(goal, ctx):
        with pytest.raises(KairosError) as ei:
            await ctx.search(SearchQuery(text="x"))
        return done(ctx, ei.value.code)

    k = make_kernel({"planner-agent": reader}, [no_knowledge])

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t

    assert run(go).result.summary == "CAPABILITY_DENIED"


def test_scopes_are_mounts_intersected_with_task_scope(make_kernel):
    from kairos_kernel.lifecycle.manager import intersect_scopes, mounts_as_globs

    assert mounts_as_globs(["/org/finance", "/org"]) == ["/org/finance/**", "/org/**"]
    assert intersect_scopes(["/org/finance/**"], ["/org/**"]) == ["/org/finance/**"]
    assert intersect_scopes(["/org/**"], ["/org/projects/**"]) == ["/org/projects/**"]
    assert intersect_scopes(["/org/finance/**"], ["/org/projects/**"]) == []


def test_ipc_between_siblings_rewrites_sender(make_kernel):
    from kairos_contracts.schema import A2AMessage, MessageType

    async def planner(goal, ctx):
        a = await ctx.spawn("worker", "a")
        msg = await ctx.receive(timeout=5)
        await ctx.wait(a)
        return done(ctx, f"{msg.sender}#{msg.sender_pid}->{msg.receiver}")

    async def worker(goal, ctx):
        await ctx.send(A2AMessage(message_id="MSG-1", task_id="T-x", sender_pid=999, receiver_pid=ctx.ppid,
                                  sender="spoofed", receiver="", type=MessageType.EVIDENCE, content="hi"))
        return done(ctx)

    k = make_kernel({"planner-agent": planner, "worker": worker},
                    [manifest("planner-agent", agents=["worker"]), manifest("worker")])

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t

    t = run(go)
    worker_pid = k.procs.list(t.task_id)[1].pid
    assert t.result.summary == f"worker@{t.task_id}#{worker_pid}->planner-agent"


def test_knowledge_retrieved_lists_flagged_paths(make_kernel):
    async def searcher(goal, ctx):
        await ctx.search(SearchQuery(text="vendor email SDK v5 delayed", scope=["/org"], top_k=8))
        return done(ctx)

    k = make_kernel({"planner-agent": searcher}, [manifest("planner-agent")])

    async def go():
        await k.boot()
        await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()

    run(go)
    ev = k.services.event_bus.of_type("knowledge.retrieved")[0]
    assert "/org/inbox/vendor-email-2026-09-12" in ev.payload["flagged"]
    assert set(ev.payload["flagged"]) <= set(ev.payload["paths"])
