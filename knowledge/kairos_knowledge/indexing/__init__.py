"""Derived, disposable indexes (OKF stays the source of truth).

Owner: P2 — Knowledge, Memory & Console

TODO:
  - [x] chunk by heading; embeddings via ModelRouter.embed (dim from embedding_dim())
  - [x] Postgres: pgvector table + tsvector full-text; incremental by content_hash
  - [x] reindex() rebuilds from scratch; publish knowledge.reindexed (kfs.KnowledgeFS.reindex)
"""

from .indexer import Indexer, chunk_body
from .store import EMBED_SCHEME, PgStore

__all__ = ["EMBED_SCHEME", "Indexer", "PgStore", "chunk_body"]
