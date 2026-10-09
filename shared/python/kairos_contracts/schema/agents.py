"""Agent manifests (package format), plans, goals and results."""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from .common import ArtifactRef, Capability, Contract, ErrorInfo, KnowledgePath, Pid, ResourceUsage, TaskId
from .syscall import SyscallRequest


class AgentFramework(StrEnum):
    CUSTOM = "custom"
    NOOA = "nooa"


class ModelPolicy(StrEnum):
    LOCAL_ONLY = "local-only"
    LOCAL_PREFERRED = "local-preferred"
    ANY = "any"


class ManifestRuntime(Contract):
    framework: AgentFramework = AgentFramework.CUSTOM
    entrypoint: str = Field(description='"module.path:ClassName"')
    model_policy: ModelPolicy = ModelPolicy.LOCAL_PREFERRED
    model_hint: str | None = None


class ManifestMemory(Contract):
    mounts: list[KnowledgePath] = Field(default_factory=list)


class ManifestCapabilities(Contract):
    knowledge: list[str] = Field(default_factory=lambda: ["read", "search"])
    tools: list[Capability] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list, description="Agents this one may spawn")


class ManifestResources(Contract):
    cpu: float = 1.0
    memory: str = "1Gi"
    gpu: float = 0.0
    max_tokens_per_task: int = 12_000
    max_tool_calls: int = 20


class ManifestNetwork(Contract):
    allow: list[str] = Field(default_factory=list)


class ManifestApproval(Contract):
    required: list[Capability] = Field(default_factory=list)


class AgentManifest(Contract):
    """agents/manifests/<name>.yaml — blueprint §34."""

    name: str
    version: str = "0.1.0"
    description: str
    handles: list[str] = Field(default_factory=list, description="Skills/topics used by the planner to route subtasks")
    runtime: ManifestRuntime
    memory: ManifestMemory = Field(default_factory=ManifestMemory)
    capabilities: ManifestCapabilities = Field(default_factory=ManifestCapabilities)
    resources: ManifestResources = Field(default_factory=ManifestResources)
    network: ManifestNetwork = Field(default_factory=ManifestNetwork)
    approval: ManifestApproval = Field(default_factory=ManifestApproval)
    # Dynamic agents (0.11.0). A registry manifest is a role template; the kernel generates an ephemeral manifest from it
    # for each agent a task creates (name "<template>@<task_id>", narrowed capabilities and mounts).
    system_prompt: str | None = Field(None, description="The role's instructions, for template agents that run it generically")
    template: str | None = Field(None, description="The role template this manifest was generated from (None: a template)")
    generated: bool = Field(False, description="True for an ephemeral manifest the kernel generated for one task")
    task_id: str | None = Field(None, description="The task a generated manifest belongs to; removed when the task ends")

    def all_capabilities(self) -> list[str]:
        """Flattened capability strings the kernel grants at spawn time (before policy narrowing)."""
        caps = [f"knowledge.{v}" for v in self.capabilities.knowledge]
        caps += list(self.capabilities.tools)
        if self.capabilities.agents:
            caps.append("agent.spawn")
        return caps


class PlanStep(Contract):
    step_id: str
    agent: str
    goal: str
    depends_on: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)


class Plan(Contract):
    task_id: TaskId
    rationale: str
    steps: list[PlanStep]


class AgentResultStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentResult(Contract):
    pid: Pid
    agent: str
    status: AgentResultStatus
    summary: str
    output: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    actions: list[SyscallRequest] = Field(default_factory=list, description="Syscalls this agent issued")
    usage: ResourceUsage = Field(default_factory=ResourceUsage)
    error: ErrorInfo | None = None
