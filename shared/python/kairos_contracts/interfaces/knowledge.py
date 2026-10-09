"""Interfaces PROVIDED BY P2 (Knowledge, Memory & Console).

Consumers: the kernel's AgentContext (P1) forwards agent calls here after scope checks;
the gateway (P1) exposes them to the UI (P2); P3's planner uses them indirectly via AgentContext.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..schema import (
    EvidenceSet,
    GraphResult,
    IngestRequest,
    IngestResult,
    InvalidationReport,
    KnowledgeListing,
    KnowledgeObject,
    MemoryQuery,
    MemoryRecord,
    Principal,
    SearchHit,
    SearchQuery,
    ValidationReport,
    WorkingSet,
)


@runtime_checkable
class KnowledgeService(Protocol):
    """The organizational knowledge filesystem (/org/...), backed by the OKF bundle + indexes.

    Every read method takes the Principal and MUST filter by principal.data_scopes and
    principal.max_privacy (use kairos_contracts.util.path_allowed / privacy_allows).
    Out-of-scope reads raise KairosError("KNOWLEDGE_FORBIDDEN"); missing paths raise ("KNOWLEDGE_NOT_FOUND").
    """

    async def read(self, path: str, principal: Principal) -> KnowledgeObject: ...
    async def list(self, path: str, principal: Principal) -> KnowledgeListing: ...
    async def search(self, query: SearchQuery, principal: Principal) -> EvidenceSet: ...
    async def traverse(self, path: str, principal: Principal, depth: int = 1, relations: list[str] | None = None) -> GraphResult: ...

    async def ingest(self, request: IngestRequest) -> IngestResult:
        """Convert source material into OKF files, then index. Publishes knowledge.changed per path."""

    async def reindex(self, paths: list[str] | None = None) -> int:
        """Rebuild derived indexes (all when None). Returns number of objects indexed. Publishes knowledge.reindexed."""

    async def validate(self) -> ValidationReport:
        """Lint the OKF bundle: frontmatter schema, broken links, duplicate titles."""


@runtime_checkable
class ContextFirewall(Protocol):
    """Separates facts from instruction-like content in retrieved text (blueprint §29)."""

    async def screen(self, hits: list[SearchHit]) -> list[SearchHit]:
        """Return hits with firewall_flags set (and snippets neutralised if needed). Never drops hits silently."""


@runtime_checkable
class MemoryService(Protocol):
    async def store(self, record: MemoryRecord) -> str: ...
    async def recall(self, query: MemoryQuery) -> list[MemoryRecord]: ...

    async def build_working_set(self, pid: int, goal: str, evidence: EvidenceSet, memories: list[MemoryRecord], token_budget: int) -> WorkingSet:
        """LOAD + EVICT: choose what fits in the context window for this pid."""

    async def summarize(self, memory_ids: list[str]) -> MemoryRecord:
        """SUMMARIZE: compress several memories into one (new record, derived_from = inputs)."""

    async def consolidate(self, task_id: str) -> list[MemoryRecord]:
        """CONSOLIDATE: promote useful episodic memories of a finished task into semantic memory."""

    async def invalidate(self, source: str) -> InvalidationReport:
        """INVALIDATE: mark everything transitively derived_from `source` stale. Publishes memory.invalidated."""

    async def rehydrate(self, pid: int) -> WorkingSet | None:
        """REHYDRATE: rebuild a pid's last working set after restart."""
