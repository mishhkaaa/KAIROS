"""Memory/knowledge coherence (blueprint §21).

Owner: P2 — Knowledge, Memory & Console

TODO:
  - [x] dependency graph from MemoryRecord.derived_from (memory.MemoryManager.invalidate's recursive CTE)
  - [x] on knowledge.changed: invalidate transitively, reindex, publish memory.invalidated
  - [x] optional watchfiles watcher over okf_dir: manual edits publish knowledge.changed (500 ms debounce)
  - [x] re-consolidate invalidated memories from the reindexed sources (InvalidationReport.reconsolidation_queued)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from kairos_contracts.schema import ChangeKind, Event, EventType, KnowledgeChange
from kairos_contracts.util import okf_file_to_org_path

logger = logging.getLogger("kairos.knowledge.coherence")


class Coherence:
    """knowledge.changed → memory.invalidate(path) → knowledge.reindex([path]) → memory.reconsolidate(stale)."""

    def __init__(self, event_bus: Any, knowledge: Any, memory: Any) -> None:
        self.bus = event_bus
        self.knowledge = knowledge
        self.memory = memory
        self._subscription = None
        self._background: set[asyncio.Task] = set()
        if hasattr(memory, "reconsolidate"):
            memory.reconsolidate_stale = True

    def start(self) -> None:
        if self._subscription is None:
            self._subscription = self.bus.subscribe(EventType.KNOWLEDGE_CHANGED.value, self._on_changed)

    def stop(self) -> None:
        if self._subscription is not None:
            self._subscription.unsubscribe()
            self._subscription = None

    async def _on_changed(self, event: Event) -> None:
        path = event.payload.get("path")
        if not path:
            return
        try:
            report = await self.memory.invalidate(path)
            if self.knowledge is not None:
                await self.knowledge.reindex([path])
        except Exception:  # a failing handler must not break the bus; log and move on
            logger.exception("coherence failed for %s", path)
            return
        if getattr(report, "reconsolidation_queued", False):
            # In the background: it calls the model once per memory, and the bus shouldn't wait for that.
            task = asyncio.create_task(self._reconsolidate(report.invalidated))
            self._background.add(task)
            task.add_done_callback(self._background.discard)

    async def _reconsolidate(self, memory_ids: list[str]) -> None:
        try:
            done = await self.memory.reconsolidate(memory_ids)
            logger.info("re-derived %d of %d stale memories", len(done), len(memory_ids))
        except Exception:
            logger.exception("re-consolidation failed for %s", memory_ids)


async def watch_bundle(okf_dir: Path, event_bus: Any, stop: asyncio.Event | None = None, debounce_ms: int = 500) -> None:
    """Publish knowledge.changed for manual edits to *.md files under okf_dir until `stop` is set."""
    from watchfiles import Change, awatch

    okf_dir = Path(okf_dir).resolve()
    kinds = {Change.added: ChangeKind.CREATED, Change.modified: ChangeKind.UPDATED, Change.deleted: ChangeKind.DELETED}
    async for changes in awatch(okf_dir, debounce=debounce_ms, stop_event=stop, recursive=True):
        latest: dict[str, ChangeKind] = {}
        for change, raw in changes:
            p = Path(raw)
            if p.suffix != ".md" or p.name.lower() == "readme.md":
                continue
            latest[okf_file_to_org_path(p.resolve().relative_to(okf_dir).as_posix())] = kinds[change]
        for path, kind in latest.items():
            await event_bus.publish(
                Event(
                    type=EventType.KNOWLEDGE_CHANGED,
                    source="knowledge.watcher",
                    payload=KnowledgeChange(path=path, change=kind).model_dump(mode="json"),
                )
            )


__all__ = ["Coherence", "watch_bundle"]
