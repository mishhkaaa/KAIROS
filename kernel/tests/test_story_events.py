"""The kernel's part of the thought-process story (0.10.0): agent.created on spawn, tool.query + task.data after a query."""
from kairos_contracts.schema import AgentCreated, Risk, SyscallRequest, TaskData, TaskStatus, ToolQuery
from kairos_contracts.schema.common import new_id
from kairos_kernel.testing import done, manifest, run, start_task


def _syscall(ctx, capability: str, tool: str, operation: str, **arguments) -> SyscallRequest:
    return SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid, capability=capability, tool=tool,
                          operation=operation, arguments=arguments, risk=Risk.LOW, justification="test")


def test_agents_a_planner_creates_are_announced_after_their_spawn(make_kernel):
    async def planner(goal, ctx):
        await ctx.wait(await ctx.spawn("finance-agent", "budget"))
        return done(ctx)

    async def finance(goal, ctx):
        return done(ctx)

    k = make_kernel({"planner-agent": planner, "finance-agent": finance},
                    [manifest("planner-agent", agents=["finance-agent"]), manifest("finance-agent")])

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t

    t = run(go)
    assert t.status == TaskStatus.COMPLETED
    created = k.bus.of_type("agent.created")
    assert len(created) == 1  # the root planner is the task itself, not a created agent
    c = AgentCreated.model_validate(created[0].payload)
    spawned = next(e for e in k.bus.of_type("process.spawned") if e.payload["ppid"] is not None)
    assert (c.pid, c.manifest_name, c.template, c.generated) == (spawned.pid, f"finance-agent@{t.task_id}", "finance-agent", True)
    assert spawned.payload["agent"] == c.manifest_name
    assert created[0].pid == c.pid


def test_a_jira_search_becomes_a_query_and_a_table(make_kernel):
    async def planner(goal, ctx):
        search = await ctx.syscall(_syscall(ctx, "jira.read", "jira", "search_issues", project="APOLLO"))
        issue = await ctx.syscall(_syscall(ctx, "jira.read", "jira", "get_issue", key="APOLLO-12"))
        return done(ctx, search=search.status.value, issue=issue.status.value)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent", tools=["jira.read"])])

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t

    assert run(go).status == TaskStatus.COMPLETED
    queries, tables = k.bus.of_type("tool.query"), k.bus.of_type("task.data")
    assert len(queries) == len(tables) == 1  # get_issue is not a query
    q, d = ToolQuery.model_validate(queries[0].payload), TaskData.model_validate(tables[0].payload)
    assert (q.tool, q.query, q.pid) == ("jira.search_issues", "project=APOLLO", queries[0].pid)
    assert d.columns == ["key", "status", "summary"] and q.rows == len(d.rows) >= 1 and d.source == "jira.search_issues"
    assert all(r[0].startswith("APOLLO-") for r in d.rows)
    assert queries[0].correlation_id == tables[0].correlation_id is not None
    completed = next(e for e in k.bus.of_type("tool.completed") if e.correlation_id == queries[0].correlation_id)
    assert completed.payload["operation"] == "search_issues"
