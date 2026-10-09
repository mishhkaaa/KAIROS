# knowledge/ — P2 Knowledge & Memory (`kairos_knowledge`) + P4 converters (`ingestion/`)
- P2: OKF I/O, validation, indexing (Postgres FTS + pgvector), hybrid retrieval, graph, KnowledgeFS, context firewall, memory manager, coherence, `kairos-okf` CLI. Brief: [P2](../shared/services/P2-knowledge-console.md)
- P4: `ingestion/` SourceConverters + `tests/samples/` + `tests/test_ingestion_contract.py`. Brief: [P4](../shared/services/P4-platform-data-demo.md)
- Test data: `shared/fixtures/okf/` (frozen). Demo data: `data/okf/` (P4).

```bash
docker compose -f infra/compose/docker-compose.yml up -d postgres
uv run pytest knowledge/tests -rs
```
