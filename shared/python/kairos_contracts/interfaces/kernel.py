"""Interfaces PROVIDED BY P1 (Kernel & Execution).

- EventBus      — used by everyone to publish/subscribe events
- PolicyEngine  — used internally by the kernel; P2's UI renders its decisions
- AuditLog      — kernel-owned journal; read by the UI via the gateway
- AgentContext  — THE agent ABI. The kernel gives one to every running agent (P3 codes against it)
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from ..schema import (
    A2AMessage,
    AgentManifest,
    AgentResult,
    ArtifactRef,
    AuditEntry,
    Event,
    EvidenceSet,
    KnowledgeListing,
    KnowledgeObject,
    MemoryQuery,
    MemoryRecord,
    ModelRequest,
    ModelResponse,
    NarrationPayload,
    PolicyDecision,
    Principal,
    RunTimeline,
    SearchQuery,
    SyscallRequest,
    SyscallResult,
    UserPermissions,
)

EventHandler = Callable[[Event], Awaitable[None]]


@runtime_checkable
class Subscription(Protocol):
    def unsubscribe(self) -> None: ...


@runtime_checkable
class EventBus(Protocol):
    async def publish(self, event: Event) -> None:
        """Fire-and-forget. Must never raise because a subscriber failed."""

    def subscribe(self, pattern: str, handler: EventHandler) -> Subscription:
        """pattern is an fnmatch glob over Event.type: "task.*", "knowledge.changed", "*"."""

    def stream(self, pattern: str = "*", task_id: str | None = None) -> AsyncIterator[Event]:
        """Async iterator of matching events from now on — used by the WebSocket gateway."""


@runtime_checkable
class PolicyEngine(Protocol):
    async def evaluate(self, request: SyscallRequest, principal: Principal) -> PolicyDecision:
        """Pure decision; no side effects. Unknown capability => DENY."""

    async def reload(self) -> None:
        """Re-read policies/*.yaml and publish policy.updated."""


@runtime_checkable
class AuditLog(Protocol):
    async def append(self, entry: AuditEntry) -> AuditEntry:
        """Assigns seq (and hash when chaining is on) and persists. Returns the stored entry."""

    async def timeline(self, task_id: str) -> RunTimeline: ...


@runtime_checkable
class PermissionsProvider(Protocol):
    """Resolves what a user may do (0.11.0). The RBAC module implements it; until then a stub maps roles to permissions.
    The kernel bounds every agent a task creates by the permissions of the task's user."""

    async def resolve(self, user_id: str, org_id: str, roles: list[str] | None = None) -> UserPermissions: ...


@runtime_checkable
class AgentContext(Protocol):
    """Everything an agent may do. Agents MUST NOT import kernel/knowledge/execution modules directly.

    Every call is attributed to (task_id, pid), quota-checked, policy-checked and audited by the kernel.
    Calls raise kairos_contracts.errors.KairosError (code from catalogs/errors.yaml) on failure.
    """

    task_id: str
    pid: int
    ppid: int | None
    """Parent pid (None for the root planner) — the usual receiver of A2A evidence/results."""
    principal: Principal
    manifest: AgentManifest
    inputs: dict[str, Any]

    # --- compute
    async def llm(self, request: ModelRequest) -> ModelResponse: ...

    # --- knowledge filesystem (capability knowledge.read / knowledge.search)
    async def search(self, query: SearchQuery) -> EvidenceSet: ...
    async def read(self, path: str) -> KnowledgeObject: ...
    async def list(self, path: str) -> KnowledgeListing: ...

    # --- memory
    async def recall(self, query: MemoryQuery) -> list[MemoryRecord]: ...
    async def remember(self, record: MemoryRecord) -> str: ...

    # --- process management (capability agent.spawn)
    async def spawn(self, agent: str, goal: str, inputs: dict[str, Any] | None = None, *,
                    capabilities: list[str] | None = None, scope: list[str] | None = None, why: str | None = None) -> int:
        """Returns child pid immediately; the child runs concurrently. `agent` is a role template the caller may spawn
        (its manifest.capabilities.agents); the kernel generates the child's manifest from it. `capabilities` and `scope`
        can only narrow the template (the kernel also bounds them by the user's permissions and org policy); `why` goes
        to the audit log (0.11.0)."""

    async def wait(self, pid: int, timeout: float | None = None) -> AgentResult: ...

    # --- IPC
    async def send(self, message: A2AMessage) -> None:
        """The kernel OVERWRITES sender_pid/sender (anti-spoofing) and fills `receiver` from receiver_pid.
        Only processes of the same task can message each other."""
    async def receive(self, timeout: float | None = None) -> A2AMessage | None: ...

    # --- world actions (blocks through approval; returns DENIED/REJECTED rather than raising)
    async def syscall(self, request: SyscallRequest) -> SyscallResult: ...

    # --- artifacts
    async def put_artifact(self, name: str, data: bytes | str | dict, content_type: str = "application/json") -> ArtifactRef: ...
    async def get_artifact(self, ref: ArtifactRef) -> bytes: ...

    # --- observability / lifecycle
    async def log(self, message: str, level: str = "info", data: dict[str, Any] | None = None) -> None:
        """Emits agent.log — shown live in the UI timeline."""

    async def narrate(self, payload: NarrationPayload) -> None:
        """Emits task.understood, agent.planned or agent.thought (by payload type) for the UI's story of the run.
        The kernel stamps pid (AgentThought.pid is overwritten). Text must be a short summary written by agent code:
        never raw model chain-of-thought or retrieved document text."""

    async def checkpoint(self, state: dict[str, Any]) -> str:
        """Persist agent-defined state; returns checkpoint_id. Called by agents at safe points."""

    def cancelled(self) -> bool:
        """Agents should poll this between steps and return early when True."""
