"""LIVE Docker tests: prove the sandbox hardening from inside a real container.

Needs a running Docker daemon + `docker build -t kairos/sandbox-base:latest execution/images/sandbox-base`.
Skipped automatically otherwise (CI without Docker).
"""
import asyncio
import time

import pytest
from kairos_contracts.schema import ExecRequest, NetworkMode, SandboxSpec, SandboxStatus
from kairos_execution.sandbox.docker_manager import DockerSandboxManager


def _docker_or_skip():
    try:
        import docker

        client = docker.from_env()
        client.ping()
        client.images.get("kairos/sandbox-base:latest")
        return client
    except Exception as e:
        pytest.skip(f"docker sandbox unavailable: {str(e)[:120]}")


@pytest.fixture(scope="module")
def client():
    return _docker_or_skip()


def test_sandbox_is_hardened(client, tmp_path):
    mgr = DockerSandboxManager(tmp_path, client=client)

    async def go():
        info = await mgr.provision(SandboxSpec(task_id="T-live", network=NetworkMode.NONE, memory_mb=256, cpu=0.5))
        run = lambda *cmd: mgr.exec(info.sandbox_id, ExecRequest(command=list(cmd), timeout_s=30))  # noqa: E731
        try:
            return info, {
                "uid": await run("id", "-u"),
                "root_write": await run("sh", "-c", "touch /etc/pwned"),
                "tmp_write": await run("sh", "-c", "touch /tmp/ok && echo ok"),
                "workspace_write": await run("sh", "-c", "echo hello > /workspace/note.txt && cat /workspace/note.txt"),
                "status": await run("cat", "/proc/self/status"),
                "net": await run("python", "-c", "import socket;socket.create_connection(('1.1.1.1',53),2)"),
                "ifaces": await run("ls", "/sys/class/net"),
            }, client.containers.get(f"kairos-{info.sandbox_id.lower()}").attrs["HostConfig"]
        finally:
            await mgr.destroy(info.sandbox_id)

    info, r, host = asyncio.run(go())
    assert r["uid"].stdout.strip() == "10001", "runs as non-root"
    assert r["root_write"].exit_code != 0, "root filesystem is read-only"
    assert r["tmp_write"].stdout.strip() == "ok", "/tmp is a writable tmpfs"
    assert r["workspace_write"].stdout.strip() == "hello", "task workspace is mounted read-write"
    assert (tmp_path / "T-live" / "note.txt").read_text().strip() == "hello", "workspace is shared with the host"
    status = dict(line.split(":", 1) for line in r["status"].stdout.splitlines() if ":" in line)
    assert status["CapEff"].strip() == "0000000000000000", "all capabilities dropped"
    assert status["NoNewPrivs"].strip() == "1", "no-new-privileges"
    assert r["net"].exit_code != 0, "no network egress"
    assert r["ifaces"].stdout.split() == ["lo"], "only loopback"
    assert host["Memory"] == 256 * 1024 * 1024 and host["NanoCpus"] == 500_000_000 and host["PidsLimit"] == 256
    assert host["ReadonlyRootfs"] is True and host["NetworkMode"] == "none"


def test_timeout_reaper_destroys_sandbox(client, tmp_path):
    mgr = DockerSandboxManager(tmp_path, client=client)

    async def go():
        info = await mgr.provision(SandboxSpec(task_id="T-reap", network=NetworkMode.NONE, timeout_s=1))
        name = f"kairos-{info.sandbox_id.lower()}"
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and (await mgr.list("T-reap"))[0].status != SandboxStatus.DESTROYED:
            await asyncio.sleep(0.5)
        return name, (await mgr.list("T-reap"))[0]

    name, info = asyncio.run(go())
    assert info.status == SandboxStatus.DESTROYED
    assert not client.containers.list(all=True, filters={"name": name}), "container removed"


def test_exec_timeout(client, tmp_path):
    from kairos_contracts.errors import KairosError

    mgr = DockerSandboxManager(tmp_path, client=client)

    async def go():
        info = await mgr.provision(SandboxSpec(task_id="T-slow", network=NetworkMode.NONE))
        try:
            with pytest.raises(KairosError) as ei:
                await mgr.exec(info.sandbox_id, ExecRequest(command=["sleep", "30"], timeout_s=1))
            return ei.value.code
        finally:
            await mgr.destroy(info.sandbox_id)

    assert asyncio.run(go()) == "TIMEOUT"


@pytest.mark.parametrize("endpoint_mode", ["ip", "port"])
@pytest.mark.parametrize("network", [NetworkMode.NONE, NetworkMode.ALLOWLIST])
def test_non_display_sandbox_has_no_internet_in_any_endpoint_mode(client, tmp_path, endpoint_mode, network):
    """The endpoint mode only exists to publish a browser's port on Docker Desktop; exec sandboxes never get egress."""
    mgr = DockerSandboxManager(tmp_path, client=client, endpoint_mode=endpoint_mode)
    probe = "import socket;socket.create_connection(('1.1.1.1',53),3);print('REACHABLE')"

    async def go():
        info = await mgr.provision(SandboxSpec(task_id="T-egress", network=network))
        try:
            return await mgr.exec(info.sandbox_id, ExecRequest(command=["python", "-c", probe], timeout_s=30))
        finally:
            await mgr.destroy(info.sandbox_id)

    res = asyncio.run(go())
    assert res.exit_code != 0 and "REACHABLE" not in res.stdout, f"{endpoint_mode}/{network}: sandbox reached the internet"
