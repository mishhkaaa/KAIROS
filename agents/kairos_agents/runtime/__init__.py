"""Agent runtime — loads and runs agent entrypoints.

Owner: P3 — Agents & Models

Contract with the kernel:
- run() is awaited inside an asyncio.Task the kernel owns; cancelling that task == ai-kill.
- run() returns AgentResult for normal completion AND handled failures (status=FAILED).
- It only raises for bugs (asyncio.CancelledError + unexpected exceptions propagate on purpose).
- The runtime never changes process state — the kernel does, around run().
"""
from __future__ import annotations

import importlib
import logging
from typing import Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import AgentFramework, AgentManifest, AgentResult, AgentResultStatus

log = logging.getLogger("kairos.agents.runtime")


class Runtime:
    """Loads agent classes via entrypoint strings and runs them against an AgentContext."""

    def _load(self, manifest: AgentManifest) -> Any:
        """Import the agent class from its entrypoint string (e.g. 'kairos_agents.library.planner:PlannerAgent')."""
        module_path, cls_name = manifest.runtime.entrypoint.split(":")
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise KairosError("AGENT_NOT_FOUND", f"Cannot import agent module {module_path}: {e}") from e

        klass = getattr(module, cls_name, None)
        if klass is None:
            raise KairosError("AGENT_NOT_FOUND", f"Class {cls_name} not found in {module_path}")

        if manifest.runtime.framework == AgentFramework.NOOA:
            try:
                from kairos_agents.adapters.nooa import wrap  # P2's stretch; optional
                return wrap(klass)
            except ImportError:
                pass  # fall back to running it as a custom agent

        return klass()

    async def run(self, manifest: AgentManifest, goal: str, ctx: Any) -> AgentResult:
        """Run the agent for the given goal. Returns AgentResult for handled failures; raises for bugs."""
        try:
            agent = self._load(manifest)
        except KairosError as e:
            return AgentResult(
                pid=ctx.pid,
                agent=manifest.name,
                status=AgentResultStatus.FAILED,
                summary=f"{manifest.name} could not be loaded: {e.message}",
                error=e.to_info(),
            )

        try:
            return await agent.run(goal, ctx)
        except KairosError as e:
            # Handled failure → result, not exception
            return AgentResult(
                pid=ctx.pid,
                agent=manifest.name,
                status=AgentResultStatus.FAILED,
                summary=f"{manifest.name} failed: {e.message}",
                error=e.to_info(),
            )
        # asyncio.CancelledError and real bugs propagate on purpose — kernel handles kill/retry

    async def restore(self, manifest: AgentManifest, goal: str, ctx: Any, state: dict[str, Any]) -> AgentResult:
        """Resume from a checkpoint's agent_state. Re-runs if the agent doesn't implement restore."""
        try:
            agent = self._load(manifest)
        except KairosError as e:
            return AgentResult(
                pid=ctx.pid,
                agent=manifest.name,
                status=AgentResultStatus.FAILED,
                summary=f"{manifest.name} could not be loaded for restore: {e.message}",
                error=e.to_info(),
            )

        agent.restore(state)
        try:
            return await agent.run(goal, ctx)
        except KairosError as e:
            return AgentResult(
                pid=ctx.pid,
                agent=manifest.name,
                status=AgentResultStatus.FAILED,
                summary=f"{manifest.name} failed on restore: {e.message}",
                error=e.to_info(),
            )
