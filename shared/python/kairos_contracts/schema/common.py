"""Primitive types shared by every KAIROS component.

Everything that crosses a module boundary is built from these. If you need a new
primitive, add it here (and bump CONTRACT_VERSION) rather than redefining it locally.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    """new_id("T") -> "T-3f9a1c02be". Prefixes are listed in shared/README.md."""
    return f"{prefix}-{uuid4().hex[:10]}"


class Contract(BaseModel):
    """Base class for every payload that crosses a module boundary.

    extra="forbid" makes schema drift fail loudly in tests instead of silently on demo day.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --------------------------------------------------------------------------- identifiers

TaskId = Annotated[str, StringConstraints(pattern=r"^T-[A-Za-z0-9]+$")]
Pid = Annotated[int, Field(ge=1)]
ArtifactRef = Annotated[str, StringConstraints(pattern=r"^artifact://[^/]+/.+$")]
"""artifact://<task_id>/<name>  e.g. artifact://T-1842/evidence.json"""

KnowledgePath = Annotated[str, StringConstraints(pattern=r"^/org(/[A-Za-z0-9._\-]+)*/?$")]
"""Knowledge-filesystem path, e.g. /org/projects/apollo  (maps to okf/projects/apollo.md)."""

PathGlob = Annotated[str, StringConstraints(pattern=r"^/(org|workspace)(/.*)?$")]
"""Glob over knowledge or workspace paths, e.g. /org/finance/**  — see util.path_matches."""

Capability = Annotated[
    str, StringConstraints(pattern=r"^(\*|[a-z][a-z0-9_]*(\.([a-z][a-z0-9_]*|\*))+)$")
]
"""<namespace>.<verb>[.<sub>], wildcards allowed: jira.write, knowledge.*, browser.open; "*" = system only.
Full list: shared/catalogs/capabilities.yaml — see util.capability_matches."""


# --------------------------------------------------------------------------- enums

class Priority(StrEnum):
    HIGH = "high"
    NORMAL = "normal"
    BACKGROUND = "background"


class PrivacyLevel(StrEnum):
    """Ordered from least to most sensitive. `restricted` must never leave the box."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


PRIVACY_ORDER = [PrivacyLevel.PUBLIC, PrivacyLevel.INTERNAL, PrivacyLevel.CONFIDENTIAL, PrivacyLevel.RESTRICTED]


class TrustLevel(StrEnum):
    VERIFIED = "verified"
    TRUSTED = "trusted"
    UNVERIFIED = "unverified"
    UNTRUSTED = "untrusted"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    STALE = "stale"


class Risk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PrincipalKind(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


# --------------------------------------------------------------------------- composite primitives

class Principal(Contract):
    """Who is asking. Agents act on behalf of a user and inherit (a subset of) their scope."""

    kind: PrincipalKind
    org_id: str
    user_id: str
    pid: Pid | None = None
    agent: str | None = None
    roles: list[str] = Field(default_factory=list)
    capabilities: list[Capability] = Field(default_factory=list)
    data_scopes: list[PathGlob] = Field(default_factory=lambda: ["/org/**"])
    max_privacy: PrivacyLevel = PrivacyLevel.INTERNAL


class UserPermissions(Contract):
    """What a user may do (0.11.0), resolved from {user, org, roles} by a PermissionsProvider. `permissions` are app
    permissions (task.create, approval.resolve, ...); `capabilities` and `data_scopes` bound every agent a task started by
    this user creates: an agent never gets a capability or an /org scope its user lacks."""

    user_id: str
    org_id: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    capabilities: list[Capability] = Field(default_factory=list)
    data_scopes: list[PathGlob] = Field(default_factory=list)


class ResourceQuota(Contract):
    max_tokens: int = 20_000
    max_tool_calls: int = 20
    max_wall_seconds: int = 600
    max_children: int = 8
    cpu: float = 1.0
    memory_mb: int = 1024
    gpu: float = Field(0.0, ge=0.0, le=1.0, description="Fraction of the shared GPU")


class ResourceUsage(Contract):
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tool_calls: int = 0
    children_spawned: int = 0
    wall_seconds: float = 0.0
    gpu_seconds: float = 0.0

    @property
    def tokens_total(self) -> int:
        return self.tokens_prompt + self.tokens_completion


class Provenance(Contract):
    """Answers: where did this come from, when was it verified, who/what produced it."""

    source: str = Field(description='"okf", "jira", "agent:finance", "tool:browser", ...')
    source_ref: str | None = Field(None, description="External id, URL or /org path")
    source_version: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    author: str | None = None
    generator: str | None = Field(None, description="Agent/pipeline that produced this")
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    trust: TrustLevel = TrustLevel.UNVERIFIED
    related_sources: list[str] = Field(default_factory=list)


class ErrorInfo(Contract):
    code: str = Field(description="One of shared/catalogs/errors.yaml")
    message: str
    retriable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
