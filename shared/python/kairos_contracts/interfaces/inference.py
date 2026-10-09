"""Interfaces PROVIDED BY P3 (Agents & Models) — model side.

Consumers: kernel AgentContext.llm (P1), knowledge embeddings (P2), UI model list (P2 via gateway).
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from ..schema import (
    EmbedRequest,
    EmbedResponse,
    ModelInfo,
    ModelRequest,
    ModelResponse,
    RoutingDecision,
    StreamChunk,
)


@runtime_checkable
class ModelProvider(Protocol):
    """One backend: Ollama, llama.cpp server, vLLM, or an approved remote API."""

    name: str

    async def generate(self, request: ModelRequest, model: str) -> ModelResponse: ...
    def stream(self, request: ModelRequest, model: str) -> AsyncIterator[StreamChunk]: ...
    async def embed(self, request: EmbedRequest, model: str) -> EmbedResponse: ...
    async def list_models(self) -> list[ModelInfo]: ...
    async def health(self) -> bool: ...


@runtime_checkable
class ModelRouter(Protocol):
    """Policy-driven model selection (blueprint §45). This is what everyone else calls.

    Hard rule: request.privacy == restricted  =>  a local model or KairosError("MODEL_UNAVAILABLE").
    """

    async def route(self, request: ModelRequest) -> RoutingDecision: ...
    async def generate(self, request: ModelRequest) -> ModelResponse: ...
    def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]: ...
    async def embed(self, request: EmbedRequest) -> EmbedResponse:
        """Always the SAME embedding model for a given deployment (index compatibility). See embedding_dim()."""

    async def embedding_dim(self) -> int: ...
    async def list_models(self) -> list[ModelInfo]: ...
