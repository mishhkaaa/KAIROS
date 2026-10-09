"""Dynamic agents (contract 0.11.0): an ephemeral manifest and policy generated per agent a task creates.

Owner: P1 — Kernel & Execution

A registry manifest is a role template. When an agent spawns a child, the kernel generates the child's manifest from the
template, bounded four ways:

    capabilities = template ∩ requested (SpawnRequest.capabilities) ∩ the user's permissions ∩ org policy
                   [∩ the parent's capabilities when the parent is itself generated: sub-agents never get wider]
    scope        = template mounts ∩ requested scope ∩ the user's data scopes [∩ the parent's scopes, same rule]

Whatever is dropped is recorded with a reason (the kernel journals it as a `policy` audit entry). The generated policy
is an overlay that can only narrow: its tools are the granted capabilities, and every capability whose catalog default
is approval-required stays required (writes always need a person). Both live in memory and are mirrored to
<data_dir>/ephemeral/<task_id>/ for inspection; they are removed when the task ends and swept at boot (only a task's
root survives a restart, and it regenerates its children).
"""
from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from kairos_contracts.schema import (
    AgentManifest,
    ApprovalMode,
    ManifestCapabilities,
    PolicyDocument,
    Principal,
    PrincipalKind,
    SpawnRequest,
    UserPermissions,
)
from kairos_contracts.util import APPROVAL_REQUIRED, capability_matches, has_capability, path_matches

log = logging.getLogger("kairos.kernel.dynamic")

# Capabilities the kernel's context checks itself (not syscalls): org policy bounds these through knowledge scopes, and
# no policy document lists them, so they are not run through PolicyEngine.permits.
CONTEXT_NAMESPACES = ("knowledge.", "agent.", "memory.")


def mounts_as_globs(mounts: list[str]) -> list[str]:
    return [m.rstrip("/") + "/**" for m in mounts]


def globs_as_mounts(globs: list[str]) -> list[str]:
    return [re.sub(r"/?\*+$", "", g.rstrip("/")) or "/org" for g in globs]


def _covers(outer: str, inner: str) -> bool:
    """Same rule as the lifecycle's scope helpers: outer covers inner's base path."""
    return path_matches(re.sub(r"/?\*+$", "", inner.rstrip("/")) or "/org", outer)


def narrow_scopes(scopes: list[str], bound: list[str]) -> tuple[list[str], list[str]]:
    """(kept, dropped): each scope narrowed to what `bound` allows (the narrower of each overlapping pair)."""
    kept: list[str] = []
    for s in scopes:
        for b in bound:
            if _covers(b, s):
                kept.append(s)
            elif _covers(s, b):
                kept.append(b)
    kept = list(dict.fromkeys(kept))
    return kept, [s for s in scopes if s not in kept]  # dropped, or narrowed to a sub-scope


@dataclass
class Generated:
    manifest: AgentManifest
    policy: PolicyDocument
    dropped: dict[str, str] = field(default_factory=dict)  # capability or scope -> why it was dropped
    requested: list[str] = field(default_factory=list)


def generate(template: AgentManifest, req: SpawnRequest, *, name: str, task_id: str, user: UserPermissions,
             org_refuses, parent: AgentManifest | None = None, parent_caps: list[str] | None = None,
             parent_scopes: list[str] | None = None) -> Generated:
    """The ephemeral manifest and policy for one agent. `org_refuses(capability) -> reason | None` asks org policy."""
    dropped: dict[str, str] = {}
    caps = template.all_capabilities()
    requested = list(req.capabilities) if req.capabilities is not None else list(caps)
    for c in requested:  # a request for something the template lacks is narrowed, and says so
        if not any(capability_matches(c, t) or capability_matches(t, c) for t in caps):
            dropped[c] = f"not in the {template.name} template"
    if req.capabilities is not None:
        caps = [c for c in caps if has_capability(c, req.capabilities)]
    kept: list[str] = []
    for c in caps:
        if not has_capability(c, user.capabilities):
            dropped[c] = f"not granted to {user.user_id} (roles: {', '.join(user.roles) or 'none'})"
        elif parent_caps is not None and not has_capability(c, parent_caps):
            dropped[c] = f"wider than the parent {parent.name if parent else 'agent'}"
        elif not c.startswith(CONTEXT_NAMESPACES) and (why := org_refuses(c)):
            dropped[c] = f"org policy: {why}"
        else:
            kept.append(c)

    scopes = mounts_as_globs(template.memory.mounts) or ["/org/**"]
    for bound, reason in ((req.scope, "outside the requested scope"),
                          (user.data_scopes, f"outside {user.user_id}'s data scopes"),
                          (parent_scopes, "wider than the parent's scope")):
        if bound is None:
            continue
        scopes, lost = narrow_scopes(scopes, list(bound))
        for s in lost:
            inside = [k for k in scopes if _covers(s, k)]
            dropped.setdefault(s, f"{reason} (narrowed to {', '.join(inside)})" if inside else reason)

    tools = [c for c in kept if not c.startswith(("knowledge.", "agent."))]
    knowledge = [c.split(".", 1)[1] for c in kept if c.startswith("knowledge.")]
    agents = list(template.capabilities.agents) if "agent.spawn" in kept else []
    manifest = template.model_copy(deep=True, update={
        "name": name, "template": template.name, "generated": True, "task_id": task_id,
        "description": f"{template.description} (generated for {task_id})",
        "capabilities": ManifestCapabilities(knowledge=knowledge, tools=tools, agents=agents),
        "memory": template.memory.model_copy(update={"mounts": globs_as_mounts(scopes)}),
    })
    policy = PolicyDocument.model_validate({
        "policy": f"gen-{name}", "description": f"Generated for {name}: narrows the org policies of {template.name}",
        "priority": 0, "applies_to": {"agents": [name]},
        "knowledge": {"allow": scopes}, "tools": {"allow": kept},
        "approval": {c: ApprovalMode.REQUIRED.value for c in sorted(APPROVAL_REQUIRED) if has_capability(c, kept)},
    })
    return Generated(manifest=manifest, policy=policy, dropped=dropped, requested=requested)


def org_probe(template: AgentManifest, task_org: str, user_id: str, roles: list[str]) -> Principal:
    """The principal org policy is asked about: the template's name, so its org documents apply."""
    return Principal(kind=PrincipalKind.AGENT, org_id=task_org, user_id=user_id, agent=template.name, roles=roles,
                     capabilities=template.all_capabilities())


class EphemeralAgents:
    """The generated manifests and policies of running tasks."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.by_task: dict[str, dict[str, Generated]] = {}

    def name_for(self, template: str, task_id: str) -> str:
        taken = self.by_task.get(task_id, {})
        base = f"{template}@{task_id}"
        n = 1 + sum(1 for g in taken.values() if g.manifest.template == template)
        return base if n == 1 else f"{base}#{n}"

    def add(self, task_id: str, g: Generated) -> None:
        self.by_task.setdefault(task_id, {})[g.manifest.name] = g
        folder = self.root / task_id
        try:
            for sub, name, data in (("manifests", g.manifest.name, g.manifest.model_dump(mode="json", exclude_none=True)),
                                    ("policies", g.policy.policy, g.policy.model_dump(mode="json", exclude_none=True))):
                (folder / sub).mkdir(parents=True, exist_ok=True)
                (folder / sub / f"{_file(name)}.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        except OSError as e:  # the files are for inspection; the kernel works from memory
            log.warning("could not write ephemeral files for %s: %s", g.manifest.name, e)

    def get(self, name: str) -> Generated | None:
        return next((t[name] for t in self.by_task.values() if name in t), None)

    def names(self, task_id: str) -> list[str]:
        return list(self.by_task.get(task_id, {}))

    def remove_task(self, task_id: str) -> list[str]:
        names = list(self.by_task.pop(task_id, {}))
        shutil.rmtree(self.root / task_id, ignore_errors=True)
        return names

    def sweep(self) -> int:
        """At boot: nothing generated survives a restart. Returns how many task folders were removed."""
        self.by_task.clear()
        if not self.root.is_dir():
            return 0
        folders = [p for p in self.root.iterdir() if p.is_dir()]
        for p in folders:
            shutil.rmtree(p, ignore_errors=True)
        return len(folders)


def _file(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)
