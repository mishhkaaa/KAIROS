# knowledge/ — owner P2, EXCEPT `kairos_knowledge/ingestion/`, `tests/samples/`, `tests/test_ingestion_contract.py` (owner P4)
- P2: OKF I/O, validation, indexing (Postgres FTS + pgvector), hybrid retrieval, graph, KnowledgeFS, ContextFirewall, MemoryService, coherence. Brief: shared/services/P2-knowledge-console.md
- P4: SourceConverters (pure functions → list[OKFDraft]; no DB, no file writes, no events). Brief: shared/services/P4-platform-data-demo.md
- Scope/privacy filtering MUST use kairos_contracts.util.path_allowed / privacy_allows.
- Contract tests run against shared/fixtures/okf (frozen). The demo bundle is data/okf (P4).
