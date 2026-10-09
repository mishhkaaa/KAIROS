"""ToolExecutor: dispatches AUTHORIZED invocations to backends; never raises for tool-level failures."""
from __future__ import annotations

import asyncio
import logging

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    ErrorInfo,
    Event,
    EventType,
    ToolInvocation,
    ToolResult,
    ToolSpec,
    VerificationCheck,
    VerificationResult,
)

from .base import ToolBackend, err, error_result, ok

log = logging.getLogger("kairos.execution.executor")


class Executor:
    def __init__(self, backends: list[ToolBackend], event_bus=None, on_task_end=None) -> None:
        self.backends = {b.name: b for b in backends}
        self._on_task_end = on_task_end
        if event_bus is not None and on_task_end is not None:
            event_bus.subscribe("task.*", self._task_event)

    async def _task_event(self, event: Event) -> None:
        ended = event.type in (EventType.TASK_COMPLETED, EventType.TASK_FAILED) or (
            event.type == EventType.TASK_STATUS_CHANGED and event.payload.get("new") == "cancelled")
        if ended and event.task_id:
            await self._on_task_end(event.task_id)

    async def list_tools(self) -> list[ToolSpec]:
        specs = []
        for b in self.backends.values():
            discover = getattr(b, "discover", None)
            if discover is not None:  # e.g. MCP servers: tools are only known after connecting
                try:
                    await discover()
                except Exception as e:
                    log.error("tool backend %s unavailable: %s", b.name, e)
                    continue
            specs.append(b.spec())
        return specs

    async def aclose(self) -> None:
        for b in self.backends.values():
            close = getattr(b, "aclose", None)
            if close is not None:
                await close()

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        backend = self.backends.get(invocation.tool)
        if backend is None:
            return err(invocation, "NOT_FOUND", f"unknown tool {invocation.tool}")
        if invocation.dry_run:
            return ok(invocation, {"dry_run": True, "tool": invocation.tool, "operation": invocation.operation})
        try:
            return await asyncio.wait_for(backend.execute(invocation), invocation.timeout_s)
        except TimeoutError:
            return err(invocation, "TIMEOUT", f"{invocation.tool}.{invocation.operation} exceeded {invocation.timeout_s}s")
        except KairosError as e:
            return err(invocation, e.code, e.message)
        except Exception as e:
            log.exception("backend %s crashed", invocation.tool)
            return error_result(invocation, ErrorInfo(code="TOOL_FAILED", message=f"{type(e).__name__}: {e}", retriable=True))

    async def verify(self, invocation: ToolInvocation, result: ToolResult) -> VerificationResult:
        backend = self.backends.get(invocation.tool)
        try:
            if backend is None:
                raise KairosError("NOT_FOUND", invocation.tool)
            return await backend.verify(invocation, result)
        except Exception as e:
            log.exception("verify crashed")
            return VerificationResult(invocation_id=invocation.invocation_id, passed=False,
                                      checks=[VerificationCheck(name="verify", passed=False, detail=str(e))])

    async def rollback(self, invocation: ToolInvocation, result: ToolResult) -> bool:
        backend = self.backends.get(invocation.tool)
        try:
            return bool(backend and await backend.rollback(invocation, result))
        except Exception:
            log.exception("rollback crashed")
            return False
