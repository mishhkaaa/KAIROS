"""The /org knowledge filesystem — the KnowledgeService implementation that ties the above together.

Owner: P2 — Knowledge, Memory & Console

TODO:
  - [x] read/list/search/traverse/ingest/reindex/validate per kairos_contracts.interfaces.KnowledgeService
  - [x] raise KNOWLEDGE_NOT_FOUND / KNOWLEDGE_FORBIDDEN
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    ChangeKind,
    Event,
    EventType,
    EvidenceSet,
    GraphResult,
    IngestRequest,
    IngestResult,
    KnowledgeChange,
    KnowledgeEntry,
    KnowledgeListing,
    KnowledgeObject,
    OKFDraft,
    Principal,
    PrivacyLevel,
    SearchQuery,
    ValidationReport,
)
from kairos_contracts.util import path_allowed, privacy_allows

from ..coherence import watch_bundle
from ..graph import GraphStore
from ..indexing import EMBED_SCHEME, Indexer, PgStore
from ..okf import OKFBundle
from ..retrieval import HybridRetriever
from ..validation import validate_bundle

logger = logging.getLogger("kairos.knowledge.kfs")


class KnowledgeFS:
    def __init__(
        self,
        okf_dir: Path,
        store: PgStore,
        models: Any,
        firewall: Any,
        event_bus: Any = None,
        converters: list[Any] | None = None,
        watch: bool = False,
    ) -> None:
        self.bundle = OKFBundle(okf_dir)
        self.store = store
        self.models = models
        self.indexer = Indexer(store, models)
        self.retriever = HybridRetriever(store, models, firewall)
        self.graph = GraphStore(store)
        self.bus = event_bus
        self.converters = converters or []
        self.objects: dict[str, KnowledgeObject] = {}
        self._lock = asyncio.Lock()
        self._ready = False
        self.watch = watch
        self._watch_stop: asyncio.Event | None = None
        self._watch_task: asyncio.Task | None = None

    async def _ensure_ready(self) -> None:
        if self._ready:
            return
        async with self._lock:
            if self._ready:
                return
            if self.models is not None:
                from kairos_contracts.schema import EmbedRequest

                probe = await self.models.embed(EmbedRequest(texts=["_dimension_probe_"], input_type="document"))
                dim, model_name = probe.dim, f"{probe.model}+{EMBED_SCHEME}"
            else:
                dim, model_name = 64, "none"
            await self.store.migrate(dim, model_name)
            await self._sync_index(None)
            self._ready = True
            if self.watch and self.bus is not None:
                # Started here, not in the factory: factories are sync and run before any event loop exists.
                self._watch_stop = asyncio.Event()
                self._watch_task = asyncio.create_task(watch_bundle(self.bundle.root, self.bus, self._watch_stop))

    async def aclose(self) -> None:
        """Stop the watcher (if any) and close the connection pool."""
        if self._watch_task is not None and self._watch_stop is not None:
            self._watch_stop.set()
            await self._watch_task
            self._watch_task = None
        await self.store.close()

    # --- access control (mirrors kairos_contracts.testing.fakes.FakeKnowledgeService)

    def _visible(self, obj: KnowledgeObject, p: Principal) -> bool:
        return path_allowed(obj.path, p.data_scopes) and privacy_allows(obj.frontmatter.privacy, p.max_privacy)

    def _get(self, path: str, p: Principal) -> KnowledgeObject:
        path = path.rstrip("/") or "/org"
        obj = self.objects.get(path)
        if obj is None:
            raise KairosError("KNOWLEDGE_NOT_FOUND", path)
        if not self._visible(obj, p):
            raise KairosError("KNOWLEDGE_FORBIDDEN", path)
        return obj

    # --- KnowledgeService

    async def read(self, path: str, principal: Principal) -> KnowledgeObject:
        await self._ensure_ready()
        return self._get(path, principal)

    async def list(self, path: str, principal: Principal) -> KnowledgeListing:
        await self._ensure_ready()
        base = path.rstrip("/") or "/org"
        children: dict[str, bool] = {}
        for p in self.objects:
            if p.startswith(base + "/"):
                seg = p[len(base) + 1 :].split("/")[0]
                child = f"{base}/{seg}"
                children[child] = children.get(child, False) or p != child
        if not children and base not in self.objects:
            raise KairosError("KNOWLEDGE_NOT_FOUND", base)
        entries = []
        for child, is_dir in sorted(children.items()):
            obj = self.objects.get(child)
            if obj and not self._visible(obj, principal):
                continue
            if (
                not obj
                and not path_allowed(child, principal.data_scopes)
                and not any(g.startswith(child + "/") for g in principal.data_scopes)
            ):
                continue
            entries.append(
                KnowledgeEntry(
                    path=child,
                    title=obj.frontmatter.title if obj else child.rsplit("/", 1)[-1],
                    type=obj.frontmatter.type if obj else "index",
                    is_dir=is_dir,
                    privacy=obj.frontmatter.privacy if obj else PrivacyLevel.INTERNAL,
                )
            )
        return KnowledgeListing(path=base, entries=entries)

    async def search(self, query: SearchQuery, principal: Principal) -> EvidenceSet:
        await self._ensure_ready()
        return await self.retriever.search(query, principal)

    async def traverse(self, path: str, principal: Principal, depth: int = 1, relations: list[str] | None = None) -> GraphResult:
        await self._ensure_ready()
        self._get(path, principal)  # KNOWLEDGE_NOT_FOUND / KNOWLEDGE_FORBIDDEN on a bad root
        return await self.graph.traverse(path, principal, depth, relations)

    async def ingest(self, request: IngestRequest) -> IngestResult:
        """converter → write OKF → validate → index changed paths → knowledge.changed per path."""
        await self._ensure_ready()
        result = IngestResult()
        converter = next((c for c in self.converters if c.can_convert(request)), None)
        if converter is None:
            result.errors.append(f"no converter can handle {request.source_type.value} {request.uri}")
            return result
        try:
            drafts: list[OKFDraft] = await converter.convert(request)
        except Exception as e:  # noqa: BLE001 — a converter failure is reported in the result, not raised
            logger.warning("converter %s failed on %s: %s", converter.name, request.uri, e)
            result.errors.append(f"{converter.name}: {e}")
            return result

        changes: list[KnowledgeChange] = []
        written: set[str] = set()
        for draft in drafts:
            try:
                change = self.bundle.write_draft(draft)
            except Exception as e:  # noqa: BLE001 — one bad draft must not abort the others
                result.errors.append(f"{draft.okf_file}: {e}")
                continue
            if change.old_hash == change.new_hash:
                result.skipped.append(f"{change.path} (unchanged)")
                continue
            (result.created if change.change == ChangeKind.CREATED else result.updated).append(change.path)
            changes.append(change)
            written.add(draft.okf_file)
        if not changes:
            return result

        for issue in validate_bundle(self.bundle).issues:
            if issue.severity == "error" and issue.okf_file in written:
                result.errors.append(f"{issue.okf_file}: {issue.message}")

        await self._sync_index({c.path for c in changes})
        if self.bus is not None:
            for change in changes:
                await self.bus.publish(
                    Event(type=EventType.KNOWLEDGE_CHANGED, source="knowledge.kfs", payload=change.model_dump(mode="json"))
                )
        return result

    async def reindex(self, paths: list[str] | None = None) -> int:
        await self._ensure_ready()
        count = await self._sync_index(set(paths) if paths else None)
        if self.bus is not None:
            await self.bus.publish(Event(type=EventType.KNOWLEDGE_REINDEXED, source="knowledge.kfs", payload={"count": count}))
        return count

    async def _sync_index(self, paths: set[str] | None) -> int:
        """Reload the bundle and bring the index in line with it: upsert present objects (re-embedding
        changed ones) and drop rows whose file is gone. Returns the number of objects indexed."""
        self.objects = self.bundle.load_all()
        indexed = set(await self.store.all_paths())
        gone = (indexed if paths is None else paths & indexed) - self.objects.keys()
        for path in gone:
            await self.store.delete_object(path)
        await self.indexer.index_objects(self.objects, only_paths=paths)
        return len(self.objects) if paths is None else len(paths & self.objects.keys())

    async def validate(self) -> ValidationReport:
        await self._ensure_ready()
        return validate_bundle(self.bundle)


__all__ = ["KnowledgeFS"]
