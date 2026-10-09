"""Model outages and wall-time quotas: a task ends in a clear state with a reason, and never hangs."""
import asyncio
import time

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import AgentResultStatus, ResourceQuota, TaskCreate, TaskStatus
from kairos_contracts.testing.fakes import user_principal
from kairos_kernel.config import KernelConfig
from kairos_kernel.policy.engine import template_of
from kairos_kernel.testing import done, manifest, run

OUTAGE = "ollama qwen2.5:7b-instruct: ConnectError: connection refused"


def _config(**kw) -> KernelConfig:
    return KernelConfig(policy_watch_interval_s=0, **kw)


async def _start(k, quota: ResourceQuota | None = None) -> str:
    task = await k.tasks.create(TaskCreate(goal="g", quota=quota, metadata={"root_agent": "planner-agent"}), user_principal())
    return task.task_id


# time.monotonic() ticks every ~15.6 ms on Windows, so a measured sleep can read up to one tick short of its length.
TICK = 0.02


def test_a_model_outage_is_ridden_out_with_backoff(make_kernel):
    """An Ollama restart makes calls fail for a few seconds; retrying at once burned all three attempts inside it."""
    attempts: list[float] = []

    async def planner(goal, ctx):
        attempts.append(time.monotonic())
        if len(attempts) < 3:
            raise KairosError("MODEL_UNAVAILABLE", OUTAGE)
        return done(ctx)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent")], config=_config(retry_backoff_s=0.2))

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await _start(k))
        await k.shutdown()
        return t

    t = run(go)
    assert t.status == TaskStatus.COMPLETED
    gaps = [b - a for a, b in zip(attempts, attempts[1:], strict=False)]
    assert gaps[0] >= 0.2 - TICK and gaps[1] >= 0.6 - TICK, f"backoff 0.2 s, then 3x: {gaps}"


def _failed(ctx, code: str = "MODEL_UNAVAILABLE", message: str = OUTAGE):
    """What the real agent runtime returns for a handled KairosError: a FAILED result, not an exception."""
    from kairos_contracts.schema import AgentResult, ErrorInfo

    return AgentResult(pid=ctx.pid, agent=ctx.manifest.name, status=AgentResultStatus.FAILED,
                       summary=f"{ctx.manifest.name} failed: {message}", error=ErrorInfo(code=code, message=message, retriable=True))


def test_a_returned_model_failure_is_retried_too(make_kernel):
    """The runtime turns KairosErrors into FAILED results, so the live Ollama restart was never retried at all."""
    attempts: list[float] = []

    async def planner(goal, ctx):
        return done(ctx, (await ctx.wait(await ctx.spawn("finance-agent", "budget"))).status.value)

    async def finance(goal, ctx):
        attempts.append(time.monotonic())
        return _failed(ctx) if len(attempts) < 3 else done(ctx)

    k = make_kernel({"planner-agent": planner, "finance-agent": finance},
                    [manifest("planner-agent", agents=["finance-agent"]), manifest("finance-agent")],
                    config=_config(retry_backoff_s=0.1))

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await _start(k))
        await k.shutdown()
        return t

    t = run(go)
    assert t.status == TaskStatus.COMPLETED and t.result.summary == "completed"
    assert len(attempts) == 3 and attempts[1] - attempts[0] >= 0.1 - TICK and attempts[2] - attempts[1] >= 0.3 - TICK


def test_returned_failures_are_not_rerun_where_that_would_repeat_work(make_kernel):
    """Re-running a planner that already spawned children would redo the whole run; re-running an agent that holds
    approval-gated capabilities could repeat a write. Those fail at once, with their reason."""
    from kairos_contracts.schema import ManifestApproval

    runs = {"planner-agent": 0, "action-agent": 0}

    async def planner(goal, ctx):
        runs["planner-agent"] += 1
        await ctx.wait(await ctx.spawn("action-agent", "update the tracker"))
        return _failed(ctx)

    async def action(goal, ctx):
        runs["action-agent"] += 1
        return _failed(ctx)

    writer = manifest("action-agent", tools=["jira.write"]).model_copy(update={"approval": ManifestApproval(required=["jira.write"])})
    k = make_kernel({"planner-agent": planner, "action-agent": action},
                    [manifest("planner-agent", agents=["action-agent"]), writer], config=_config(retry_backoff_s=0.05))

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await _start(k))
        await k.shutdown()
        return t

    t = run(go)
    assert runs == {"planner-agent": 1, "action-agent": 1}
    assert t.status == TaskStatus.FAILED and "connection refused" in t.error.message


def test_crashes_are_still_retried_at_once(make_kernel):
    attempts: list[float] = []

    async def planner(goal, ctx):
        attempts.append(time.monotonic())
        if len(attempts) < 2:
            raise RuntimeError("bug")
        return done(ctx)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent")], config=_config(retry_backoff_s=5))

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await _start(k))
        await k.shutdown()
        return t

    assert run(go).status == TaskStatus.COMPLETED
    assert attempts[1] - attempts[0] < 1, "only backend errors wait: a code bug won't fix itself"


def test_an_outage_that_outlasts_the_retries_fails_the_task_with_its_reason(make_kernel):
    async def planner(goal, ctx):
        raise KairosError("MODEL_UNAVAILABLE", OUTAGE)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent")], config=_config(retry_backoff_s=0.05))

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await _start(k))
        await k.shutdown()
        return t

    t = run(go)
    assert t.status == TaskStatus.FAILED
    assert t.error.code == "MODEL_UNAVAILABLE" and "connection refused" in t.error.message
    events = k.services.event_bus.of_type("task.failed")
    assert events and "connection refused" in str(events[-1].payload)


def test_a_blocked_agent_is_stopped_at_its_wall_time_quota(make_kernel):
    """Wall time was checked only when an agent next called ctx.*: one stuck in a call (a model that never answers, a
    child that never finishes) ran on forever."""

    async def planner(goal, ctx):
        await asyncio.Event().wait()  # never returns

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent")], config=_config(min_agent_wall_s=0))

    async def go():
        await k.boot()
        t0 = time.monotonic()
        t = await k.tasks.wait_terminal(await _start(k, ResourceQuota(max_wall_seconds=1)))
        took = time.monotonic() - t0
        await k.shutdown()
        return t, took

    t, took = run(go, timeout=10)
    assert t.status == TaskStatus.FAILED and took < 5
    assert t.error.code == "QUOTA_EXCEEDED" and "wall clock" in t.error.message
    assert k.store.result(t.root_pid).status == AgentResultStatus.FAILED


def test_a_planner_waiting_on_a_stuck_child_ends_the_task_and_leaves_nothing_running(make_kernel):
    async def planner(goal, ctx):
        await ctx.wait(await ctx.spawn("finance-agent", "stuck"))  # no timeout of its own
        return done(ctx)

    async def finance(goal, ctx):
        await asyncio.Event().wait()

    k = make_kernel({"planner-agent": planner, "finance-agent": finance},
                    [manifest("planner-agent", agents=["finance-agent"]), manifest("finance-agent")],
                    config=_config(min_agent_wall_s=0))

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await _start(k, ResourceQuota(max_wall_seconds=1)))
        await k.shutdown()
        return t

    t = run(go, timeout=10)
    # every process gets the task's wall time and the planner's clock starts first, so the planner is stopped first
    assert t.status == TaskStatus.FAILED and t.error.code == "QUOTA_EXCEEDED"
    states = {template_of(p.agent): p.state.value for p in k.procs.list(t.task_id)}
    assert states == {"planner-agent": "FAILED", "finance-agent": "TERMINATED"}, states


def test_the_minimum_agent_wall_time_protects_approval_waits(make_kernel):
    """Tasks default to 600 s, but a human may take longer to approve: agents get at least min_agent_wall_s."""
    captured = {}

    async def planner(goal, ctx):
        captured["quota"] = k.procs.get(ctx.pid).quota.max_wall_seconds
        return done(ctx)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent")], config=_config())

    async def go():
        await k.boot()
        await k.tasks.wait_terminal(await _start(k))
        await k.shutdown()

    run(go)
    assert captured["quota"] == 1800
