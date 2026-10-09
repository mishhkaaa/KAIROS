"""Agent registry — loads and validates AgentManifest YAML files.

Owner: P3 — Agents & Models
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import AgentManifest

log = logging.getLogger("kairos.agents.registry")


def _terms(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2]


class ManifestRegistry:
    """Discovers, parses and validates agent manifests from a directory of YAML files.

    Structure expected: <manifests_dir>/<name>.yaml, each a valid AgentManifest.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._by_name: dict[str, AgentManifest] = {}
        self._load()

    def _load(self) -> None:
        self._by_name.clear()
        if not self._directory.exists():
            log.warning("manifests_dir does not exist: %s", self._directory)
            return
        for p in sorted(self._directory.glob("*.yaml")):
            try:
                raw = yaml.safe_load(p.read_text(encoding="utf-8"))
                manifest = AgentManifest.model_validate(raw)
                self._by_name[manifest.name] = manifest
                log.debug("loaded manifest: %s from %s", manifest.name, p)
            except Exception as e:
                log.error("failed to load manifest %s: %s", p, e)

    async def list(self) -> list[AgentManifest]:
        return list(self._by_name.values())

    async def get(self, name: str) -> AgentManifest:
        if name not in self._by_name:
            raise KairosError("AGENT_NOT_FOUND", f"No agent manifest found for '{name}'")
        return self._by_name[name]

    async def match(self, goal: str, limit: int = 3) -> list[AgentManifest]:
        """Return the best candidate agents for a goal, scored by keyword overlap with handles + description."""
        g = set(_terms(goal))
        scored = [
            (len(g & set(_terms(" ".join(m.handles) + " " + m.description))), m)
            for m in self._by_name.values()
        ]
        return [m for s, m in sorted(scored, key=lambda x: -x[0]) if s > 0][:limit]

    def reload(self) -> None:
        """Reload all manifests from disk (useful for hot-reload)."""
        self._load()


# Alias: the contract tests use AgentRegistry, so ManifestRegistry IS the AgentRegistry
AgentRegistry = ManifestRegistry
