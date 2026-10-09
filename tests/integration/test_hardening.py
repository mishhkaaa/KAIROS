"""Kernel protections for generated agents: generated agents and their sub-agents are retried on model outages and
held to their wall-time quotas; a SQL timeout ends the task with a clear reason and files nothing; a killed task
leaves no generated manifests or policies behind. Real kernel, fake models/knowledge/tools."""
import asyncio

from kairos_agents.library.data_engineer import DataEngineerAgent
from kairos_agents.library.planner import PlannerAgent
from kairos_agents.library.research import ResearchAgent
from kairos_agents.library.writer import WriterAgent
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import ResourceQuota, TaskCreate, TaskStatus, ToolResult, ToolResultStatus
from kairos_contracts.testing.fakes import FakeAgentContext, FakeModelRouter, FakeToolExecutor, load_manifests, user_principal
from kairos_contracts.wiring import REPO_ROOT
from kairos_kernel.config import KernelConfig
from kairos_kernel.policy.engine import template_of
from kairos_kernel.testing import done, kernel_factory, manifest, run

VENDORS = "Which vendors were paid more than their contract in Q3, and by how much? Draft a note to finance."
OUTAGE = "ollama qwen2.5:7b-instruct: cannot reach Ollama at http://127.0.0.1:11434 (ConnectError)"


def _kernel(tmp_path, scripts, manifests, **config):
    make = kernel_factory(tmp_path, KernelConfig(policy_watch_interval_s=0, retry_backoff_s=0.05, **config))
    return make(scripts, manifests)


async def _task(k, goal="g", quota=None):
    await k.boot()
    task = await k.tasks.create(TaskCreate(goal=goal, quota=quota, metadata={"root_agent": "planner-agent"}), user_principal())
    return task.task_id


def test_a_generated_agent_rides_out_a_model_outage(tmp_path):
    attempts = []

    async def planner(goal, ctx):
        return (await ctx.wait(await ctx.spawn("finance-agent", "budget"))).model_copy(update={"pid": ctx.pid, "agent": ctx.manifest.name})

    async def finance(goal, ctx):
        attempts.append(ctx.manifest.name)
        if len(attempts) < 3:
            raise KairosError("MODEL_UNAVAILABLE", OUTAGE)
        return done(ctx, "recovered")

    k = _kernel(tmp_path, {"planner-agent": planner, "finance-agent": finance},
                [manifest("planner-agent", agents=["finance-agent"]), manifest("finance-agent")])

    async def go():
        t = await k.tasks.wait_terminal(await _task(k), timeout=30)
        await k.shutdown()
        return t

    t = run(go, timeout=40)
    assert t.status == TaskStatus.COMPLETED and len(attempts) == 3
    assert attempts == [f"finance-agent@{t.task_id}"] * 3  # retried as the same generated agent
    assert k.ephemeral.names(t.task_id) == []


def test_generated_agents_and_their_sub_agents_are_held_to_their_wall_time(tmp_path):
    async def planner(goal, ctx):
        return (await ctx.wait(await ctx.spawn("analyst", "look"))).model_copy(update={"pid": ctx.pid, "agent": ctx.manifest.name})

    async def analyst(goal, ctx):
        return (await ctx.wait(await ctx.spawn("writer", "draft"))).model_copy(update={"pid": ctx.pid, "agent": ctx.manifest.name})

    async def writer(goal, ctx):
        await asyncio.sleep(30)  # stuck (a model that never answers)
        return done(ctx)

    k = _kernel(tmp_path, {"planner-agent": planner, "analyst": analyst, "writer": writer},
                [manifest("planner-agent", agents=["analyst"]), manifest("analyst", agents=["writer"]), manifest("writer")],
                min_agent_wall_s=0)

    async def go():
        tid = await _task(k, quota=ResourceQuota(max_wall_seconds=1))
        t = await k.tasks.wait_terminal(tid, timeout=30)
        procs = {template_of(p.agent): p for p in k.procs.list(tid)}
        await k.shutdown()
        return t, procs

    t, procs = run(go, timeout=40)
    assert t.status == TaskStatus.FAILED and t.error.code == "QUOTA_EXCEEDED", t.error
    assert procs["writer"].agent == f"writer@{t.task_id}" and procs["writer"].state.value in ("FAILED", "TERMINATED")
    assert k.ephemeral.names(t.task_id) == [] and not (tmp_path / "ephemeral" / t.task_id).exists()


class _SlowDb(FakeToolExecutor):
    async def execute(self, invocation):
        if invocation.tool == "db" and invocation.operation == "query":
            self.invocations.append(invocation)
            return ToolResult(invocation_id=invocation.invocation_id, status=ToolResultStatus.ERROR,
                              error=KairosError("TIMEOUT", "the statement ran longer than 5000 ms").to_info())
        return await super().execute(invocation)


def test_a_sql_timeout_fails_the_task_clearly_and_files_nothing(tmp_path):
    tools = _SlowDb()
    make = kernel_factory(tmp_path, KernelConfig(policy_watch_interval_s=0, retry_backoff_s=0))
    good = "SELECT v.name FROM vendors v LIMIT 200"
    k = make({"planner-agent": lambda g, c: PlannerAgent().run(g, c), "data-engineer": lambda g, c: DataEngineerAgent().run(g, c),
              "writer": lambda g, c: WriterAgent().run(g, c)},
             load_manifests(REPO_ROOT / "agents" / "manifests"), tools=tools,
             models=FakeModelRouter({"Database schema": {"sql": good}}))

    async def go():
        tid = await _task(k, VENDORS)
        t = await k.tasks.wait_terminal(tid, timeout=30)
        await k.shutdown()
        return t

    t = run(go, timeout=40)
    assert t.status == TaskStatus.FAILED and t.error.code == "TIMEOUT", t.error
    assert "data-engineer did not finish" in t.error.message and "5000 ms" in t.error.message
    assert "nothing was filed" in t.error.message
    assert tools.db.execute("SELECT COUNT(*) FROM finance_notes").fetchone() == (0,)
    assert not [i for i in tools.invocations if i.tool == "db" and i.operation == "write"]
    assert k.ephemeral.names(t.task_id) == []


def test_a_killed_task_leaves_no_generated_manifests_or_policies(tmp_path):
    async def planner(goal, ctx):
        await ctx.wait(await ctx.spawn("finance-agent", "budget"))
        return done(ctx)

    async def finance(goal, ctx):
        await asyncio.sleep(30)
        return done(ctx)

    k = _kernel(tmp_path, {"planner-agent": planner, "finance-agent": finance},
                [manifest("planner-agent", agents=["finance-agent"]), manifest("finance-agent")])

    async def go():
        tid = await _task(k)
        for _ in range(200):
            if k.ephemeral.names(tid):
                break
            await asyncio.sleep(0.02)
        generated = k.ephemeral.names(tid)
        root = k.tasks.get(tid).root_pid
        await k.lifecycle.kill(root, reason="killed by the operator")
        t = await k.tasks.wait_terminal(tid, timeout=10)
        overlay = dict(getattr(k.policy, "generated", {}))
        await k.shutdown()
        return t, generated, overlay

    t, generated, overlay = run(go, timeout=30)
    assert generated == [f"finance-agent@{t.task_id}"]
    assert t.status in (TaskStatus.FAILED, TaskStatus.CANCELLED)
    assert k.ephemeral.names(t.task_id) == [] and not (tmp_path / "ephemeral" / t.task_id).exists()
    assert not any(name.endswith(t.task_id) for name in overlay)


def test_a_browser_timeout_is_reported_and_the_research_goes_on():
    class _SlowBrowser(FakeToolExecutor):
        async def execute(self, invocation):
            if invocation.tool == "browser":
                return ToolResult(invocation_id=invocation.invocation_id, status=ToolResultStatus.ERROR,
                                  error=KairosError("TIMEOUT", "MCP tool browser.open exceeded 60s").to_info())
            return await super().execute(invocation)

    research = next(m for m in load_manifests(REPO_ROOT / "agents" / "manifests") if m.name == "research-agent")
    ctx = FakeAgentContext(manifest=research, responses={"": {"findings": [], "urls_opened": [], "summary": "s"}})
    ctx.tools = _SlowBrowser()
    result = asyncio.run(ResearchAgent().run("Project Apollo vendor context", ctx))
    assert result.status.value == "completed"  # a page it could not open is not a failed investigation
    assert result.output["urls_opened"] == []
    [browse] = [r for q, r in ctx.syscalls if q.capability == "browser.open"]
    assert browse.status.value == "failed" and browse.error.code == "TIMEOUT"
