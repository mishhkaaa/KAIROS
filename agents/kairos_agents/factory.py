"""Factory contract for P3 — agents (see kairos_contracts.wiring).

Owner: P3 — Agents & Models
"""
from __future__ import annotations

import logging

from kairos_contracts.interfaces import AgentRegistry, AgentRuntime
from kairos_contracts.wiring import ServiceBundle, Settings

log = logging.getLogger("kairos.agents.factory")


def build_agent_registry(settings: Settings, services: ServiceBundle) -> AgentRegistry:
    """Build the real ManifestRegistry from settings.manifests_dir."""
    from kairos_agents.registry import ManifestRegistry

    manifests_dir = settings.manifests_dir
    log.info("building agent registry: manifests_dir=%s", manifests_dir)
    return ManifestRegistry(manifests_dir)


def build_agent_runtime(settings: Settings, services: ServiceBundle) -> AgentRuntime:
    """Build the real Runtime."""
    from kairos_agents.runtime import Runtime

    log.info("building agent runtime")
    return Runtime()
