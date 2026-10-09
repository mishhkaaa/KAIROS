"""Execution policy documents (policies/*.yaml) — blueprint §46."""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .common import Capability, Contract, PathGlob


class ApprovalMode(StrEnum):
    REQUIRED = "required"
    AUTO = "auto"
    NEVER = "never"  # i.e. always deny


class PolicyAppliesTo(Contract):
    agents: list[str] = Field(default_factory=lambda: ["*"])
    roles: list[str] = Field(default_factory=lambda: ["*"])


class AllowDeny(Contract):
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)


class FilesystemRules(Contract):
    read: list[PathGlob] = Field(default_factory=list)
    write: list[PathGlob] = Field(default_factory=list)


class PolicyDocument(Contract):
    policy: str = Field(description="Unique id, e.g. finance-agent-v1")
    description: str = ""
    priority: int = Field(100, description="Lower number wins when several policies match")
    applies_to: PolicyAppliesTo = Field(default_factory=PolicyAppliesTo)
    knowledge: AllowDeny = Field(default_factory=AllowDeny, description="PathGlobs over /org")
    filesystem: FilesystemRules = Field(default_factory=FilesystemRules)
    network: AllowDeny = Field(default_factory=AllowDeny, description="host:port entries")
    tools: AllowDeny = Field(default_factory=AllowDeny, description="Capability globs")
    approval: dict[Capability, ApprovalMode] = Field(default_factory=dict)
