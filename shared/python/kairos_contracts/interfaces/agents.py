"""Interfaces PROVIDED BY P3 (Agents & Models) — agent side.

Consumer: the kernel (P1). The kernel owns PIDs/state; the runtime just executes agent code.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..schema import AgentManifest, AgentResult
from .kernel import AgentContext


@runtime_checkable
class AgentRegistry(Protocol):
    """The 'package manager' for agents: agents/manifests/*.yaml."""

    async def list(self) -> list[AgentManifest]: ...
    async def get(self, name: str) -> AgentManifest:
        """Raises KairosError("AGENT_NOT_FOUND")."""

    async def match(self, goal: str, limit: int = 3) -> list[AgentManifest]:
        """Best candidate agents for a subtask (by `handles`, description, embeddings...)."""


@runtime_checkable
class AgentRuntime(Protocol):
    """Loads an agent class (custom or NOOA) and runs it against an AgentContext.

    Contract with the kernel:
      * run() is awaited inside an asyncio.Task the kernel owns; cancelling that task == ai-kill.
      * run() returns AgentResult for normal completion AND for handled failures (status=failed);
        it only raises for bugs. The kernel maps exceptions to FAILED + retry policy.
      * The runtime never changes process state itself — the kernel does, around run().
    """

    async def run(self, manifest: AgentManifest, goal: str, ctx: AgentContext) -> AgentResult: ...

    async def restore(self, manifest: AgentManifest, goal: str, ctx: AgentContext, state: dict[str, Any]) -> AgentResult:
        """Resume from a checkpoint's agent_state (ai-resume). May simply re-run if unsupported."""
