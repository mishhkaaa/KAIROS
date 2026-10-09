"""Ollama HTTP provider for the KAIROS model layer.

Owner: P3 — Agents & Models
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import EmbedRequest, EmbedResponse, ModelInfo, ModelRequest, ModelResponse, StreamChunk, TokenUsage

log = logging.getLogger("kairos.models.providers.ollama")


# nomic-embed-text is trained with task prefixes; without them queries and documents land in one undifferentiated space.
_NOMIC_PREFIX = {"query": "search_query: ", "document": "search_document: "}


def task_prefixed(model: str, req: EmbedRequest) -> list[str]:
    """The texts as the model expects them: nomic models get their task prefix when the request says what they are."""
    prefix = _NOMIC_PREFIX.get(req.input_type or "") if model.split(":")[0].endswith("nomic-embed-text") else None
    return [f"{prefix}{t}" for t in req.texts] if prefix else list(req.texts)


# Model families with a thinking mode; other models are never sent `think` (Ollama refuses it for them).
THINKING_FAMILIES = ("gemma4", "qwen3", "deepseek-r1", "gpt-oss")
THINK_BUDGET = 1024


def thinks(model: str) -> bool:
    return model.split("/")[-1].startswith(THINKING_FAMILIES)


class OllamaProvider:
    """One backend: Ollama HTTP API (POST /api/chat, POST /api/embed, GET /api/tags)."""

    name = "ollama"

    def __init__(self, base_url: str, timeout: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    def _transport_error(self, what: str, e: httpx.HTTPError) -> KairosError:
        """httpx's timeout and connection errors usually stringify to "", which left task failures with no reason."""
        kind = type(e).__name__
        if isinstance(e, httpx.TimeoutException) and not isinstance(e, httpx.ConnectTimeout):
            return KairosError("TIMEOUT", f"{what}: no answer within {self.timeout:g}s ({kind})")
        if isinstance(e, httpx.TransportError):
            return KairosError("MODEL_UNAVAILABLE", f"{what}: cannot reach Ollama at {self.base_url} ({kind})")
        return KairosError("MODEL_UNAVAILABLE", f"{what}: {kind}: {e}")

    def _body(self, req: ModelRequest, model: str, stream: bool, think: bool = True) -> dict:
        def message(m: Any) -> dict:
            out = {"role": m.role.value, "content": m.content}
            if m.images:
                out["images"] = m.images  # base64, for vision models (Gemma 4)
            return out

        body: dict = {
            "model": model,
            "stream": stream,
            "messages": [message(m) for m in req.messages],
            "options": {
                "temperature": req.temperature,
                "num_predict": req.max_tokens,
                "stop": req.stop or None,
            },
        }
        if req.json_schema:
            body["format"] = req.json_schema  # Ollama structured outputs
        if req.think and think and thinks(model):
            body["think"] = True
            body["options"]["num_predict"] = req.max_tokens + THINK_BUDGET  # the thinking comes out of the same budget
        return body

    async def generate(self, req: ModelRequest, model: str) -> ModelResponse:
        t0 = time.perf_counter()
        try:
            r = await self.client.post("/api/chat", json=self._body(req, model, stream=False))
            if r.status_code == 400 and req.think and "think" in r.text.lower():
                # This build of the model has no thinking mode: answer without it
                r = await self.client.post("/api/chat", json=self._body(req, model, stream=False, think=False))
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise KairosError("MODEL_UNAVAILABLE", f"ollama {model}: HTTP {e.response.status_code} — {e.response.text[:200]}") from e
        except httpx.HTTPError as e:
            raise self._transport_error(f"ollama {model}", e) from e

        data = r.json()
        if "error" in data:
            raise KairosError("MODEL_UNAVAILABLE", f"ollama {model}: {data['error']}")

        content = data.get("message", {}).get("content", "")
        parsed = None
        if req.json_schema:
            try:
                parsed = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                parsed = None  # the router repairs/retries

        return ModelResponse(
            model=model,
            provider=self.name,
            content=content,
            parsed=parsed,
            local=True,
            usage=TokenUsage(
                prompt=data.get("prompt_eval_count", 0),
                completion=data.get("eval_count", 0),
            ),
            latency_ms=(time.perf_counter() - t0) * 1000,
            finish_reason=data.get("done_reason", "stop"),
        )

    async def stream(self, req: ModelRequest, model: str):
        """Async generator of StreamChunks."""
        try:
            async with self.client.stream("POST", "/api/chat", json=self._body(req, model, stream=True)) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("done"):
                        yield StreamChunk(
                            delta="",
                            done=True,
                            usage=TokenUsage(
                                prompt=d.get("prompt_eval_count", 0),
                                completion=d.get("eval_count", 0),
                            ),
                        )
                    else:
                        yield StreamChunk(delta=d.get("message", {}).get("content", ""))
        except httpx.HTTPError as e:
            raise self._transport_error(f"ollama stream {model}", e) from e

    async def embed(self, req: EmbedRequest, model: str) -> EmbedResponse:
        """One POST /api/embed for the whole batch (the old /api/embeddings took one prompt per request)."""
        if not req.texts:
            return EmbedResponse(model=model, dim=0, vectors=[])
        try:
            r = await self.client.post("/api/embed", json={"model": model, "input": task_prefixed(model, req)})
        except httpx.HTTPError as e:
            raise self._transport_error(f"ollama embed {model}", e) from e
        if r.status_code >= 400:
            raise KairosError("MODEL_UNAVAILABLE", f"embed {model}: {r.text[:200]}")
        vecs = r.json().get("embeddings") or []
        if len(vecs) != len(req.texts) or not all(vecs):
            raise KairosError("MODEL_UNAVAILABLE", f"ollama embed returned {len(vecs)} vectors for {len(req.texts)} texts ({model})")
        return EmbedResponse(model=model, dim=len(vecs[0]), vectors=vecs)

    async def list_models(self) -> list[ModelInfo]:
        try:
            r = await self.client.get("/api/tags", timeout=5.0)
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
            return [
                ModelInfo(
                    name=n,
                    provider=self.name,
                    local=True,
                    capabilities=["embed"] if "embed" in n else ["chat", "json"],
                )
                for n in names
            ]
        except httpx.HTTPError as e:
            log.warning("ollama list_models failed: %s", e)
            return []

    async def health(self) -> bool:
        try:
            r = await self.client.get("/api/tags", timeout=2.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        await self.client.aclose()
