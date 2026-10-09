"""The user-permissions stub (contract 0.11.0): {user, org, roles} -> UserPermissions from policies/role-capabilities.yaml.

Owner: P1 — Kernel & Execution. The RBAC module replaces it as ServiceBundle.permissions (same PermissionsProvider
interface); the kernel only falls back to this when no provider is wired.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from kairos_contracts.schema import UserPermissions

log = logging.getLogger("kairos.kernel.permissions")

FILE = "rbac/role-capabilities.yaml"  # a subfolder: the policy engine loads every policies/*.yaml as a PolicyDocument
# No file: behave as before permissions existed (every agent keeps its manifest's capabilities).
_UNBOUNDED = {"capabilities": ["knowledge.*", "memory.*", "agent.*", "jira.*", "fs.*", "browser.*", "db.*", "postgres.*",
                               "database.*", "external.*", "mcp.*", "sandbox.*", "github.*", "calendar.*"],
              "data_scopes": ["/org/**"]}


class RolePermissions:
    def __init__(self, table: dict[str, Any] | None) -> None:
        table = table or {}
        self.roles: dict[str, dict[str, list[str]]] = table.get("roles") or {}
        self.users: dict[str, list[str]] = table.get("users") or {}
        self.default_role: str = table.get("default_role", "member")

    @classmethod
    def from_dir(cls, policies_dir: Path) -> RolePermissions:
        path = Path(policies_dir) / FILE
        if not path.is_file():
            log.warning("%s not found: agents are bounded by their manifests and policies only", path)
            return cls(None)
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")))

    async def resolve(self, user_id: str, org_id: str, roles: list[str] | None = None) -> UserPermissions:
        if not self.roles:
            return UserPermissions(user_id=user_id, org_id=org_id, roles=list(roles or []), **_UNBOUNDED)
        roles = list(roles or self.users.get(user_id) or [self.default_role])
        caps: list[str] = []
        scopes: list[str] = []
        for r in roles:
            grant = self.roles.get(r) or {}
            caps += grant.get("capabilities", [])
            scopes += grant.get("data_scopes", [])
        return UserPermissions(user_id=user_id, org_id=org_id, roles=roles, capabilities=list(dict.fromkeys(caps)),
                               data_scopes=list(dict.fromkeys(scopes)))
