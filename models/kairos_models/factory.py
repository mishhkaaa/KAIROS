"""Model router factory for P3.

Owner: P3 — Agents & Models

Builds a PolicyRouter over OllamaProvider using settings from:
  - settings.ollama_url  (KAIROS_OLLAMA_URL env var, default http://localhost:11434)
  - settings.models_config (KAIROS_MODELS_CONFIG, default models/models.yaml: routing config)
"""
from __future__ import annotations

import logging

import yaml
from kairos_contracts.interfaces import ModelRouter
from kairos_contracts.wiring import ServiceBundle, Settings

log = logging.getLogger("kairos.models.factory")


def build_model_router(settings: Settings, services: ServiceBundle) -> ModelRouter:
    """Build and return the real PolicyRouter backed by OllamaProvider."""
    from kairos_models.providers.ollama import OllamaProvider
    from kairos_models.router.router import PolicyRouter

    config_path = settings.models_config
    if not config_path.exists():
        log.warning("models config not found at %s, using empty config", config_path)
        config: dict = {}
    else:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    ollama_url = settings.ollama_url
    log.info("building model router: ollama_url=%s, config=%s", ollama_url, config_path)

    providers = [OllamaProvider(ollama_url)]
    return PolicyRouter(providers, config)
