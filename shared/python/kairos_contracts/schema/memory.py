"""Memory manager: working / episodic / semantic memory and the working set (context window)."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from .common import Contract, Pid, TaskId, utcnow


class MemoryKind(StrEnum):
    WORKING = "working"      # RAM   — current task context
    EPISODIC = "episodic"    # cache — past runs, failures, feedback
    SEMANTIC = "semantic"    # disk  — consolidated facts, procedures


class MemoryScope(StrEnum):
    TASK = "task"
    AGENT = "agent"
    USER = "user"
    ORG = "org"


class MemoryRecord(Contract):
    memory_id: str = Field(description='"MEM-..."')
    kind: MemoryKind
    scope: MemoryScope
    org_id: str
    owner: str = Field(description="agent name, user_id or org_id depending on scope")
    task_id: TaskId | None = None
    content: str
    summary: str | None = None
    derived_from: list[str] = Field(
        default_factory=list,
        description="/org paths or MEM ids this was derived from — drives invalidation",
    )
    tags: list[str] = Field(default_factory=list)
    importance: float = Field(0.5, ge=0.0, le=1.0)
    stale: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    last_used_at: datetime | None = None


class MemoryQuery(Contract):
    text: str
    org_id: str
    kinds: list[MemoryKind] = Field(default_factory=lambda: [MemoryKind.EPISODIC, MemoryKind.SEMANTIC])
    scopes: list[MemoryScope] = Field(default_factory=lambda: list(MemoryScope))
    owner: str | None = None
    task_id: TaskId | None = None
    include_stale: bool = False
    top_k: int = Field(5, ge=1, le=50)


class WorkingSetItem(Contract):
    ref: str = Field(description="/org path, MEM id, artifact ref or 'inline'")
    source: str = Field(description="evidence | memory | tool_output | plan | message")
    content: str
    tokens: int
    pinned: bool = False


class WorkingSet(Contract):
    """What actually goes into the model's context for a pid. LOAD/EVICT operate on this."""

    pid: Pid
    token_budget: int
    tokens_used: int = 0
    items: list[WorkingSetItem] = Field(default_factory=list)


class InvalidationReport(Contract):
    """Payload of the memory.invalidated event."""

    source: str = Field(description="The /org path or MEM id that changed")
    invalidated: list[str] = Field(default_factory=list, description="MEM ids marked stale")
    affected_agents: list[str] = Field(default_factory=list)
    reconsolidation_queued: bool = False
