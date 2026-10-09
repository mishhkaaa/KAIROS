"""Health, resource monitor (ai-top) and system status."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .agents import AgentManifest
from .common import Contract, utcnow
from .inference import ModelInfo
from .tools import ToolSpec


class ComponentHealth(Contract):
    component: str = Field(description="kernel | knowledge | memory | models | agents | tools | sandbox | db | redis | ollama")
    ok: bool
    mode: str = Field("real", description="real | fake — which implementation is wired in")
    detail: str = ""


class GpuStatus(Contract):
    name: str
    utilization: float = Field(ge=0.0, le=1.0)
    memory_used_mb: int
    memory_total_mb: int


class ResourceSnapshot(Contract):
    ts: datetime = Field(default_factory=utcnow)
    cpu_percent: float
    ram_used_mb: int
    ram_total_mb: int
    gpu: GpuStatus | None = None
    running_processes: int = 0
    queued_tasks: int = 0
    active_sandboxes: int = 0
    tokens_last_minute: int = 0


class SystemStatus(Contract):
    ready: bool
    version: str
    contract_version: str
    uptime_s: float
    components: list[ComponentHealth]


# ---------------------------------------------------------------- GET /system/config (read-only; secrets redacted)
class StackComponent(Contract):
    component: str = Field(description="ServiceBundle attribute, e.g. knowledge, models, sandbox")
    mode: str = Field(description="real | fake | fake(fallback)")
    implementation: str = Field(description="Implementing class, e.g. kairos_knowledge.kfs.KnowledgeFS")
    ok: bool
    detail: str = ""


class RuntimeVersions(Contract):
    kairos: str
    contract: str
    python: str
    node: str | None = Field(None, description="Node.js on the server, if installed (the console build)")


class ModelRoute(Contract):
    task_class: str = Field(description="planning | reasoning | ... | default | latency_critical | embedding")
    model: str
    local: bool = True
    available: bool = Field(description="The model is present in the runtime (ollama list)")
    context_window: int | None = None


class ModelsConfig(Contract):
    config_file: str = Field(description="Routing file in use, relative to the repo, e.g. models/models.7b-only.yaml")
    default: str
    embedding: str
    remote_enabled: bool = False
    routes: list[ModelRoute] = Field(default_factory=list)
    models: list[ModelInfo] = Field(default_factory=list)


class PolicySummary(Contract):
    policy: str
    priority: int
    agents: list[str] = Field(default_factory=list, description="applies_to.agents")
    roles: list[str] = Field(default_factory=list, description="applies_to.roles")
    requires_approval: list[str] = Field(default_factory=list, description="Capabilities that need a human")
    auto_approved: list[str] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list, description="approval: never, plus tools.deny")


class FirewallConfig(Contract):
    regex: bool = Field(True, description="Pattern screening; always on")
    llm_classifier: bool = Field(False, description="KAIROS_FIREWALL_LLM")


class EndpointInfo(Contract):
    name: str = Field(description="gateway | database | redis | ollama | jira | ...")
    url: str = Field(description="Credentials are always redacted (user:***@host)")


class SystemConfig(Contract):
    """GET /system/config: one read-only document describing the running system. Never contains secrets."""

    versions: RuntimeVersions
    env: str = "dev"
    stack: list[StackComponent] = Field(default_factory=list)
    models: ModelsConfig
    agents: list[AgentManifest] = Field(default_factory=list)
    tools: list[ToolSpec] = Field(default_factory=list)
    policies: list[PolicySummary] = Field(default_factory=list)
    firewall: FirewallConfig = Field(default_factory=FirewallConfig)
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    endpoints: list[EndpointInfo] = Field(default_factory=list)
    paths: dict[str, str] = Field(default_factory=dict, description="okf_dir, policies_dir, manifests_dir, data_dir, models_config")
