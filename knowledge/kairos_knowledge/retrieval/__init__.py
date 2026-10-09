"""Hybrid retrieval (blueprint §17).

Owner: P2 — Knowledge, Memory & Console

TODO:
  - [x] lexical (FTS) + semantic (pgvector) + graph neighbours -> reciprocal rank fusion
  - [x] filters: scope, types, tags, min_trust, freshness; principal data_scopes + max_privacy (util.path_allowed/privacy_allows)
  - [x] report filtered_by_policy; progressive disclosure via index.md summaries
  - [ ] stretch: cross-encoder / LLM rerank
"""

from .retriever import HybridRetriever

__all__ = ["HybridRetriever"]
