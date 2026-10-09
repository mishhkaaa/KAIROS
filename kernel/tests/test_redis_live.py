"""LIVE Redis tests: the event bus mirror and history replay across a kernel restart.

Starts a throwaway redis:7-alpine container (skips without Docker) — or uses KAIROS_TEST_REDIS_URL if set.
"""
import os
import subprocess
import time
import uuid

import pytest
from kairos_contracts.schema import Event
from kairos_contracts.testing.fakes import fake_bundle
from kairos_contracts.wiring import Settings
from kairos_kernel.config import KernelConfig
from kairos_kernel.events.bus import KernelEventBus, RedisMirror, redis_reachable
from kairos_kernel.kernel import Kernel
from kairos_kernel.testing import ScriptedRuntime, done, manifest, run, start_task


@pytest.fixture(scope="module")
def redis_url():
    if os.getenv("KAIROS_TEST_REDIS_URL"):
        yield os.environ["KAIROS_TEST_REDIS_URL"]
        return
    name = f"kairos-redis-test-{uuid.uuid4().hex[:6]}"
    started = subprocess.run(["docker", "run", "-d", "--rm", "--name", name, "-p", "127.0.0.1::6379", "redis:7-alpine"],
                             capture_output=True, text=True)
    if started.returncode != 0:
        pytest.skip(f"cannot start redis: {started.stderr.strip()[:120]}")
    try:
        port = subprocess.run(["docker", "port", name, "6379/tcp"], capture_output=True, text=True).stdout.split(":")[-1].strip()
        url = f"redis://127.0.0.1:{port}/0"
        deadline = time.monotonic() + 20
        while not redis_reachable(url):
            if time.monotonic() > deadline:
                pytest.skip("redis did not come up")
            time.sleep(0.3)
        yield url
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def test_mirror_appends_and_replays(redis_url):
    key = f"test:{uuid.uuid4().hex}"

    async def go():
        bus = KernelEventBus(mirror=RedisMirror(redis_url, key=key))
        for i in range(5):
            await bus.publish(Event(type="agent.log", source="t", task_id="T-r", payload={"i": i}))
        history = await bus.replay()
        await bus.mirror.close()
        return history

    history = run(go)
    assert [e.payload["i"] for e in history] == [0, 1, 2, 3, 4]


def test_unreachable_redis_never_breaks_publish():
    async def go():
        bus = KernelEventBus(mirror=RedisMirror("redis://127.0.0.1:1/0"))
        got = []
        stream = bus.stream("*")
        await bus.publish(Event(type="task.created", source="t"))
        got.append(await stream.__anext__())
        history = await bus.replay()
        await bus.mirror.close()
        return got, history

    got, history = run(go)
    assert got[0].type == "task.created" and history == []


def test_event_history_survives_kernel_restart(redis_url, tmp_path):
    key = f"test:{uuid.uuid4().hex}"

    def kernel():
        settings = Settings(data_dir=tmp_path)
        bundle = fake_bundle(settings)
        bundle.event_bus = KernelEventBus(mirror=RedisMirror(redis_url, key=key))
        bundle.agent_runtime = ScriptedRuntime({"planner-agent": lambda goal, ctx: _finish(ctx)})
        from kairos_contracts.testing.fakes import FakeAgentRegistry

        bundle.agent_registry = FakeAgentRegistry(manifests=[manifest("planner-agent")])
        return Kernel(settings, bundle, KernelConfig(policy_watch_interval_s=0))

    async def _finish(ctx):
        await ctx.log("did the work")
        return done(ctx, "ok")

    async def first():
        k = kernel()
        await k.boot()
        tid = await start_task(k)
        await k.tasks.wait_terminal(tid)
        await k.shutdown()
        return tid, [e.type for e in k.history[tid]]

    async def second(tid):
        k = kernel()
        await k.boot()
        types = [e.type for e in k.history.get(tid, [])]
        await k.shutdown()
        return types

    tid, before = run(first)
    after = run(lambda: second(tid))
    assert "task.completed" in before and after[: len(before)] == before, "restarted kernel still has the full timeline"
