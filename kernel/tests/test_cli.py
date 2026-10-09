"""The ai-* CLI against a real kernel gateway served by uvicorn on a background thread."""
import asyncio
import importlib
import socket
import threading
import time

import pytest
import uvicorn
from kairos_contracts.schema import Risk, SyscallRequest
from kairos_contracts.schema.common import new_id
from kairos_kernel.gateway.app import create_app
from kairos_kernel.testing import done, kernel_factory, manifest
from typer.testing import CliRunner


async def planner(goal, ctx):
    if goal == "long":
        for _ in range(3000):
            await ctx.log("tick")
            await asyncio.sleep(0.01)
    if goal.startswith("update"):
        await ctx.syscall(SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid, capability="jira.write",
                                         tool="jira", operation="update_issue", risk=Risk.MEDIUM,
                                         arguments={"key": "APOLLO-12", "comment": "from cli"}))
    child = await ctx.spawn("worker", "help")
    await ctx.wait(child)
    return done(ctx, f"finished {goal}")


async def worker(goal, ctx):
    return done(ctx, "worker ok")


@pytest.fixture(scope="module")
def cli(tmp_path_factory):
    kernel = kernel_factory(tmp_path_factory.mktemp("cli"))(
        {"planner-agent": planner, "worker": worker},
        [manifest("planner-agent", agents=["worker"], tools=["jira.write"]), manifest("worker")])
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(kernel), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    import os

    old = os.environ.get("KAIROS_URL")
    os.environ["KAIROS_URL"] = f"http://127.0.0.1:{port}"
    import kairos_kernel.cli.main as main

    main = importlib.reload(main)
    yield main, CliRunner(), kernel
    server.should_exit = True
    thread.join(10)
    if old is None:
        os.environ.pop("KAIROS_URL", None)
    else:
        os.environ["KAIROS_URL"] = old


def invoke(cli, *args):
    main, runner, _ = cli
    result = runner.invoke(main.app, list(args), env={"COLUMNS": "200"})
    return result


def test_run_streams_and_auto_approves(cli):
    r = invoke(cli, "run", "update the tracker", "--yes")
    assert r.exit_code == 0, r.output
    assert "approval needed: jira.write" in r.output and "transaction.committed" in r.output
    assert "finished update the tracker" in r.output


def test_ps_tree_audit_tasks(cli):
    r = invoke(cli, "run", "simple", "--yes")
    assert r.exit_code == 0
    tasks = invoke(cli, "tasks")
    assert "simple" in tasks.output and "completed" in tasks.output
    ps = invoke(cli, "ps")
    assert "planner-agent" in ps.output and "worker" in ps.output and "COMPLETED" in ps.output
    tree = invoke(cli, "tree")
    assert "planner-agent" in tree.output and "worker" in tree.output
    task_id = cli[2].tasks.list()[-1].task_id
    audit = invoke(cli, "audit", task_id)
    assert audit.exit_code == 0 and "Spawned worker" in audit.output and "goal: simple" in audit.output


def test_control_commands(cli):
    _, _, kernel = cli
    import httpx

    main = cli[0]
    t = httpx.post(f"{main.URL}/tasks", json={"goal": "long", "metadata": {"root_agent": "planner-agent"}}).json()
    deadline = time.monotonic() + 10
    while kernel.tasks.get(t["task_id"]).root_pid is None and time.monotonic() < deadline:
        time.sleep(0.02)
    pid = kernel.tasks.get(t["task_id"]).root_pid
    assert "PAUSED" in invoke(cli, "pause", str(pid)).output
    assert "RUNNING" in invoke(cli, "resume", str(pid)).output
    assert "checkpoint CKPT-" in invoke(cli, "checkpoint", str(pid)).output
    assert "TERMINATED" in invoke(cli, "kill", str(pid)).output
    top = invoke(cli, "top", "--once")
    assert top.exit_code == 0 and "CPU" in top.output and "tok/min" in top.output
    missing = invoke(cli, "kill", "99999")
    assert missing.exit_code == 1 and "PROCESS_NOT_FOUND" in missing.output


def test_mount_lists_and_reads(cli):
    listing = invoke(cli, "mount", "/org/projects")
    assert "/org/projects/apollo" in listing.output
    obj = invoke(cli, "mount", "/org/projects/apollo")
    assert "Project Apollo" in obj.output and "trust=verified" in obj.output
    windows_mangled = invoke(cli, "mount", "C:/Program Files/Git/org/projects")
    assert "/org/projects/apollo" in windows_mangled.output


def test_unreachable_gateway(cli, monkeypatch):
    main = cli[0]
    monkeypatch.setattr(main, "URL", "http://127.0.0.1:1")
    r = invoke(cli, "ps", "--all")
    assert r.exit_code == 2 and "cannot reach KAIROS gateway" in r.output
