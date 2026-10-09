"""LIVE end-to-end browser path (P1 side): DockerSandboxManager starts kairos/sandbox-browser, a reference Playwright
client connects to SandboxInfo.endpoints["playwright"], and BrowserBackend opens a real page, enforces the network
allowlist, stores the screenshot as an artifact and cleans the sandbox up.

P4's production BrowserDriver replaces `ReferenceDriver` below; this test proves the P1 half works for real.
Needs Docker + `docker build -t kairos/sandbox-browser:latest execution/images/sandbox-browser`.
"""
import asyncio

import pytest
from kairos_contracts.schema import (
    BrowserPage,
    ExecRequest,
    NetworkMode,
    SandboxInfo,
    SandboxSpec,
    ToolInvocation,
    ToolResultStatus,
)
from kairos_contracts.schema.common import new_id
from kairos_contracts.testing.fakes import InMemoryEventBus
from kairos_contracts.wiring import ServiceBundle, Settings
from kairos_execution.artifacts.store import FsArtifactStore
from kairos_execution.sandbox.docker_manager import DockerSandboxManager
from kairos_execution.tools.sandboxed import BrowserBackend, SandboxPool


class ReferenceDriver:
    """Minimal Playwright client (the shape of P4's driver) used only to exercise the P1 path."""

    def __init__(self) -> None:
        self._pw, self._pages = None, {}

    async def _page(self, sb: SandboxInfo):
        if sb.sandbox_id not in self._pages:
            from playwright.async_api import async_playwright

            self._pw = self._pw or await async_playwright().start()
            browser = await self._pw.chromium.connect(sb.endpoints["playwright"], timeout=20000)
            self._pages[sb.sandbox_id] = (browser, await (await browser.new_context()).new_page())
        return self._pages[sb.sandbox_id][1]

    async def open(self, sb, url):
        page = await self._page(sb)
        await page.goto(url, timeout=15000)
        return BrowserPage(url=page.url, title=await page.title(), text=(await page.inner_text("body"))[:20000])

    async def click(self, sb, selector):
        raise NotImplementedError

    async def type(self, sb, selector, text):
        raise NotImplementedError

    async def screenshot(self, sb) -> bytes:
        return await (await self._page(sb)).screenshot(type="png")

    async def close(self, sb):
        entry = self._pages.pop(sb.sandbox_id, None)
        if entry:
            await entry[0].close()
        if not self._pages and self._pw:
            await self._pw.stop()
            self._pw = None


def _client():
    try:
        import docker

        c = docker.from_env()
        c.ping()
        c.images.get("kairos/sandbox-browser:latest")
        c.images.get("kairos/sandbox-base:latest")
        if not c.containers.list(filters={"name": "vendor-docs", "status": "running"}):
            raise RuntimeError("vendor-docs isn't running (docker compose ... up -d vendor-docs)")
        return c
    except Exception as e:
        pytest.skip(f"browser sandbox unavailable: {str(e)[:120]}")


def test_browser_open_in_real_sandbox(tmp_path):
    client = _client()
    mgr = DockerSandboxManager(tmp_path / "ws", client=client)
    bus, artifacts = InMemoryEventBus(), FsArtifactStore(tmp_path / "artifacts")
    services = ServiceBundle(settings=Settings(), event_bus=bus, sandbox=mgr, browser=ReferenceDriver(), artifacts=artifacts)
    pool = SandboxPool(services)
    backend = BrowserBackend(services, pool)
    allow = {"network_allow": ["vendor-docs:80"]}

    def inv(url: str) -> ToolInvocation:
        return ToolInvocation(invocation_id=new_id("INV"), syscall_id=new_id("SC"), task_id="T-browse", pid=104,
                              tool="browser", operation="open", arguments={"url": url}, constraints=allow)

    async def go():
        denied = await backend.execute(inv("https://example.com/"))
        opened = await backend.execute(inv("http://vendor-docs/sdk-v5.html"))
        png = await artifacts.get(opened.artifacts[0]) if opened.artifacts else b""
        sandbox_ids = [s.sandbox_id for s in await mgr.list("T-browse")]
        await pool.release_task("T-browse")
        return denied, opened, png, sandbox_ids

    denied, opened, png, sandbox_ids = asyncio.run(go())
    assert denied.status == ToolResultStatus.ERROR and denied.error.code == "POLICY_DENIED"
    assert opened.status == ToolResultStatus.SUCCESS, opened.error
    assert opened.output["title"] == "PayCo SDK v5: release status"
    assert "2026-10-20" in opened.output["text"]
    assert png.startswith(b"\x89PNG") and len(png) > 1000
    assert [e.type for e in bus.history] == ["sandbox.started", "sandbox.screenshot", "sandbox.destroyed"]
    assert not client.containers.list(all=True, filters={"label": f"kairos.sandbox={sandbox_ids[0]}"})


def test_browser_sandbox_has_no_internet(tmp_path):
    """The browser container is on the internal network only, in both endpoint modes (port mode publishes through a
    relay), so nothing inside it (page subresources included) reaches the internet, while vendor-docs resolves."""
    mgr = DockerSandboxManager(tmp_path / "ws", client=_client())

    async def go():
        sb = await mgr.provision(SandboxSpec(task_id="T-egress", display=True, network=NetworkMode.ALLOWLIST,
                                             network_allow=["vendor-docs:80"]))
        try:
            internet = await mgr.exec(sb.sandbox_id, ExecRequest(command=["curl", "-sS", "-m", "5", "-o", "/dev/null", "https://1.1.1.1"]))
            internal = await mgr.exec(sb.sandbox_id, ExecRequest(command=["curl", "-sS", "-m", "5", "-o", "/dev/null", "-w", "%{http_code}", "http://vendor-docs/"]))
            return sb, internet, internal
        finally:
            await mgr.destroy(sb.sandbox_id)

    sb, internet, internal = asyncio.run(go())
    assert internet.exit_code != 0, f"the browser sandbox reached the internet: {internet.stdout} {internet.stderr}"
    assert internal.stdout.strip() == "200", internal
    assert sb.endpoints["playwright"].startswith("ws://")
