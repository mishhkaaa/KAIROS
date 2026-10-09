"""MCP adapter: exposes the tools of configured MCP servers as KAIROS tools (blueprint §26).

MCP is the transport, not the security boundary: every call still goes syscall -> policy -> approval -> here.
Configure servers in the YAML file named by KAIROS_MCP_CONFIG (see execution/mcp.example.yaml):

    servers:
      - name: notes                 # tool name agents use in SyscallRequest.tool
        command: python
        args: [path/to/server.py]
        capability: mcp.call        # capability every operation requires (policies must allow it)
        risk: medium
        timeout_s: 60

One persistent stdio session per server, owned by a worker task (the MCP client's context managers must be
entered and exited in the same task).
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import yaml
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    Risk,
    ToolInvocation,
    ToolOperation,
    ToolResult,
    ToolSpec,
    ToolTransport,
    VerificationResult,
)
from pydantic import BaseModel, Field

from ..tools.base import err, ok, status_check

log = logging.getLogger("kairos.execution.mcp")


class McpServerConfig(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | None = None
    capability: str = "mcp.call"
    risk: Risk = Risk.MEDIUM
    timeout_s: float = 60.0
    browser: bool = False  # a Playwright MCP server that serves the `browser` tool (McpBrowserBackend) instead


def load_mcp_config(path: str | Path | None = None) -> list[McpServerConfig]:
    path = path or os.getenv("KAIROS_MCP_CONFIG")
    if not path or not Path(path).is_file():
        return []
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return [McpServerConfig.model_validate(s) for s in raw.get("servers", [])]


class McpBackend:
    def __init__(self, config: McpServerConfig) -> None:
        self.config = config
        self.name = config.name
        self._tools: list[Any] = []
        self._queue: asyncio.Queue | None = None
        self._ready: asyncio.Event | None = None
        self._worker: asyncio.Task | None = None
        self._error: BaseException | None = None

    # ------------------------------------------------------------------ session worker
    async def discover(self) -> None:
        if self._worker is None or self._worker.done():
            self._queue, self._ready, self._error = asyncio.Queue(), asyncio.Event(), None
            self._worker = asyncio.create_task(self._run(), name=f"mcp-{self.name}")
        try:
            await asyncio.wait_for(self._ready.wait(), 30)
        except TimeoutError as e:
            raise KairosError("TOOL_FAILED", f"MCP server {self.name} did not start within 30s") from e
        if self._error is not None:
            raise KairosError("TOOL_FAILED", f"MCP server {self.name} failed: {self._error}")

    async def _run(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=self.config.command, args=self.config.args, env=self.config.env,
                                       cwd=self.config.cwd)
        try:
            async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
                await session.initialize()
                self._tools = list((await session.list_tools()).tools)
                self._ready.set()
                while True:
                    item = await self._queue.get()
                    if item is None:
                        return
                    fut, tool, args = item
                    try:
                        res = await session.call_tool(tool, args, read_timeout_seconds=self.config.timeout_s)
                        if not fut.done():
                            fut.set_result(res)
                    except Exception as e:
                        if not fut.done():
                            fut.set_exception(e)
        except Exception as e:  # includes ExceptionGroup from the client's task group
            log.error("MCP server %s stopped: %s", self.name, e)
            self._error = e
            self._ready.set()

    async def aclose(self) -> None:
        if self._worker is not None and not self._worker.done():
            await self._queue.put(None)
            try:
                await asyncio.wait_for(self._worker, 10)
            except (TimeoutError, Exception):
                self._worker.cancel()

    # ------------------------------------------------------------------ ToolBackend
    def spec(self) -> ToolSpec:
        ops = [ToolOperation(name=t.name, capability=self.config.capability, description=t.description or t.name,
                             input_schema=dict(t.input_schema or {}), output_schema=dict(t.output_schema or {}),
                             risk=self.config.risk) for t in self._tools]
        return ToolSpec(name=self.name, description=f"MCP server {self.name}", transport=ToolTransport.MCP, operations=ops)

    async def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        """One MCP tool call; the raw result (text and image content). Raises KairosError, TimeoutError."""
        await self.discover()
        if tool not in {t.name for t in self._tools}:
            raise KairosError("NOT_FOUND", f"MCP server {self.name} has no tool {tool}")
        fut = asyncio.get_running_loop().create_future()
        await self._queue.put((fut, tool, dict(arguments)))
        return await asyncio.wait_for(fut, self.config.timeout_s)

    async def execute(self, inv: ToolInvocation) -> ToolResult:
        try:
            res = await self.call(inv.operation, inv.arguments)
        except KairosError as e:
            return err(inv, e.code, e.message)
        except TimeoutError:
            return err(inv, "TIMEOUT", f"MCP tool {self.name}.{inv.operation} exceeded {self.config.timeout_s}s")
        except Exception as e:
            return err(inv, "TOOL_FAILED", f"MCP call failed: {e}")
        texts = [c.text for c in res.content if getattr(c, "type", "") == "text"]
        if res.is_error:
            return err(inv, "TOOL_FAILED", "; ".join(texts) or "MCP tool reported an error")
        return ok(inv, {"content": texts, "structured": res.structured_content})

    async def verify(self, inv: ToolInvocation, result: ToolResult) -> VerificationResult:
        return status_check(inv, result)

    async def rollback(self, inv: ToolInvocation, result: ToolResult) -> bool:
        return False  # MCP has no generic undo
