"""Knowledge / relationship graph.

Owner: P2 — Knowledge, Memory & Console

TODO:
  - [x] edges from markdown links + frontmatter.related + owner/part_of fields (indexing/indexer.py)
  - [x] traverse(path, depth, relations) with scope filtering
"""

from __future__ import annotations

from typing import Any

from kairos_contracts.schema import GraphEdge, GraphResult, KnowledgeEntry, Principal
from kairos_contracts.schema.common import PrivacyLevel
from kairos_contracts.util import path_allowed, privacy_allows

from ..indexing.store import PgStore


class GraphStore:
    def __init__(self, store: PgStore) -> None:
        self.store = store

    async def traverse(self, root: str, principal: Principal, depth: int = 1, relations: list[str] | None = None) -> GraphResult:
        seen = {root}
        frontier = [root]
        edges: list[GraphEdge] = []
        edge_seen: set[tuple[str, str, str]] = set()

        for _ in range(max(depth, 0)):
            if not frontier:
                break
            rows = await self.store.neighbors(frontier, relations)
            nxt: list[str] = []
            for row in rows:
                src, dst, relation, weight = row["src"], row["dst"], row["relation"], row["weight"]
                if src not in frontier:
                    continue  # keep edges outgoing from the current frontier only
                target_obj = await self.store.get_object_row(dst)
                if target_obj is None or not self._visible(target_obj, principal):
                    continue
                key = (src, dst, relation)
                if key not in edge_seen:
                    edge_seen.add(key)
                    edges.append(GraphEdge(src=src, dst=dst, relation=relation, weight=weight))
                if dst not in seen:
                    seen.add(dst)
                    nxt.append(dst)
            frontier = nxt

        nodes: list[KnowledgeEntry] = []
        for path in sorted(seen):
            obj = await self.store.get_object_row(path)
            if obj is None:
                continue
            nodes.append(KnowledgeEntry(path=path, title=obj["title"], type=obj["type"], privacy=PrivacyLevel(obj["privacy"])))
        return GraphResult(root=root, nodes=nodes, edges=edges)

    def _visible(self, obj: dict[str, Any], principal: Principal) -> bool:
        return path_allowed(obj["path"], principal.data_scopes) and privacy_allows(
            PrivacyLevel(obj["privacy"]), principal.max_privacy
        )


__all__ = ["GraphStore"]
