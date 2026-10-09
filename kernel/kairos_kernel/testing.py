"""Test helpers for kernel tests (and for anyone scripting agents against a real kernel)."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from kairos_contracts.schema import (
    AgentManifest,
    AgentResult,
    AgentResultStatus,
    ManifestCapabilities,
    ManifestResources,
    ManifestRuntime,
    TaskCreate,
)
from kairos_contracts.testing.fakes import FakeAgentRegistry, fake_bundle, user_principal
from kairos_contracts.wiring import Settings

from .config import KernelConfig
from .kernel import Kernel

Script = Callable[[str, Any], Awaitable[AgentResult]]


def manifest(name: str, *, tools: list[str] | None = None, agents: list[str] | None = None, max_tokens: int = 12_000,
             max_tool_calls: int = 10) -> AgentManifest:
    return AgentManifest(name=name, description=f"test {name}", runtime=ManifestRuntime(entrypoint="tests:X"),
                         capabilities=ManifestCapabilities(tools=tools or [], agents=agents or []),
                         resources=ManifestResources(max_tokens_per_task=max_tokens, max_tool_calls=max_tool_calls))


def done(ctx: Any, summary: str = "ok", **output: Any) -> AgentResult:
    return AgentResult(pid=ctx.pid, agent=ctx.manifest.name, status=AgentResultStatus.COMPLETED, summary=summary,
                       output=output)


class ScriptedRuntime:
    """AgentRuntime whose agents are plain async functions keyed by manifest name."""

    def __init__(self, scripts: dict[str, Script]) -> None:
        self.scripts = scripts
        self.calls: dict[str, int] = {}
        self.restored: dict[str, int] = {}

    async def run(self, m: AgentManifest, goal: str, ctx: Any) -> AgentResult:
        name = m.name if m.name in self.scripts else (m.template or m.name)  # generated agents run their template's script
        self.calls[name] = self.calls.get(name, 0) + 1
        return await self.scripts[name](goal, ctx)

    async def restore(self, m: AgentManifest, goal: str, ctx: Any, state: dict) -> AgentResult:
        ctx.inputs["_restored"] = dict(state)  # scripts can tell a resumed run from a fresh one
        self.restored[m.template or m.name] = self.restored.get(m.template or m.name, 0) + 1
        return await self.run(m, goal, ctx)


def kernel_factory(tmp_path, config: KernelConfig | None = None):
    def _make(scripts: dict[str, Script] | None = None, manifests: list[AgentManifest] | None = None,
              config: KernelConfig | None = config, **overrides: Any):
        settings = Settings(data_dir=tmp_path)
        bundle = fake_bundle(settings)
        if manifests is not None:
            bundle.agent_registry = FakeAgentRegistry(manifests=manifests)
        if scripts is not None:
            bundle.agent_runtime = ScriptedRuntime(scripts)
        for name, value in overrides.items():
            setattr(bundle, name, value)
        return Kernel(settings, bundle, config or KernelConfig(policy_watch_interval_s=0))

    return _make


async def start_task(kernel: Kernel, goal: str = "test goal", root: str = "planner-agent") -> str:
    task = await kernel.tasks.create(TaskCreate(goal=goal, metadata={"root_agent": root}), user_principal())
    return task.task_id


def run(coro_fn: Callable[[], Awaitable[Any]], timeout: float = 20) -> Any:
    return asyncio.run(asyncio.wait_for(coro_fn(), timeout))


async def eventually(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), timeout)
