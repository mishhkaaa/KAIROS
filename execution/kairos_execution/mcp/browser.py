"""The `browser` tool served by the Playwright MCP server, in place of the Playwright driver backend.

Owner: P1 — Kernel & Execution

Off by default. Enabled by a server with `browser: true` in the file named by KAIROS_MCP_CONFIG (see
execution/mcp.browser.example.yaml): the server runs in the `kairos/sandbox-browser-mcp` image with `docker run -i`, on
the internal sandbox network (it reaches only vendor-docs), read-only, as uid 10001, with --allowed-origins. Agents keep
calling `browser.open` (and `browser.click` / `browser.type`, which need approval): same capabilities, same policies.

open(url): the kernel's network allowlist first, then MCP browser_navigate, browser_snapshot (the page text: an
accessibility snapshot) and browser_take_screenshot (stored as an artifact, announced as sandbox.screenshot).
"""
from __future__ import annotations

import base64
import logging
import re
from typing import Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    Event,
    EventType,
    ToolInvocation,
    ToolOperation,
    ToolResult,
    ToolSpec,
    ToolTransport,
    VerificationResult,
)
from kairos_contracts.schema.common import Risk
from kairos_contracts.wiring import ServiceBundle

from ..tools.base import err, network_allowed, ok, require, status_check
from .backend import McpBackend, McpServerConfig

log = logging.getLogger("kairos.execution.mcp.browser")

MAX_TEXT = 20_000

SPEC = ToolSpec(name="browser", description="Isolated browser (Playwright MCP server in a sandbox)", transport=ToolTransport.MCP,
                operations=[
    ToolOperation(name="open", capability="browser.open", description="Open a URL and return title + page text",
                  input_schema={"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}}},
                  risk=Risk.MEDIUM, requires_sandbox=True),
    ToolOperation(name="click", capability="browser.click", description="Click an element (ref from the page snapshot)",
                  input_schema={"type": "object", "required": ["ref"], "properties": {
                      "ref": {"type": "string"}, "element": {"type": "string"}}}, risk=Risk.MEDIUM, requires_sandbox=True),
    ToolOperation(name="type", capability="browser.type", description="Type into an element (ref from the page snapshot)",
                  input_schema={"type": "object", "required": ["ref", "text"], "properties": {
                      "ref": {"type": "string"}, "element": {"type": "string"}, "text": {"type": "string"}}},
                  risk=Risk.MEDIUM, requires_sandbox=True),
])


def _texts(res: Any) -> list[str]:
    return [c.text for c in res.content if getattr(c, "type", "") == "text"]


def _image(res: Any) -> bytes | None:
    for c in res.content:
        if getattr(c, "type", "") == "image" and getattr(c, "data", None):
            return base64.b64decode(c.data)
    return None


class McpBrowserBackend:
    name = "browser"

    def __init__(self, config: McpServerConfig, services: ServiceBundle, mcp: McpBackend | None = None) -> None:
        self.mcp = mcp or McpBackend(config)
        self.services = services
        self._shots = 0

    def spec(self) -> ToolSpec:
        return SPEC

    async def _call(self, tool: str, args: dict[str, Any]) -> Any:
        res = await self.mcp.call(tool, args)
        if res.is_error:
            raise KairosError("TOOL_FAILED", "; ".join(_texts(res))[:500] or f"MCP {tool} reported an error")
        return res

    async def execute(self, inv: ToolInvocation) -> ToolResult:
        a = inv.arguments
        try:
            if inv.operation == "open":
                require(a, "url")
                if not str(a["url"]).startswith(("http://", "https://")):
                    raise KairosError("BAD_REQUEST", "only http(s) URLs")
                if not network_allowed(a["url"], inv.constraints):
                    raise KairosError("POLICY_DENIED", f"{a['url']} is not in the network allowlist")
                await self._call("browser_navigate", {"url": a["url"]})
            elif inv.operation == "click":
                require(a, "ref")
                await self._call("browser_click", {"ref": a["ref"], "element": a.get("element", a["ref"])})
            elif inv.operation == "type":
                require(a, "ref", "text")
                await self._call("browser_type", {"ref": a["ref"], "element": a.get("element", a["ref"]), "text": a["text"]})
            else:
                return err(inv, "NOT_FOUND", f"unknown browser operation {inv.operation}")
            snapshot = "\n".join(_texts(await self._call("browser_snapshot", {})))
            url = (re.search(r"Page URL:\s*(\S+)", snapshot) or [None, a.get("url", "")])[1]
            title = (re.search(r"Page Title:\s*(.+)", snapshot) or [None, ""])[1].strip()
            artifacts = await self._screenshot(inv)
            return ok(inv, {"url": url, "title": title, "text": snapshot[:MAX_TEXT], "transport": "mcp"}, artifacts=artifacts)
        except KairosError as e:
            return err(inv, e.code, e.message)
        except TimeoutError:
            return err(inv, "TIMEOUT", f"the browser did not answer within {self.mcp.config.timeout_s:g}s")
        except Exception as e:
            return err(inv, "SANDBOX_FAILED", f"MCP browser failed: {e}")

    async def _screenshot(self, inv: ToolInvocation) -> list[str]:
        if self.services.artifacts is None:
            return []
        png = _image(await self._call("browser_take_screenshot", {"type": "png"}))
        if png is None:
            return []
        self._shots += 1
        ref = await self.services.artifacts.put(inv.task_id, f"screenshots/{self._shots:03d}.png", png, "image/png")
        if self.services.event_bus is not None:
            await self.services.event_bus.publish(Event(type=EventType.SANDBOX_SCREENSHOT, source="execution.mcp.browser",
                                                        task_id=inv.task_id, pid=inv.pid,
                                                        payload={"sandbox_id": f"mcp-{self.mcp.name}", "artifact": ref}))
        return [ref]

    async def verify(self, inv: ToolInvocation, result: ToolResult) -> VerificationResult:
        return status_check(inv, result)

    async def rollback(self, inv: ToolInvocation, result: ToolResult) -> bool:
        return False  # browsing is read-only from the organization's point of view

    async def aclose(self) -> None:
        await self.mcp.aclose()
