"""Model runtime: chat/generation, streaming, embeddings, routing decisions."""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from .common import Contract, Pid, PrivacyLevel, TaskId


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(Contract):
    role: Role
    content: str
    name: str | None = None


class TaskClass(StrEnum):
    PLANNING = "planning"
    REASONING = "reasoning"
    EXTRACTION = "extraction"
    SUMMARIZATION = "summarization"
    CLASSIFICATION = "classification"
    CODE = "code"
    VISION = "vision"


class Latency(StrEnum):
    CRITICAL = "critical"
    NORMAL = "normal"
    BATCH = "batch"


class ModelRequest(Contract):
    messages: list[ChatMessage]
    task_class: TaskClass = TaskClass.REASONING
    privacy: PrivacyLevel = PrivacyLevel.INTERNAL
    latency: Latency = Latency.NORMAL
    model_hint: str | None = Field(None, description="Preferred model; router may override")
    max_tokens: int = 1024
    temperature: float = 0.2
    json_schema: dict[str, Any] | None = Field(None, description="Request structured JSON output")
    stop: list[str] = Field(default_factory=list)
    # accounting — filled by the kernel's AgentContext, not by agents
    task_id: TaskId | None = None
    pid: Pid | None = None


class TokenUsage(Contract):
    prompt: int = 0
    completion: int = 0


class ModelResponse(Contract):
    model: str
    provider: str
    content: str
    parsed: dict[str, Any] | None = Field(None, description="Set when json_schema was requested")
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    local: bool = True


class StreamChunk(Contract):
    delta: str
    done: bool = False
    usage: TokenUsage | None = None


class EmbedRequest(Contract):
    texts: list[str]
    model_hint: str | None = None
    input_type: Literal["query", "document"] | None = Field(
        None,
        description="What the texts are: some embedding models (nomic-embed-text) are trained with a task prefix and "
        "retrieve better when queries and documents are marked; providers that don't need it ignore it",
    )


class EmbedResponse(Contract):
    model: str
    dim: int
    vectors: list[list[float]]


class ModelInfo(Contract):
    name: str
    provider: str
    local: bool = True
    context_window: int = 8192
    capabilities: list[str] = Field(default_factory=list, description="chat | embed | vision | json | tools")
    embedding_dim: int | None = None
    available: bool = True


class RoutingDecision(Contract):
    model: str
    provider: str
    local: bool
    reason: str
