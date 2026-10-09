"""Execution-layer interfaces.

PROVIDED BY P1 (Kernel & Execution): ToolExecutor, SandboxManager, ArtifactStore
PROVIDED BY P4 (Platform, Data & Demo): BrowserDriver — plugged into P1's ToolExecutor for browser.* tools

Consumer: the kernel's syscall gateway / transaction manager. Agents never call these directly.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..schema import (
    ArtifactRef,
    BrowserPage,
    ExecRequest,
    ExecResult,
    SandboxInfo,
    SandboxSpec,
    ToolInvocation,
    ToolResult,
    ToolSpec,
    VerificationResult,
)


@runtime_checkable
class ToolExecutor(Protocol):
    """Runs an already-AUTHORIZED ToolInvocation. It does not do policy; it does enforce invocation.constraints."""

    async def list_tools(self) -> list[ToolSpec]: ...
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        """Never raises for tool-level errors: returns status=error with ErrorInfo."""

    async def verify(self, invocation: ToolInvocation, result: ToolResult) -> VerificationResult:
        """Post-condition check (e.g. re-read the Jira issue and compare)."""

    async def rollback(self, invocation: ToolInvocation, result: ToolResult) -> bool:
        """Undo using result.rollback_token. Returns False if not reversible."""


@runtime_checkable
class SandboxManager(Protocol):
    async def provision(self, spec: SandboxSpec) -> SandboxInfo:
        """spec.display=True => browser image; SandboxInfo.endpoints["playwright"] must be set."""

    async def exec(self, sandbox_id: str, request: ExecRequest) -> ExecResult: ...
    async def screenshot(self, sandbox_id: str) -> bytes | None: ...
    async def destroy(self, sandbox_id: str) -> None: ...
    async def list(self, task_id: str | None = None) -> list[SandboxInfo]: ...


@runtime_checkable
class ArtifactStore(Protocol):
    """artifact://<task_id>/<name>  <->  $KAIROS_DATA_DIR/artifacts/<task_id>/<name>"""

    async def put(self, task_id: str, name: str, data: bytes, content_type: str = "application/octet-stream") -> ArtifactRef: ...
    async def get(self, ref: ArtifactRef) -> bytes: ...
    async def exists(self, ref: ArtifactRef) -> bool: ...
    async def list(self, task_id: str) -> list[ArtifactRef]: ...


@runtime_checkable
class BrowserDriver(Protocol):
    """Drives the Playwright browser INSIDE a sandbox that P1's SandboxManager provisioned (spec.display=True).

    Connects to sandbox.endpoints["playwright"]. Never launches a browser on the host.
    Raises KairosError("SANDBOX_FAILED") if the endpoint is unreachable, ("TIMEOUT") on navigation timeout.
    """

    async def open(self, sandbox: SandboxInfo, url: str) -> BrowserPage: ...
    async def click(self, sandbox: SandboxInfo, selector: str) -> BrowserPage: ...
    async def type(self, sandbox: SandboxInfo, selector: str, text: str) -> BrowserPage: ...
    async def screenshot(self, sandbox: SandboxInfo) -> bytes: ...
    async def close(self, sandbox: SandboxInfo) -> None: ...
