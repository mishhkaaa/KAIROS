"""Unit tests for the execution layer: jails, allowlists, rollback, container hardening, browser backend."""
import asyncio
from pathlib import Path

import pytest
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    NetworkMode,
    SandboxSpec,
    ToolInvocation,
    ToolResultStatus,
)
from kairos_contracts.schema.common import new_id
from kairos_contracts.testing.fakes import FakeBrowserDriver, FakeSandboxManager, InMemoryArtifactStore, InMemoryEventBus
from kairos_contracts.wiring import ServiceBundle, Settings
from kairos_execution.artifacts.store import FsArtifactStore
from kairos_execution.connectors.jira import JiraBackend
from kairos_execution.files.workspace import FsBackend
from kairos_execution.sandbox.docker_manager import DockerSandboxManager
from kairos_execution.tools.base import network_allowed
from kairos_execution.tools.executor import Executor
from kairos_execution.tools.sandboxed import BrowserBackend, SandboxPool


def inv(tool: str, op: str, task_id: str = "T-1", constraints=None, timeout_s: int = 120, **args) -> ToolInvocation:
    return ToolInvocation(invocation_id=new_id("INV"), syscall_id=new_id("SC"), task_id=task_id, pid=105, tool=tool,
                          operation=op, arguments=args, constraints=constraints or {}, timeout_s=timeout_s)


def test_artifact_names_cannot_escape(tmp_path):
    store = FsArtifactStore(tmp_path)
    for bad in ("../x", "/etc/passwd", "a/../../b", ".meta/x"):
        with pytest.raises(KairosError):
            asyncio.run(store.put("T-1", bad, b"x"))
    ref = asyncio.run(store.put("T-1", "screenshots/001.png", b"png", "image/png"))
    assert asyncio.run(store.list("T-1")) == [ref] and store.content_type(ref) == "image/png"


def test_fs_jail_write_verify_rollback(tmp_path):
    fs = FsBackend(tmp_path)

    async def go():
        escape = await fs.execute(inv("fs", "write_file", path="../../evil.txt", content="x"))
        first = inv("fs", "write_file", path="reports/r.md", content="v1")
        r1 = await fs.execute(first)
        second = inv("fs", "write_file", path="/workspace/reports/r.md", content="v2")
        r2 = await fs.execute(second)
        verified = await fs.verify(second, r2)
        undone = await fs.rollback(second, r2)
        read = await fs.execute(inv("fs", "read_file", path="reports/r.md"))
        return escape, r1, verified, undone, read

    escape, r1, verified, undone, read = asyncio.run(go())
    assert escape.status == ToolResultStatus.ERROR and escape.error.code == "CAPABILITY_DENIED"
    assert r1.status == ToolResultStatus.SUCCESS and verified.passed and undone
    assert read.output["content"] == "v1", "rollback restored the previous version"


def test_jira_comment_update_and_rollback():
    jira = JiraBackend("inprocess")

    async def go():
        up = inv("jira", "update_issue", key="APOLLO-12", fields={"status": "At Risk"}, comment="root causes: …")
        res = await jira.execute(up)
        ver = await jira.verify(up, res)
        rolled = await jira.rollback(up, res)
        after = await jira.execute(inv("jira", "get_issue", key="APOLLO-12"))
        search = await jira.execute(inv("jira", "search_issues", project="APOLLO"))
        return res, ver, rolled, after, search

    res, ver, rolled, after, search = asyncio.run(go())
    assert res.output["status"] == "At Risk" and "root causes: …" in res.output["comments"]
    assert ver.passed and {c.name for c in ver.checks} >= {"field:status", "comment"}
    assert rolled and after.output["status"] == "In Progress" and after.output["comments"] == []
    assert {i["key"] for i in search.output["issues"]} == {"APOLLO-12", "APOLLO-31"}


@pytest.mark.parametrize("url,allow,ok", [
    ("http://vendor-docs/sdk-v5.html", ["vendor-docs:80"], True),
    ("https://docs.vendor.example/x", ["*.vendor.example:443"], True),
    ("https://evil.example/x", ["vendor-docs:80"], False),
    ("http://vendor-docs:8080/", ["vendor-docs:80"], False),
    ("http://anything/", None, True),       # no constraint from policy (e.g. fake policy)
    ("http://anything/", [], False),        # constraint present but empty => nothing allowed
])
def test_network_allowlist(url, allow, ok):
    assert network_allowed(url, {} if allow is None else {"network_allow": allow}) is ok


def test_executor_timeout_and_unknown_tool():
    class Slow:
        name = "slow"

        def spec(self):
            from kairos_contracts.testing.fakes import FAKE_TOOL_SPECS

            return FAKE_TOOL_SPECS[0]

        async def execute(self, i):
            await asyncio.sleep(5)

    ex = Executor([Slow()])
    r = asyncio.run(ex.execute(inv("slow", "x", timeout_s=0)))
    assert r.status == ToolResultStatus.ERROR and r.error.code == "TIMEOUT"
    assert asyncio.run(ex.execute(inv("nope", "x"))).error.code == "NOT_FOUND"


def test_browser_backend_enforces_allowlist_and_saves_screenshot():
    bus, sandbox, browser, artifacts = InMemoryEventBus(), FakeSandboxManager(), FakeBrowserDriver(), InMemoryArtifactStore()
    services = ServiceBundle(settings=Settings(), event_bus=bus, sandbox=sandbox, browser=browser, artifacts=artifacts)
    pool = SandboxPool(services)
    backend = BrowserBackend(services, pool)
    allow = {"network_allow": ["vendor-docs:80"]}

    async def go():
        blocked = await backend.execute(inv("browser", "open", constraints=allow, url="https://evil.example/"))
        opened = await backend.execute(inv("browser", "open", constraints=allow, url="http://vendor-docs/sdk-v5.html"))
        await pool.release_task("T-1")
        return blocked, opened

    blocked, opened = asyncio.run(go())
    assert blocked.error.code == "POLICY_DENIED"
    assert opened.status == ToolResultStatus.SUCCESS and opened.output["title"].startswith("Fake page")
    assert opened.artifacts == ["artifact://T-1/screenshots/001.png"]
    assert [e.type for e in bus.history] == ["sandbox.started", "sandbox.screenshot", "sandbox.destroyed"]
    assert sandbox.sandboxes and all(s.status.value == "destroyed" for s in sandbox.sandboxes.values())


def test_docker_run_kwargs_are_hardened(tmp_path):
    mgr = DockerSandboxManager(tmp_path, client=object(), endpoint_mode="ip")
    kw = mgr.run_kwargs("SB-1", SandboxSpec(task_id="T-1", network=NetworkMode.NONE, memory_mb=512, cpu=0.5), tmp_path)
    assert kw["read_only"] and kw["cap_drop"] == ["ALL"] and kw["user"] == "10001"
    assert kw["network_mode"] == "none" and "no-new-privileges" in kw["security_opt"]
    assert kw["mem_limit"] == "512m" and kw["nano_cpus"] == 500_000_000 and kw["pids_limit"] == 256
    assert list(kw["volumes"].values()) == [{"bind": "/workspace", "mode": "rw"}]

    browser = mgr.run_kwargs("SB-2", SandboxSpec(task_id="T-1", display=True, network=NetworkMode.ALLOWLIST), tmp_path)
    assert browser["image"].startswith("kairos/sandbox-browser") and browser["network"] == "kairos_sandbox"
    assert "ports" not in browser

    dev = DockerSandboxManager(tmp_path, client=object(), endpoint_mode="port")
    browser_dev = dev.run_kwargs("SB-3", SandboxSpec(task_id="T-1", display=True, network=NetworkMode.ALLOWLIST), tmp_path)
    assert browser_dev["network"] == "kairos_sandbox" and "ports" not in browser_dev, "the browser never joins the bridge"
    relay = dev.relay_kwargs("SB-3", browser_dev["name"])
    assert relay["ports"] == {"3000/tcp": ("127.0.0.1", None)} and relay["command"][-2:] == ["kairos-sb-3", "3000"]
    assert relay["read_only"] and relay["cap_drop"] == ["ALL"] and relay["user"] == "10001"
    assert relay["labels"]["kairos.sandbox"] == "SB-3", "stale-container cleanup finds relays too"


@pytest.mark.parametrize("mode", ["ip", "port"])
def test_only_display_sandboxes_depend_on_the_endpoint_mode(tmp_path, mode):
    mgr = DockerSandboxManager(tmp_path, client=object(), endpoint_mode=mode)
    offline = mgr.run_kwargs("SB-1", SandboxSpec(task_id="T-1", network=NetworkMode.NONE), tmp_path)
    assert offline["network_mode"] == "none" and "ports" not in offline and "network" not in offline
    allow = mgr.run_kwargs("SB-2", SandboxSpec(task_id="T-1", network=NetworkMode.ALLOWLIST), tmp_path)
    assert allow["network"] == "kairos_sandbox" and "ports" not in allow, "non-display sandboxes never use the default bridge"


@pytest.mark.parametrize("mode", ["ip", "port"])
def test_display_sandboxes_are_internal_in_both_modes(tmp_path, mode):
    """Port mode used to put the browser on the default bridge (internet access); now the relay does the publishing."""
    mgr = DockerSandboxManager(tmp_path, client=object(), endpoint_mode=mode)
    for net in (NetworkMode.NONE, NetworkMode.ALLOWLIST):
        kw = mgr.run_kwargs("SB-1", SandboxSpec(task_id="T-1", display=True, network=net), tmp_path)
        assert kw["network"] == "kairos_sandbox" and "ports" not in kw


def test_docker_manager_lifecycle_with_fake_client(tmp_path):
    class Container:
        def __init__(self, kw):
            self.kw, self.removed, self.labels = kw, False, kw["labels"]
            self.attrs = {"NetworkSettings": {"Networks": {}, "Ports": {}}}
            self.name = kw["name"]

        def reload(self):
            pass

        def exec_run(self, cmd, workdir, demux):
            class R:
                exit_code, output = 0, (b"hi\n", b"")

            return R()

        def remove(self, force):
            self.removed = True

    class Client:
        def __init__(self):
            self.containers = self
            self.started: list[Container] = []

        def list(self, all, filters):
            return []

        def run(self, **kw):
            self.started.append(Container(kw))
            return self.started[-1]

    client = Client()
    mgr = DockerSandboxManager(Path(tmp_path), client=client, endpoint_mode="ip")

    async def go():
        info = await mgr.provision(SandboxSpec(task_id="T-9"))
        from kairos_contracts.schema import ExecRequest

        res = await mgr.exec(info.sandbox_id, ExecRequest(command=["echo", "hi"]))
        await mgr.destroy(info.sandbox_id)
        return info, res, await mgr.list("T-9")

    info, res, listed = asyncio.run(go())
    assert res.stdout == "hi\n" and client.started[0].removed
    assert listed[0].status.value == "destroyed" and (tmp_path / "T-9").is_dir()


def test_port_mode_publishes_the_browser_through_a_relay(tmp_path):
    """Docker Desktop (port mode): the browser starts on the internal network only; a relay container publishes
    127.0.0.1:<port>, joins the sandbox network to reach it, serves the endpoint, and is removed with the sandbox."""
    connected: list[tuple[str, str]] = []
    started: list = []

    class Container:
        def __init__(self, kw):
            self.kw, self.name, self.labels, self.removed = kw, kw["name"], kw["labels"], False
            ports = {"3000/tcp": [{"HostPort": "49153"}]} if "ports" in kw else {}
            self.attrs = {"NetworkSettings": {"Networks": {}, "Ports": ports}}

        def reload(self):
            pass

        def remove(self, force):
            self.removed = True

    class Network:
        def __init__(self, name):
            self.name = name

        def connect(self, container):
            connected.append((self.name, container.name))

    class Client:
        def __init__(self):
            self.containers, self.networks = self, self

        def list(self, all=None, filters=None, names=None):
            return [] if filters is not None else [Network(n) for n in names or []]

        def get(self, name):
            return Network(name)

        def create(self, *a, **kw):
            pass

        def run(self, **kw):
            started.append(Container(kw))
            return started[-1]

    mgr = DockerSandboxManager(Path(tmp_path), client=Client(), endpoint_mode="port")

    async def no_wait(url, timeout=30.0):
        return None

    mgr._wait_for_port = no_wait

    async def go():
        web = await mgr.provision(SandboxSpec(task_id="T-7", display=True, network=NetworkMode.ALLOWLIST))
        await mgr.provision(SandboxSpec(task_id="T-7", network=NetworkMode.ALLOWLIST))  # no relay for non-display
        await mgr.destroy(web.sandbox_id)
        return web

    web = asyncio.run(go())
    browser, relay = started[0], started[1]
    assert browser.kw["network"] == "kairos_sandbox" and "ports" not in browser.kw
    assert relay.name == f"kairos-{web.sandbox_id.lower()}-relay" and "ports" in relay.kw
    assert connected == [("kairos_sandbox", relay.name)], "only the relay joins the sandbox network from the bridge"
    assert web.endpoints == {"playwright": "ws://127.0.0.1:49153/"}
    assert browser.removed and relay.removed
    assert len(started) == 3
