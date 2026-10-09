"""`fs` tool backend: file operations jailed to the task workspace (<data_dir>/workspaces/<task_id>, mounted at
/workspace inside sandboxes). Writes are reversible."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    Risk,
    ToolInvocation,
    ToolOperation,
    ToolResult,
    ToolResultStatus,
    ToolSpec,
    ToolTransport,
    VerificationCheck,
    VerificationResult,
)

from ..tools.base import err, ok, require, status_check, token

MAX_BYTES = 5 * 1024 * 1024

SPEC = ToolSpec(name="fs", description="Task workspace file operations", transport=ToolTransport.NATIVE, operations=[
    ToolOperation(name="read_file", capability="fs.read", description="Read a workspace file",
                  input_schema={"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}),
    ToolOperation(name="list_dir", capability="fs.read", description="List a workspace directory",
                  input_schema={"type": "object", "properties": {"path": {"type": "string"}}}),
    ToolOperation(name="write_file", capability="fs.write", description="Write a workspace file",
                  input_schema={"type": "object", "required": ["path", "content"], "properties": {
                      "path": {"type": "string"}, "content": {"type": "string"}}}, risk=Risk.LOW, reversible=True),
])


class FsBackend:
    name = "fs"

    def __init__(self, workspaces_root: Path) -> None:
        self.root = Path(workspaces_root)
        self._undo: dict[str, tuple[Path, bytes | None]] = {}

    def spec(self) -> ToolSpec:
        return SPEC

    def _path(self, task_id: str, rel: str) -> Path:
        base = (self.root / task_id).resolve()
        rel = rel.replace("\\", "/").removeprefix("/workspace").lstrip("/")
        path = (base / rel).resolve()
        if not path.is_relative_to(base):
            raise KairosError("CAPABILITY_DENIED", f"path escapes the workspace: {rel!r}")
        return path

    async def execute(self, inv: ToolInvocation) -> ToolResult:
        a = inv.arguments
        try:
            if inv.operation == "read_file":
                require(a, "path")
                p = self._path(inv.task_id, a["path"])
                if not p.is_file():
                    raise KairosError("NOT_FOUND", a["path"])
                return ok(inv, {"path": a["path"], "content": await asyncio.to_thread(p.read_text, encoding="utf-8")})
            if inv.operation == "list_dir":
                p = self._path(inv.task_id, a.get("path", "."))
                entries = sorted(f"{c.name}/" if c.is_dir() else c.name for c in p.iterdir()) if p.is_dir() else []
                return ok(inv, {"path": a.get("path", "."), "entries": entries})
            if inv.operation == "write_file":
                return await self._write(inv, a)
            return err(inv, "NOT_FOUND", f"unknown fs operation {inv.operation}")
        except KairosError as e:
            return err(inv, e.code, e.message)
        except OSError as e:
            return err(inv, "TOOL_FAILED", str(e))

    async def _write(self, inv: ToolInvocation, a: dict[str, Any]) -> ToolResult:
        require(a, "path", "content")
        data = str(a["content"]).encode()
        if len(data) > MAX_BYTES:
            raise KairosError("BAD_REQUEST", f"file larger than {MAX_BYTES} bytes")
        p = self._path(inv.task_id, a["path"])
        previous = p.read_bytes() if p.is_file() else None

        def write() -> None:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

        await asyncio.to_thread(write)
        rb = token()
        self._undo[rb] = (p, previous)
        return ok(inv, {"path": a["path"], "bytes": len(data)}, rollback_token=rb)

    async def verify(self, inv: ToolInvocation, result: ToolResult) -> VerificationResult:
        if result.status != ToolResultStatus.SUCCESS or inv.operation != "write_file":
            return status_check(inv, result)
        p = self._path(inv.task_id, inv.arguments["path"])
        same = p.is_file() and p.read_bytes() == str(inv.arguments["content"]).encode()
        return status_check(inv, result, [VerificationCheck(name="content_written", passed=same)])

    async def rollback(self, inv: ToolInvocation, result: ToolResult) -> bool:
        undo = self._undo.pop(result.rollback_token or "", None)
        if undo is None:
            return False
        path, previous = undo
        if previous is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(previous)
        return True
