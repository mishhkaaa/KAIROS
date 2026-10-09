"""ctx.narrate (contract 0.10.0): the real context satisfies AgentContext and publishes the three agent-told events."""
import pytest
from kairos_contracts.errors import KairosError
from kairos_contracts.interfaces.kernel import AgentContext
from kairos_contracts.schema import AgentPlanned, AgentThought, TaskStatus, TaskUnderstood, ToolQuery
from kairos_kernel.testing import done, manifest, run, start_task


def test_the_real_context_satisfies_the_agent_context_protocol(make_kernel):
    seen = {}

    async def planner(goal, ctx):
        seen["ctx"] = ctx
        return done(ctx)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent")])

    async def go():
        await k.boot()
        await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()

    run(go)
    assert isinstance(seen["ctx"], AgentContext)  # runtime_checkable: every protocol member, narrate included


def test_narrate_publishes_the_story_with_the_kernels_pid(make_kernel):
    errors = []

    async def planner(goal, ctx):
        await ctx.narrate(TaskUnderstood(intent="investigate", entities=["Project Apollo"], plan_summary="two agents"))
        await ctx.narrate(AgentPlanned(role="finance-agent", why="budget", scope=["/org/finance"]))
        await ctx.narrate(AgentThought(pid=999, step="plan", text="Planning 2 steps."))
        with pytest.raises(KairosError) as e:  # tool.query is the kernel's to emit
            await ctx.narrate(ToolQuery(pid=ctx.pid, tool="db.query", query="select 1", rows=1, ms=1))
        errors.append(e.value.code)
        return done(ctx)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent")])

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t

    t = run(go)
    assert t.status == TaskStatus.COMPLETED and errors == ["BAD_REQUEST"]
    understood, planned, thought = (k.bus.of_type(x) for x in ("task.understood", "agent.planned", "agent.thought"))
    assert understood[0].payload["entities"] == ["Project Apollo"] and understood[0].task_id == t.task_id
    assert planned[0].payload == {"role": "finance-agent", "why": "budget", "scope": ["/org/finance"], "capabilities": [], "score": None}
    pid = understood[0].pid
    assert thought[0].pid == pid and thought[0].payload["pid"] == pid != 999  # an agent cannot speak for another pid
    assert not k.bus.of_type("tool.query")


def test_a_spawn_scope_only_narrows(make_kernel):
    from kairos_contracts.schema import AgentManifest, ManifestMemory

    seen = {}

    async def planner(goal, ctx):
        seen["pid"] = await ctx.spawn("finance-agent", "budget", scope=["/org/finance/**", "/org/hr/**"], why="budget")
        await ctx.wait(seen["pid"])
        return done(ctx)

    async def finance(goal, ctx):
        seen["scopes"] = list(ctx.principal.data_scopes)
        return done(ctx)

    fin = manifest("finance-agent").model_copy(update={"memory": ManifestMemory(mounts=["/org/finance", "/org/projects"])})
    k = make_kernel({"planner-agent": planner, "finance-agent": finance},
                    [manifest("planner-agent", agents=["finance-agent"]), AgentManifest.model_validate(fin.model_dump())])

    async def go():
        await k.boot()
        await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()

    run(go)
    assert seen["scopes"] == ["/org/finance/**"]  # /org/projects dropped by the request, /org/hr never granted
