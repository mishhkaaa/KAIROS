"""Settings + the service bundle passed to every package factory.

FACTORY CONTRACT — each package exposes `<package>/factory.py` with functions of the form

    def build_<thing>(settings: Settings, services: ServiceBundle) -> <Interface>

They may read already-built services from `services` (build order is fixed in kairosd/wiring.py):

    event_bus, artifacts            (P1)
    models                          (P3)  needs: event_bus
    firewall                        (P2)  needs: models
    converters                      (P4)  list[SourceConverter]
    knowledge, memory               (P2)  needs: models, firewall, converters, event_bus
    sandbox                         (P1)  needs: event_bus
    browser                         (P4)  BrowserDriver
    tools                           (P1)  needs: sandbox, browser, artifacts, event_bus
    agent_registry, agent_runtime   (P3)
    probe                           (P4)  ResourceProbe
    policy, audit, kernel           (P1)  needs: everything

Switching a component between its fake and real implementation is a config change
(KAIROS_<COMPONENT>=fake|real), never a code change.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .interfaces import (
        AgentRegistry,
        AgentRuntime,
        ArtifactStore,
        AuditLog,
        BrowserDriver,
        ContextFirewall,
        EventBus,
        KnowledgeService,
        MemoryService,
        ModelRouter,
        PermissionsProvider,
        PolicyEngine,
        ResourceProbe,
        SandboxManager,
        SourceConverter,
        ToolExecutor,
    )

Mode = Literal["fake", "real"]
COMPONENTS = ["events", "artifacts", "models", "firewall", "converters", "knowledge", "memory", "sandbox", "browser", "tools",
              "agents", "probe", "policy", "audit"]
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseModel):
    """Read from environment (see .env.example). Keep this the ONLY config object."""

    env: str = "dev"
    data_dir: Path = REPO_ROOT / ".data"                     # /sovereign-data on the appliance
    okf_dir: Path = REPO_ROOT / "shared" / "fixtures" / "okf"  # P2 switches to data/okf
    policies_dir: Path = REPO_ROOT / "policies"
    manifests_dir: Path = REPO_ROOT / "agents" / "manifests"
    database_url: str = "postgresql+psycopg://kairos:kairos@localhost:5432/kairos"
    redis_url: str = "redis://127.0.0.1:6379/0"     # not localhost: on Windows it resolves to ::1 first and times out
    ollama_url: str = "http://localhost:11434"
    jira_url: str = "http://localhost:8090"          # mock-jira (P1)
    default_chat_model: str = "qwen2.5:7b-instruct"
    default_embed_model: str = "nomic-embed-text"
    models_config: Path = Field(
        REPO_ROOT / "models" / "models.yaml",
        description="P3: model routing file; e.g. models/models.7b-only.yaml keeps one chat model resident on an 8 GB GPU",
    )
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8080
    knowledge_watch: bool = Field(
        False, description="P2: watch okf_dir and publish knowledge.changed for manual edits (500 ms debounce)"
    )
    firewall_llm: bool = Field(
        False,
        description="P2: also ask the local LLM classifier about unverified/untrusted hits the regex didn't flag; "
        "its catches carry the extra flag instruction_like_llm",
    )
    auth: str = Field("dev", description="P1: dev (X-Kairos-User headers, sign in by email) | google (Google ID token -> session)")
    google_client_id: str | None = Field(None, description="P1: OAuth web client id for Google sign-in (public, not a secret)")
    vault_key: str | None = Field(None, description="P1: 32-byte key (base64) encrypting connector tokens at rest; unset = dev vault")
    session_hours: int = Field(12, description="P1: how long a sign-in lasts")
    demo_data_url: str = Field(
        "postgresql+psycopg://kairos:kairos@localhost:5432/kairos_demo_data",
        description="P1: the demo company's operational database behind the db tool (db.query read-only, db.write "
        "with approval); scripts/seed_demo_data.py creates and fills it (0.12.0)",
    )
    modes: dict[str, Mode] = Field(default_factory=lambda: {c: "fake" for c in COMPONENTS})

    @classmethod
    def from_env(cls, dotenv: Path | None = REPO_ROOT / ".env") -> Settings:
        """Environment wins over .env. Relative paths are resolved against the repo root."""
        if dotenv is not None and dotenv.exists():
            for line in dotenv.read_text(encoding="utf-8").splitlines():
                line = line.split(" #", 1)[0].strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
        kw: dict = {}
        for name, finfo in cls.model_fields.items():
            if name == "modes":
                continue
            val = os.getenv(f"KAIROS_{name.upper()}")
            if val is not None:
                kw[name] = (REPO_ROOT / val).resolve() if finfo.annotation is Path and not Path(val).is_absolute() else val
        s = cls(**kw)
        default = os.getenv("KAIROS_DEFAULT_MODE")
        for c in COMPONENTS:
            mode = os.getenv(f"KAIROS_MODE_{c.upper()}", default)
            if mode in ("fake", "real"):
                s.modes[c] = mode  # type: ignore[assignment]
        return s


@dataclass
class ServiceBundle:
    settings: Settings
    event_bus: EventBus | None = None
    artifacts: ArtifactStore | None = None
    models: ModelRouter | None = None
    knowledge: KnowledgeService | None = None
    firewall: ContextFirewall | None = None
    memory: MemoryService | None = None
    converters: list[SourceConverter] | None = None
    sandbox: SandboxManager | None = None
    browser: BrowserDriver | None = None
    tools: ToolExecutor | None = None
    agent_registry: AgentRegistry | None = None
    agent_runtime: AgentRuntime | None = None
    probe: ResourceProbe | None = None
    policy: PolicyEngine | None = None
    audit: AuditLog | None = None
    permissions: PermissionsProvider | None = None  # 0.11.0: None means the kernel's built-in role stub
    modes: dict[str, str] = field(default_factory=dict)

    def require(self, name: str):
        svc = getattr(self, name)
        if svc is None:
            raise RuntimeError(f"Service {name!r} not built yet — check build order in kairosd/wiring.py")
        return svc
