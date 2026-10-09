"""Backends that run inside task sandboxes: `browser` (via P4's BrowserDriver) and `sandbox` (command exec).

One sandbox per (task, kind), provisioned lazily and destroyed when the task ends (the executor listens for
task.completed / task.failed / task.status_changed→cancelled).
"""
from __future__ import annotations

import logging
from typing import Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    Event,
    EventType,
    ExecRequest,
    NetworkMode,
    Risk,
    SandboxInfo,
    SandboxSpec,
    ToolInvocation,
    ToolOperation,
    ToolResult,
    ToolSpec,
    ToolTransport,
    VerificationResult,
)
from kairos_contracts.wiring import ServiceBundle

from .base import err, network_allowed, ok, require, status_check

log = logging.getLogger("kairos.execution.sandboxed")

BROWSER_SPEC = ToolSpec(name="browser", description="Isolated browser inside a task sandbox (Playwright)",
                        transport=ToolTransport.BROWSER, operations=[
    ToolOperation(name="open", capability="browser.open", description="Open a URL; returns title, text, links + screenshot",
                  input_schema={"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}}},
                  risk=Risk.MEDIUM, requires_sandbox=True),
    ToolOperation(name="click", capability="browser.click", description="Click a CSS selector on the current page",
                  input_schema={"type": "object", "required": ["selector"], "properties": {"selector": {"type": "string"}}},
                  risk=Risk.MEDIUM, requires_sandbox=True),
    ToolOperation(name="type", capability="browser.type", description="Fill text into a CSS selector",
                  input_schema={"type": "object", "required": ["selector", "text"], "properties": {
                      "selector": {"type": "string"}, "text": {"type": "string"}}}, risk=Risk.MEDIUM, requires_sandbox=True),
])

SANDBOX_SPEC = ToolSpec(name="sandbox", description="Run a command in the task's isolated container",
                        transport=ToolTransport.SANDBOX, operations=[
    ToolOperation(name="exec", capability="sandbox.exec", description="Run a command in /workspace (no network)",
                  input_schema={"type": "object", "required": ["command"], "properties": {
                      "command": {"type": "array", "items": {"type": "string"}}, "timeout_s": {"type": "integer"}}},
                  risk=Risk.HIGH, requires_sandbox=True),
])


class SandboxPool:
    def __init__(self, services: ServiceBundle) -> None:
        self.services = services
        self.by_key: dict[tuple[str, str], SandboxInfo] = {}

    async def get(self, key: tuple[str, str], spec: SandboxSpec) -> SandboxInfo:
        if key not in self.by_key:
            if self.services.sandbox is None:
                raise KairosError("SANDBOX_FAILED", "no sandbox manager wired")
            info = await self.services.sandbox.provision(spec)
            self.by_key[key] = info
            await self._publish(EventType.SANDBOX_STARTED, spec.task_id, spec.pid,
                                {"sandbox_id": info.sandbox_id, "image": spec.image if not spec.display else "browser"})
        return self.by_key[key]

    async def release_task(self, task_id: str) -> None:
        for key in [k for k in self.by_key if k[0] == task_id]:
            info = self.by_key.pop(key)
            try:
                if key[1] == "browser" and self.services.browser is not None:
                    await self.services.browser.close(info)
                await self.services.sandbox.destroy(info.sandbox_id)
                await self._publish(EventType.SANDBOX_DESTROYED, task_id, info.spec.pid, {"sandbox_id": info.sandbox_id})
            except Exception:
                log.exception("destroying sandbox %s failed", info.sandbox_id)

    async def _publish(self, type_: EventType, task_id: str, pid: int | None, payload: dict[str, Any]) -> None:
        if self.services.event_bus is not None:
            await self.services.event_bus.publish(Event(type=type_, source="execution.sandbox", task_id=task_id, pid=pid,
                                                         payload=payload))


class BrowserBackend:
    name = "browser"

    def __init__(self, services: ServiceBundle, pool: SandboxPool) -> None:
        self.services, self.pool = services, pool
        self._shots = 0

    def spec(self) -> ToolSpec:
        return BROWSER_SPEC

    async def execute(self, inv: ToolInvocation) -> ToolResult:
        driver = self.services.browser
        if driver is None:
            return err(inv, "SANDBOX_FAILED", "no browser driver wired")
        a = inv.arguments
        try:
            if inv.operation == "open":
                require(a, "url")
                if not a["url"].startswith(("http://", "https://")):
                    raise KairosError("BAD_REQUEST", "only http(s) URLs")
                if not network_allowed(a["url"], inv.constraints):
                    raise KairosError("POLICY_DENIED", f"{a['url']} is not in the network allowlist")
            allow = list(inv.constraints.get("network_allow", []))
            web = "*" in allow  # the public internet: a separate sandbox on the web network, never the internal one
            spec = SandboxSpec(task_id=inv.task_id, pid=inv.pid, display=True, network=NetworkMode.ALLOWLIST,
                               network_allow=["*"] if web else allow, timeout_s=900)
            sandbox = await self.pool.get((inv.task_id, "web" if web else "browser"), spec)
            if inv.operation == "open":
                page = await driver.open(sandbox, a["url"])
            elif inv.operation == "click":
                require(a, "selector")
                page = await driver.click(sandbox, a["selector"])
            elif inv.operation == "type":
                require(a, "selector", "text")
                page = await driver.type(sandbox, a["selector"], a["text"])
            else:
                return err(inv, "NOT_FOUND", f"unknown browser operation {inv.operation}")
            artifacts = []
            if self.services.artifacts is not None:
                self._shots += 1
                png = await driver.screenshot(sandbox)
                ref = await self.services.artifacts.put(inv.task_id, f"screenshots/{self._shots:03d}.png", png, "image/png")
                artifacts.append(ref)
                await self.pool._publish(EventType.SANDBOX_SCREENSHOT, inv.task_id, inv.pid,
                                         {"sandbox_id": sandbox.sandbox_id, "artifact": ref})
            return ok(inv, {**page.model_dump(mode="json"), "sandbox_id": sandbox.sandbox_id}, artifacts=artifacts)
        except KairosError as e:
            return err(inv, e.code, e.message)

    async def verify(self, inv: ToolInvocation, result: ToolResult) -> VerificationResult:
        return status_check(inv, result)

    async def rollback(self, inv: ToolInvocation, result: ToolResult) -> bool:
        return False  # browsing is read-only from the organization's point of view; nothing to undo


class SandboxExecBackend:
    name = "sandbox"

    def __init__(self, services: ServiceBundle, pool: SandboxPool) -> None:
        self.services, self.pool = services, pool

    def spec(self) -> ToolSpec:
        return SANDBOX_SPEC

    async def execute(self, inv: ToolInvocation) -> ToolResult:
        a = inv.arguments
        try:
            if inv.operation != "exec":
                return err(inv, "NOT_FOUND", f"unknown sandbox operation {inv.operation}")
            require(a, "command")
            if not isinstance(a["command"], list) or not all(isinstance(x, str) for x in a["command"]):
                raise KairosError("BAD_REQUEST", "command must be a list of strings")
            sandbox = await self.pool.get((inv.task_id, "exec"), SandboxSpec(task_id=inv.task_id, pid=inv.pid,
                                                                             network=NetworkMode.NONE))
            res = await self.services.sandbox.exec(sandbox.sandbox_id,
                                                   ExecRequest(command=a["command"], timeout_s=int(a.get("timeout_s", 120))))
            return ok(inv, {**res.model_dump(mode="json"), "sandbox_id": sandbox.sandbox_id})
        except KairosError as e:
            return err(inv, e.code, e.message)

    async def verify(self, inv: ToolInvocation, result: ToolResult) -> VerificationResult:
        from kairos_contracts.schema import VerificationCheck

        exit_ok = result.output.get("exit_code", 1) == 0
        return status_check(inv, result, [VerificationCheck(name="exit_code_0", passed=exit_ok,
                                                            detail=str(result.output.get("exit_code")))])

    async def rollback(self, inv: ToolInvocation, result: ToolResult) -> bool:
        return False
