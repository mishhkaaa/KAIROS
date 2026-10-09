"""GET /system/config: a read-only description of the running system. Every URL goes through redact_url; no secret
setting (session keys, vault keys, OAuth secrets) is ever read into this document."""
from __future__ import annotations

import asyncio
import logging
import platform
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from kairos_contracts import CONTRACT_VERSION
from kairos_contracts.schema import (
    EndpointInfo,
    FirewallConfig,
    ModelInfo,
    ModelRoute,
    ModelsConfig,
    RuntimeVersions,
    StackComponent,
    SystemConfig,
)
from kairos_contracts.util import policy_summary, redact_url
from kairos_contracts.wiring import REPO_ROOT

from .. import __version__
from ..policy.engine import load_policy_documents

if TYPE_CHECKING:
    from ..kernel import Kernel

log = logging.getLogger("kairos.kernel.gateway.config")

_node_version: str | None | bool = False  # False = not probed yet


async def node_version() -> str | None:
    global _node_version
    if _node_version is False:
        _node_version = None
        node = shutil.which("node")
        if node:
            try:
                proc = await asyncio.create_subprocess_exec(node, "--version", stdout=asyncio.subprocess.PIPE,
                                                            stderr=asyncio.subprocess.DEVNULL)
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
                _node_version = out.decode().strip().lstrip("v") or None
            except (OSError, TimeoutError):
                log.debug("node --version failed")
    return _node_version or None


def _rel(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _impl(svc: Any) -> str:
    if isinstance(svc, list):
        return ", ".join(sorted({f"{type(s).__module__}.{type(s).__qualname__}" for s in svc})) or "-"
    return f"{type(svc).__module__}.{type(svc).__qualname__}"


def models_config(path: Path, available: list[ModelInfo]) -> ModelsConfig:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        log.warning("cannot read models config %s: %s", path, e)
        raw = {}
    by_name = {m.name: m for m in available}
    default = raw.get("default", "")
    embedding = raw.get("embedding", "")
    pairs = [*(raw.get("by_task_class") or {}).items(), ("default", default),
             ("latency_critical", raw.get("latency_critical") or default), ("embedding", embedding)]

    def route(task_class: str, model: str) -> ModelRoute:
        info = by_name.get(model) or by_name.get(f"{model}:latest")
        return ModelRoute(task_class=task_class, model=model, local=info.local if info else True, available=info is not None,
                          context_window=info.context_window if info and "embed" not in info.capabilities else None)

    return ModelsConfig(config_file=_rel(path), default=default, embedding=embedding,
                        remote_enabled=bool((raw.get("remote") or {}).get("enabled", False)),
                        routes=[route(t, m) for t, m in pairs if m], models=available)


async def build_system_config(k: Kernel) -> SystemConfig:
    svc, s = k.services, k.settings
    health = {c.component: c for c in k.components()}
    stack = [StackComponent(component=name, mode=h.mode, implementation=_impl(getattr(svc, name, None)) if h.ok else "-",
                            ok=h.ok, detail=h.detail)
             for name, h in health.items() if name != "kernel"]
    stack.insert(0, StackComponent(component="kernel", mode="real", implementation=_impl(k), ok=k.ready))

    async def safe(coro: Any, default: Any) -> Any:  # one broken service must not take the whole page down
        try:
            return await coro
        except Exception as e:
            log.warning("system/config: %s", e)
            return default

    models = await safe(svc.models.list_models(), []) if svc.models else []
    agents = await safe(svc.agent_registry.list(), []) if svc.agent_registry else []
    tools = await safe(svc.tools.list_tools(), []) if svc.tools else []
    documents = getattr(k.policy, "documents", None)
    policies = documents() if documents else load_policy_documents(s.policies_dir)

    return SystemConfig(
        versions=RuntimeVersions(kairos=__version__, contract=CONTRACT_VERSION, python=platform.python_version(),
                                 node=await node_version()),
        env=s.env,
        stack=stack,
        models=models_config(s.models_config, models),
        agents=agents,
        tools=tools,
        policies=sorted((policy_summary(d) for d in policies), key=lambda p: (p.priority, p.policy)),
        firewall=FirewallConfig(regex=True, llm_classifier=s.firewall_llm),
        feature_flags={"knowledge_watch": s.knowledge_watch, "firewall_llm": s.firewall_llm},
        endpoints=[EndpointInfo(name="gateway", url=f"http://{s.gateway_host}:{s.gateway_port}"),
                   *(EndpointInfo(name=n, url=redact_url(u)) for n, u in
                     (("database", s.database_url), ("redis", s.redis_url), ("ollama", s.ollama_url), ("jira", s.jira_url)))],
        paths={"okf_dir": _rel(s.okf_dir), "policies_dir": _rel(s.policies_dir), "manifests_dir": _rel(s.manifests_dir),
               "data_dir": _rel(s.data_dir), "models_config": _rel(s.models_config)})
