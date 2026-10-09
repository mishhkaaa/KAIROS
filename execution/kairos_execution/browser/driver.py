"""PlaywrightDriver: drives the browser that runs INSIDE a sandbox (playwright run-server). Never launches a host browser."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import BrowserPage, SandboxInfo
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright.async_api import Error as PWError
from playwright.async_api import TimeoutError as PWTimeout

log = logging.getLogger("kairos.execution.browser.driver")

MAX_TEXT = 20_000
MAX_LINKS = 100
# Docker's default /dev/shm is 64 MB and crashes Chromium; run-server applies these launch options per connection.
_LAUNCH_HEADERS = {"x-playwright-launch-options": json.dumps({"args": ["--disable-dev-shm-usage"]})}
_SNAPSHOT_JS = """() => ({
  text: document.body ? document.body.innerText : "",
  links: Array.from(document.querySelectorAll("a[href]"), a => a.href),
})"""


@dataclass
class _Session:
    browser: Browser
    context: BrowserContext
    page: Page


class PlaywrightDriver:
    def __init__(self, nav_timeout_ms: int = 15_000, action_timeout_ms: int = 5_000, connect_timeout_s: float = 15.0):
        self.nav_timeout_ms = nav_timeout_ms
        self.action_timeout_ms = action_timeout_ms
        self.connect_timeout_s = connect_timeout_s
        self._pw: Playwright | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sessions: dict[str, _Session] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _check_loop(self) -> None:
        # Playwright objects are bound to the loop that created them (tests call asyncio.run per test).
        loop = asyncio.get_running_loop()
        if loop is not self._loop:
            self._loop, self._pw, self._sessions, self._locks = loop, None, {}, {}

    async def _connect(self, sb: SandboxInfo) -> _Session:
        endpoint = sb.endpoints.get("playwright")
        if not endpoint:
            raise KairosError("SANDBOX_FAILED", f"sandbox {sb.sandbox_id} has no playwright endpoint")
        if self._pw is None:
            self._pw = await async_playwright().start()
        deadline = time.monotonic() + self.connect_timeout_s
        while True:
            remaining_ms = max((deadline - time.monotonic()) * 1000, 1000)
            try:
                browser = await self._pw.chromium.connect(endpoint, timeout=remaining_ms, headers=_LAUNCH_HEADERS)
                break
            except PWError as e:  # run-server needs a moment after the container starts
                if time.monotonic() >= deadline:
                    raise KairosError("SANDBOX_FAILED", f"cannot connect to {endpoint}: {e.message}") from e
                await asyncio.sleep(0.5)
        try:
            context = await browser.new_context(viewport={"width": 1280, "height": 800}, accept_downloads=False,
                                                service_workers="block")
            context.set_default_timeout(self.action_timeout_ms)
            context.set_default_navigation_timeout(self.nav_timeout_ms)
            page = await context.new_page()
        except PWError as e:
            await browser.close()
            raise KairosError("SANDBOX_FAILED", f"cannot open a page in sandbox {sb.sandbox_id}: {e.message}") from e
        log.info("connected to browser in sandbox %s", sb.sandbox_id)
        return _Session(browser, context, page)

    async def _session(self, sb: SandboxInfo) -> _Session:
        self._check_loop()
        async with self._locks.setdefault(sb.sandbox_id, asyncio.Lock()):
            s = self._sessions.get(sb.sandbox_id)
            if s is None or not s.browser.is_connected() or s.page.is_closed():
                s = self._sessions[sb.sandbox_id] = await self._connect(sb)
            return s

    def _error(self, sb: SandboxInfo, s: _Session, what: str, e: PWError) -> KairosError:
        if isinstance(e, PWTimeout):
            return KairosError("TIMEOUT", f"{what} timed out: {e.message}")
        if not s.browser.is_connected():
            self._sessions.pop(sb.sandbox_id, None)
            return KairosError("SANDBOX_FAILED", f"browser in sandbox {sb.sandbox_id} disconnected during {what}")
        return KairosError("TOOL_FAILED", f"{what} failed: {e.message}")

    async def _snapshot(self, page: Page) -> BrowserPage:
        data = await page.evaluate(_SNAPSHOT_JS)
        links: list[str] = []
        for href in data.get("links") or []:
            if href.startswith(("http://", "https://")) and href not in links:
                links.append(href)
                if len(links) == MAX_LINKS:
                    break
        return BrowserPage(url=page.url, title=await page.title(), text=(data.get("text") or "")[:MAX_TEXT], links=links)

    async def _settle(self, page: Page) -> None:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=self.action_timeout_ms)
        except PWTimeout:
            pass

    async def open(self, sandbox: SandboxInfo, url: str) -> BrowserPage:
        if urlsplit(url).scheme not in ("http", "https"):
            raise KairosError("BAD_REQUEST", f"only http(s) URLs can be opened, got {url!r}")
        s = await self._session(sandbox)
        try:
            await s.page.goto(url, wait_until="domcontentloaded")
            return await self._snapshot(s.page)
        except PWError as e:
            raise self._error(sandbox, s, f"navigation to {url}", e) from e

    async def click(self, sandbox: SandboxInfo, selector: str) -> BrowserPage:
        s = await self._session(sandbox)
        try:
            await s.page.click(selector)
            await self._settle(s.page)
            return await self._snapshot(s.page)
        except PWError as e:
            raise self._error(sandbox, s, f"click {selector!r}", e) from e

    async def type(self, sandbox: SandboxInfo, selector: str, text: str) -> BrowserPage:
        s = await self._session(sandbox)
        try:
            await s.page.fill(selector, text)
            return await self._snapshot(s.page)
        except PWError as e:
            raise self._error(sandbox, s, f"type into {selector!r}", e) from e

    async def screenshot(self, sandbox: SandboxInfo) -> bytes:
        s = await self._session(sandbox)
        try:
            return await s.page.screenshot(type="png")
        except PWError as e:
            raise self._error(sandbox, s, "screenshot", e) from e

    async def close(self, sandbox: SandboxInfo) -> None:
        self._check_loop()
        self._locks.pop(sandbox.sandbox_id, None)
        s = self._sessions.pop(sandbox.sandbox_id, None)
        if s is not None:
            for closer in (s.context.close, s.browser.close):
                try:
                    await closer()
                except PWError:
                    pass
        if not self._sessions and self._pw is not None:  # no open sandboxes: stop the local Playwright driver process
            pw, self._pw = self._pw, None
            await pw.stop()
