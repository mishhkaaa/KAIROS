"""Policy-driven model router (blueprint §45).

Owner: P3 — Agents & Models

Routing rules (in priority order):
1. privacy == restricted  =>  local providers only; raise MODEL_UNAVAILABLE if none.
2. model = model_hint if available and pulled.
3. If latency == critical  =>  config['latency_critical'] model.
4. by_task_class[task_class] if available and pulled.
5. config['default'].
6. Any local chat model that is pulled.
7. Raise MODEL_UNAVAILABLE.

At run time, a model that errors or times out is retried on config['fallback'] in order (Gemma 4 first, then Qwen 2.5).

JSON repair rule (rule 4 in the spec):
If json_schema was set and parsed is None or fails validation, retry once with a repair message.

Embedding always uses config['embedding'] model. embedding_dim is cached after the first call.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import jsonschema
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    EmbedRequest,
    EmbedResponse,
    Latency,
    ModelInfo,
    ModelRequest,
    ModelResponse,
    PrivacyLevel,
    RoutingDecision,
    StreamChunk,
)

log = logging.getLogger("kairos.models.router")

_MODEL_LIST_TTL = 60.0  # seconds


def _valid(data: Any, schema: dict[str, Any]) -> bool:
    try:
        jsonschema.validate(data, schema)
        return True
    except jsonschema.ValidationError:
        return False
    except jsonschema.SchemaError:
        return True  # not the model's fault; let the caller validate


class PolicyRouter:
    """Policy-driven router over a list of ModelProviders."""

    def __init__(self, providers: list, config: dict[str, Any]) -> None:
        self._providers = {p.name: p for p in providers}
        self._config = config
        self._cached_models: list[ModelInfo] = []
        self._cache_ts: float = 0.0
        self._dim: int | None = None
        self._dim_lock = asyncio.Lock()

    # ------------------------------------------------------------------ internal helpers

    @property
    def _local_providers(self) -> list:
        return [p for p in self._providers.values()]  # all our providers are local for now

    async def _get_models(self) -> list[ModelInfo]:
        now = time.monotonic()
        if now - self._cache_ts > _MODEL_LIST_TTL:
            models: list[ModelInfo] = []
            for p in self._providers.values():
                try:
                    models.extend(await p.list_models())
                except Exception as e:
                    log.warning("listing models from %s failed: %s", p.name, e)
            self._cached_models = models
            self._cache_ts = now if models else 0.0  # don't remember an empty list: ask again next time
        return self._cached_models

    def _is_pulled(self, model_name: str, models: list[ModelInfo]) -> bool:
        return any(m.name == model_name or m.name.startswith(model_name + ":") for m in models)

    def _fallbacks(self, failed: str, models: list[ModelInfo]) -> list[str]:
        """config['fallback'], in order: the pulled models to try when `failed` errors or times out."""
        return [m for m in self._config.get("fallback", []) or [] if m != failed and self._is_pulled(m, models)]

    def _best_local_chat(self, models: list[ModelInfo]) -> str | None:
        for m in models:
            if "chat" in m.capabilities and m.local and m.available:
                return m.name
        return None

    def _provider_for(self, model_name: str, models: list[ModelInfo]) -> Any:
        for m in models:
            if m.name == model_name or m.name.startswith(model_name + ":"):
                p = self._providers.get(m.provider)
                if p:
                    return p
        # fall back to first provider
        if self._providers:
            return next(iter(self._providers.values()))
        return None

    async def _resolve_model(self, req: ModelRequest, local_only: bool, models: list[ModelInfo]) -> tuple[str, Any, str]:
        """Return (model_name, provider, reason)."""
        # Rule: privacy restricted => local only (already handled by caller)
        cfg = self._config

        # 1. model_hint
        if req.model_hint and (not local_only or self._is_pulled(req.model_hint, models)):
            p = self._provider_for(req.model_hint, models)
            if p:
                return req.model_hint, p, f"model_hint={req.model_hint}"

        # 2. latency critical
        if req.latency == Latency.CRITICAL:
            lat_model = cfg.get("latency_critical", cfg.get("default", ""))
            if lat_model and self._is_pulled(lat_model, models):
                p = self._provider_for(lat_model, models)
                if p:
                    return lat_model, p, f"latency_critical={lat_model}"

        # 3. by_task_class
        task_model = cfg.get("by_task_class", {}).get(req.task_class.value if hasattr(req.task_class, "value") else str(req.task_class))
        if task_model and self._is_pulled(task_model, models):
            p = self._provider_for(task_model, models)
            if p:
                return task_model, p, f"task_class={req.task_class}"

        # 4. default
        default = cfg.get("default", "")
        if default and self._is_pulled(default, models):
            p = self._provider_for(default, models)
            if p:
                return default, p, "config_default"

        # 5. any local chat model
        best = self._best_local_chat(models)
        if best:
            p = self._provider_for(best, models)
            if p:
                return best, p, "any_local_chat"

        # 6. nothing usable is pulled: say so now, rather than as an HTTP 404 from the provider later
        raise KairosError("MODEL_UNAVAILABLE", "no pulled local chat model; `ollama pull` one from models/models.yaml")

    # ------------------------------------------------------------------ public API

    async def route(self, request: ModelRequest) -> RoutingDecision:
        local_only = request.privacy == PrivacyLevel.RESTRICTED
        models = await self._get_models()
        model_name, provider, reason = await self._resolve_model(request, local_only, models)
        return RoutingDecision(model=model_name, provider=provider.name, local=True, reason=reason)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        local_only = request.privacy == PrivacyLevel.RESTRICTED
        if local_only and not self._local_providers:
            raise KairosError("MODEL_UNAVAILABLE", "privacy=restricted but no local providers configured")

        models = await self._get_models()
        model_name, provider, reason = await self._resolve_model(request, local_only, models)
        log.debug("routing %s to %s/%s (reason: %s)", request.task_class, provider.name, model_name, reason)

        try:
            resp = await provider.generate(request, model_name)
        except KairosError as e:
            if e.code not in ("MODEL_UNAVAILABLE", "TIMEOUT"):
                raise
            resp = None
            for fallback in self._fallbacks(model_name, models):
                log.warning("%s failed (%s); falling back to %s", model_name, e.message[:120], fallback)
                model_name, provider = fallback, self._provider_for(fallback, models)
                try:
                    resp = await provider.generate(request, model_name)
                    break
                except KairosError as again:
                    if again.code not in ("MODEL_UNAVAILABLE", "TIMEOUT"):
                        raise
            if resp is None:
                raise

        # JSON repair: if schema was requested and parsed is None or invalid, retry once
        if request.json_schema and (resp.parsed is None or not _valid(resp.parsed, request.json_schema)):
            try:
                resp = await self._repair_json(request, model_name, provider, resp)
            except Exception as e:
                log.warning("JSON repair failed for %s: %s", model_name, e)

        return resp

    async def _repair_json(self, request: ModelRequest, model: str, provider: Any, first_resp: ModelResponse) -> ModelResponse:
        """Retry once with an explicit JSON repair instruction."""
        from kairos_contracts.schema import ChatMessage, Role
        repair_msg = ChatMessage(
            role=Role.USER,
            content=f"Your previous answer was not valid JSON for the schema. Reply with JSON only matching this schema: {json.dumps(request.json_schema)}",
        )
        repaired_req = request.model_copy(update={"messages": list(request.messages) + [repair_msg]})
        resp = await provider.generate(repaired_req, model)
        if resp.parsed is None and resp.content:
            try:
                resp = resp.model_copy(update={"parsed": json.loads(resp.content)})
            except (json.JSONDecodeError, TypeError):
                pass
        # Validate against schema
        if resp.parsed is not None and request.json_schema:
            try:
                jsonschema.validate(resp.parsed, request.json_schema)
            except jsonschema.ValidationError as e:
                log.warning("JSON validation failed after repair: %s", e.message)
                resp = resp.model_copy(update={"parsed": None})
        return resp

    async def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        local_only = request.privacy == PrivacyLevel.RESTRICTED
        models = await self._get_models()
        model_name, provider, _ = await self._resolve_model(request, local_only, models)
        async for chunk in provider.stream(request, model_name):
            yield chunk

    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        embed_model = self._config.get("embedding", "nomic-embed-text")
        # find a provider that can embed — try all until one succeeds
        reasons: list[str] = []
        for provider in self._providers.values():
            try:
                return await provider.embed(request, embed_model)
            except KairosError as e:
                reasons.append(e.message)
        raise KairosError("MODEL_UNAVAILABLE", f"no provider could embed with {embed_model}: " + "; ".join(reasons or ["none configured"]))

    async def embedding_dim(self) -> int:
        if self._dim is not None:
            return self._dim
        async with self._dim_lock:
            if self._dim is not None:
                return self._dim
            resp = await self.embed(EmbedRequest(texts=["dim probe"]))
            self._dim = resp.dim
            log.info("embedding_dim=%d (model=%s)", self._dim, resp.model)
            return self._dim

    async def list_models(self) -> list[ModelInfo]:
        return await self._get_models()
