"""Scheduled agents (cron): firing, no self-overlap, config parsing, boot wiring."""
import asyncio

from kairos_contracts.schema import Priority, TaskStatus
from kairos_kernel.config import KernelConfig
from kairos_kernel.scheduler.cron import CronRunner, Schedule, load_schedules
from kairos_kernel.testing import done, eventually, manifest, run


def test_schedule_fires_as_background_task_without_overlap(make_kernel):

    async def planner(goal, ctx):
        await asyncio.sleep(0.2)
        return done(ctx, goal)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent")])

    async def go():
        await k.boot()
        cron = CronRunner(k, [Schedule(name="check", every_s=10, goal="check budgets")])
        first = await cron.fire(cron.schedules[0])
        overlap = await cron.fire(cron.schedules[0])  # previous run still active -> skipped
        t = await k.tasks.wait_terminal(first)
        second = await cron.fire(cron.schedules[0])
        await k.tasks.wait_terminal(second)
        await k.shutdown()
        return t, overlap, second

    t, overlap, second = run(go)
    assert overlap is None and second and second != t.task_id
    assert t.status == TaskStatus.COMPLETED and t.user_id == "scheduler" and t.priority == Priority.BACKGROUND
    assert t.metadata["schedule"] == "check"
    assert [e.payload["job"] for e in k.bus.of_type("cron.triggered")] == ["check", "check"]


def test_schedules_file_is_wired_at_boot(make_kernel, tmp_path):
    f = tmp_path / "schedules.yaml"
    f.write_text("schedules:\n  - {name: boot-job, every_s: 3600, goal: warm up, run_at_boot: true, priority: normal}\n")
    assert load_schedules(f)[0].priority == Priority.NORMAL and load_schedules(tmp_path / "missing.yaml") == []

    async def planner(goal, ctx):
        return done(ctx, goal)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent")],
                    config=KernelConfig(schedules_file=str(f), policy_watch_interval_s=0))

    async def go():
        await k.boot()
        await eventually(lambda: any(t.metadata.get("schedule") == "boot-job" for t in k.tasks.list()))
        task = next(t for t in k.tasks.list() if t.metadata.get("schedule") == "boot-job")
        t = await k.tasks.wait_terminal(task.task_id)
        await k.shutdown()
        return t

    assert run(go).result.summary == "warm up"
