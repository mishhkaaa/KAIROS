"""The browser tool through the Playwright MCP server (B4): unit tests on a stub MCP session, the factory switch, and a
live run in the kairos/sandbox-browser-mcp image (skipped without Docker or the image)."""
import asyncio
import base64
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from kairos_contracts.schema import ToolInvocation
from kairos_contracts.testing.fakes import InMemoryArtifactStore, InMemoryEventBus
from kairos_contracts.wiring import REPO_ROOT, ServiceBundle, Settings
from kairos_execution.mcp.backend import McpServerConfig, load_mcp_config
from kairos_execution.mcp.browser import McpBrowserBackend

PNG = b"\x89PNG\r\n\x1a\nfake"
SNAPSHOT = "### Page\n- Page URL: http://vendor-docs/sdk-v5.html\n- Page Title: PayCo SDK v5: release status\n### Snapshot\n..."


def _res(*content, error=False):
    return SimpleNamespace(content=list(content), is_error=error)


def _text(t):
    return SimpleNamespace(type="text", text=t)


class StubMcp:
    name = "playwright"
    config = SimpleNamespace(timeout_s=60)

    def __init__(self, fail: dict | None = None):
        self.calls, self.fail = [], fail or {}

    async def call(self, tool, args):
        self.calls.append((tool, args))
        if tool in self.fail:
            return self.fail[tool]()
        if tool == "browser_snapshot":
            return _res(_text(SNAPSHOT))
        if tool == "browser_take_screenshot":
            return _res(_text("saved"), SimpleNamespace(type="image", data=base64.b64encode(PNG).decode(), mimeType="image/png"))
        return _res(_text("ok"))

    async def aclose(self):
        pass


def _backend(stub):
    services = ServiceBundle(settings=Settings(), artifacts=InMemoryArtifactStore(), event_bus=InMemoryEventBus())
    return McpBrowserBackend(McpServerConfig(name="playwright", command="docker", browser=True), services, mcp=stub), services


def _open(backend, url, constraints=None):
    return asyncio.run(backend.execute(ToolInvocation(invocation_id="INV-1", syscall_id="SC-1", task_id="T-1", pid=104,
                                                      tool="browser", operation="open", arguments={"url": url},
                                                      constraints=constraints or {"network_allow": ["vendor-docs:80"]})))


def test_open_returns_the_page_and_a_screenshot_event():
    stub = StubMcp()
    backend, services = _backend(stub)
    r = _open(backend, "http://vendor-docs/sdk-v5.html")
    assert r.status.value == "success"
    assert (r.output["url"], r.output["title"], r.output["transport"]) == ("http://vendor-docs/sdk-v5.html",
                                                                         "PayCo SDK v5: release status", "mcp")
    assert [t for t, _ in stub.calls] == ["browser_navigate", "browser_snapshot", "browser_take_screenshot"]
    [ref] = r.artifacts
    assert asyncio.run(services.artifacts.get(ref)) == PNG
    [shot] = services.event_bus.of_type("sandbox.screenshot")
    assert shot.payload["artifact"] == ref and shot.task_id == "T-1" and shot.pid == 104


def test_the_kernels_allowlist_applies_before_the_browser_is_asked():
    stub = StubMcp()
    backend, _ = _backend(stub)
    r = _open(backend, "http://example.com/")
    assert r.status.value == "error" and r.error.code == "POLICY_DENIED" and stub.calls == []
    assert _open(backend, "file:///etc/passwd").error.code == "BAD_REQUEST"


def test_browser_errors_and_timeouts_are_clear():
    def blocked():
        return _res(_text("Error: net::ERR_BLOCKED_BY_CLIENT at http://vendor-docs/x"), error=True)

    def slow():
        raise TimeoutError

    r = _open(_backend(StubMcp({"browser_navigate": blocked}))[0], "http://vendor-docs/x")
    assert r.error.code == "TOOL_FAILED" and "ERR_BLOCKED_BY_CLIENT" in r.error.message
    r = _open(_backend(StubMcp({"browser_navigate": slow}))[0], "http://vendor-docs/x")
    assert r.error.code == "TIMEOUT" and "60s" in r.error.message


def test_the_example_config_switches_the_browser_tool(monkeypatch):
    from kairos_execution.factory import build_tool_executor

    monkeypatch.setenv("KAIROS_MCP_CONFIG", str(REPO_ROOT / "execution" / "mcp.browser.example.yaml"))
    [cfg] = load_mcp_config()
    assert cfg.browser and "--allowed-origins" in cfg.args and "kairos_sandbox" in cfg.args and "--read-only" in cfg.args
    executor = build_tool_executor(Settings(), ServiceBundle(settings=Settings()))
    assert isinstance(executor.backends["browser"], McpBrowserBackend)
    assert "playwright" not in executor.backends  # the browser server is not also a generic MCP tool
    monkeypatch.delenv("KAIROS_MCP_CONFIG")
    assert not isinstance(build_tool_executor(Settings(), ServiceBundle(settings=Settings())).backends["browser"],
                          McpBrowserBackend)  # off by default


def _image_present() -> bool:
    if not shutil.which("docker"):
        return False
    r = subprocess.run(["docker", "image", "inspect", "kairos/sandbox-browser-mcp:latest"], capture_output=True)
    return r.returncode == 0


@pytest.mark.skipif(not _image_present(), reason="needs Docker and kairos/sandbox-browser-mcp (see its Dockerfile)")
def test_live_vendor_docs_through_the_mcp_sandbox(monkeypatch):
    monkeypatch.setenv("KAIROS_MCP_CONFIG", str(REPO_ROOT / "execution" / "mcp.browser.example.yaml"))
    [cfg] = load_mcp_config()
    services = ServiceBundle(settings=Settings(), artifacts=InMemoryArtifactStore(), event_bus=InMemoryEventBus())
    backend = McpBrowserBackend(cfg, services)

    async def go():
        try:
            ok = await backend.execute(ToolInvocation(invocation_id="INV-1", syscall_id="SC-1", task_id="T-live", pid=1,
                                                      tool="browser", operation="open",
                                                      arguments={"url": "http://vendor-docs/warehouse-pricing.html"},
                                                      constraints={"network_allow": ["vendor-docs:80", "example.com:80"]}))
            blocked = await backend.execute(ToolInvocation(invocation_id="INV-2", syscall_id="SC-2", task_id="T-live", pid=1,
                                                           tool="browser", operation="open", arguments={"url": "http://example.com/"},
                                                           constraints={"network_allow": ["vendor-docs:80", "example.com:80"]}))
            return ok, blocked
        finally:
            await backend.aclose()

    ok, blocked = asyncio.run(go())
    assert ok.status.value == "success" and "vendor-docs" in ok.output["url"] and ok.output["text"]
    assert len(ok.artifacts) == 1 and services.event_bus.of_type("sandbox.screenshot")
    assert blocked.status.value == "error"  # outside --allowed-origins even when the policy would allow it
