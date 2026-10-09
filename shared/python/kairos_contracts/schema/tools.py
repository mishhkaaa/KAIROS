"""Tool executors (MCP / API / browser / file) and execution sandboxes."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from .common import ArtifactRef, Capability, Contract, ErrorInfo, Pid, Risk, TaskId, utcnow


class ToolTransport(StrEnum):
    NATIVE = "native"      # python implementation (fs, mock jira)
    MCP = "mcp"            # MCP server
    HTTP = "http"          # REST / GraphQL
    BROWSER = "browser"    # Playwright in a sandbox
    SANDBOX = "sandbox"    # arbitrary command in a container


class ToolOperation(Contract):
    name: str
    capability: Capability
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema")
    output_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema")
    risk: Risk = Risk.LOW
    reversible: bool = False
    requires_sandbox: bool = False


class ToolSpec(Contract):
    name: str
    description: str
    transport: ToolTransport
    operations: list[ToolOperation]


class Mount(Contract):
    source: str = Field(description="Host path")
    target: str = Field(description="Path inside the sandbox")
    read_only: bool = True


class NetworkMode(StrEnum):
    NONE = "none"
    ALLOWLIST = "allowlist"


class SandboxSpec(Contract):
    image: str = "kairos/sandbox-base:latest"
    task_id: TaskId
    pid: Pid | None = None
    mounts: list[Mount] = Field(default_factory=list)
    network: NetworkMode = NetworkMode.NONE
    network_allow: list[str] = Field(default_factory=list, description="host:port entries")
    cpu: float = 1.0
    memory_mb: int = 1024
    gpu: bool = False
    timeout_s: int = 300
    env: dict[str, str] = Field(default_factory=dict)
    display: bool = Field(False, description="Start a virtual display (browser / computer use)")


class SandboxStatus(StrEnum):
    PROVISIONING = "provisioning"
    RUNNING = "running"
    STOPPED = "stopped"
    DESTROYED = "destroyed"
    FAILED = "failed"


class SandboxInfo(Contract):
    sandbox_id: str
    status: SandboxStatus
    spec: SandboxSpec
    created_at: datetime = Field(default_factory=utcnow)
    live_view_url: str | None = Field(None, description="noVNC / screenshot stream for the UI")
    endpoints: dict[str, str] = Field(
        default_factory=dict, description='Services exposed by the sandbox, e.g. {"playwright": "ws://172.18.0.5:3000/"}'
    )


class BrowserPage(Contract):
    """What the BrowserDriver (P4) returns after every browser action."""

    url: str
    title: str = ""
    text: str = Field("", description="Visible text, truncated to ~20k chars")
    links: list[str] = Field(default_factory=list)


class ExecRequest(Contract):
    command: list[str]
    workdir: str = "/workspace"
    stdin: str | None = None
    timeout_s: int = 120


class ExecResult(Contract):
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0


class ToolInvocation(Contract):
    """Built by the kernel from an ALLOWED/approved SyscallRequest. Agents never create these."""

    invocation_id: str
    syscall_id: str
    task_id: TaskId
    pid: Pid
    tool: str
    operation: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    arguments_ref: ArtifactRef | None = None
    constraints: dict[str, Any] = Field(default_factory=dict, description="From PolicyDecision.constraints")
    timeout_s: int = 120
    dry_run: bool = False


class ToolResultStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ToolResult(Contract):
    invocation_id: str
    status: ToolResultStatus
    output: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    logs: str = ""
    rollback_token: str | None = Field(None, description="Opaque; pass back to ToolExecutor.rollback")
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime = Field(default_factory=utcnow)
    error: ErrorInfo | None = None


class VerificationCheck(Contract):
    name: str
    passed: bool
    detail: str = ""


class VerificationResult(Contract):
    invocation_id: str
    passed: bool
    checks: list[VerificationCheck] = Field(default_factory=list)
