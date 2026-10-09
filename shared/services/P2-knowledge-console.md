# P2 Knowledge, Memory & Console: what this split provides
Packages: `knowledge/` (`kairos_knowledge`, minus `ingestion/`), `apps/web/`, `agents/kairos_agents/adapters/` (stretch)

| Provides | Kind | Consumers | Fake until ready | Contract |
|---|---|---|---|---|
| `KnowledgeService` (`/org` filesystem, hybrid search, graph, ingest pipeline) | interface | P1 (for agents + gateway) | `FakeKnowledgeService` | `KnowledgeServiceContract` |
| `ContextFirewall` | interface | KnowledgeFS, P1 context | `FakeContextFirewall` | `ContextFirewallContract` |
| `MemoryService` | interface | P1 context/lifecycle | `FakeMemoryService` | `MemoryServiceContract` |
| Web console | UI over the gateway | humans / demo | mock gateway | — |
| NOOA adapter (stretch) | runtime adapter | P3 runtime | falls back to custom | — |

**Access rule:** every read filters by `principal.data_scopes` (`util.path_allowed`) and `principal.max_privacy` (`util.privacy_allows`). **Events published:** `knowledge.changed`, `knowledge.reindexed`, `memory.invalidated`, `memory.consolidated`.
**Consumes:** `ModelRouter.embed/embedding_dim/generate` (P3), `EventBus` (P1), `services.converters` (P4), and the gateway (P1) for the UI. Owns the `postgres` schema.

**Behaviour notes for consumers**
- `search()` screens every hit's **full body** with the firewall, so P1's `ctx.search()` must not screen again (hits already carry `firewall_flags`). `untrusted_source` is added only when `provenance.trust == untrusted`.
- `filtered_by_policy` counts only objects removed by the principal's `data_scopes` / `max_privacy`, never by the query's own `types` / `tags` / `min_trust`.
- The first call on a fresh `KnowledgeFS` migrates the schema and indexes `settings.okf_dir` (a few seconds). A change of embedding model or dim drops the embeddings and re-embeds everything automatically.
- `ingest()` reports converter/validation problems in `IngestResult.errors` (it doesn't raise). Re-ingesting identical content lands in `skipped` and publishes no event.
- `build_memory_service` starts coherence: every `knowledge.changed` → `memory.invalidate(path)` → `knowledge.reindex([path])` → `memory.invalidated` + `knowledge.reindexed`. The file watcher (`coherence.watch_bundle`) is opt-in: with `KAIROS_KNOWLEDGE_WATCH=true` (contract 0.3.0) `KnowledgeFS` starts it on its first call and republishes manual edits under `okf_dir` as `knowledge.changed`.
- CLI: `uv run kairos-okf validate | search "<text>" | reindex | ingest <path> --target /org/...`.
- **Any event loop:** Postgres I/O runs on worker threads (sync psycopg + `asyncio.to_thread`), so the knowledge and memory services work on every asyncio loop, including uvicorn's default `ProactorEventLoop` on Windows, which Playwright and asyncio subprocesses need. No process needs a loop-policy change for P2.
- **Memory recall:** a memory with no word in common with the query is only recalled when its embedding cosine is ≥ `RECALL_KEYWORD_GATE_COSINE` (0.42, tuned on `nomic-embed-text`: related paraphrases score 0.375–0.839, unrelated pairs 0.320–0.408). `test_recall_real_embeddings.py` guards it when Ollama is up.

## How it is tested
| Suite | What it proves | Needs |
|---|---|---|
| `knowledge/tests/test_contract.py` | Knowledge, firewall and memory contracts on the real implementations | Postgres (skips if unreachable) |
| `test_retrieval_units.py` | fused ordering, per-mode scores in [0,1], `filtered_by_policy` counting | Postgres |
| `test_memory_units.py` | 3-hop invalidation CTE, stale recall, working-set budget + pinning + `<untrusted-data>`, rehydrate, consolidate | Postgres |
| `test_ingest.py` | converter → files + index + `knowledge.changed`; unchanged = no-op; deleted files leave the index | Postgres |
| `test_coherence.py` | editing an OKF file → `knowledge.changed` → `memory.invalidated` (right `affected_agents`) → reindexed and searchable | Postgres |
| `test_chunker.py`, `test_validation.py` | chunking, linter rules; the fixtures validate with zero errors | nothing |

## Live invalidation demo (S2)
The demo steps are in `docs/DEMO_SCRIPT.md` (step 18). In short:
1. Run `kairosd` with `KAIROS_KNOWLEDGE_WATCH=true` after a completed run. The finance and engineering agents `ctx.remember` their findings, derived from the documents they cited.
2. Append a line to `data/okf/finance/cloud-bill-2026-09.md`.
3. Within ~1 s: `knowledge.changed` → `memory.invalidated` (count + affected agents; derived-of-derived memories too) → `knowledge.reindexed`. The console toasts the invalidation on every page, and the explorer shows the edit without a reload. On `integration/m3` (2026-09-28, real models) the toast came after 0.2 s and named only finance-agent; the explorer updated after 0.9 s, and engineering-agent's memories stayed fresh.
4. Reset with `git checkout data/okf/finance/cloud-bill-2026-09.md`.

Security policy v2 (`data/demo-assets/security-policy-v2.md`) reindexes but invalidates nothing until agents consult `/org/policies` (P3 follow-up).

## Status (owner keeps this current)
| Item | Status |
|---|---|
| OKF I/O + validation | ✅ |
| Postgres schema + indexing | ✅ (auto re-embed on model/dim change) |
| Hybrid retrieval + graph + scope filter | ✅ |
| Context firewall | ✅ regex; LLM classifier behind `KAIROS_FIREWALL_LLM` (contract 0.8.0, off by default): its catches carry `instruction_like` + `instruction_like_llm` and log a warning on `kairos.knowledge.firewall` |
| Memory manager + coherence | ✅ (re-consolidation queue not done) |
| Ingest pipeline (uses P4 converters) | ✅ all five of P4's converters through the pipeline; output byte-identical to P4's committed data/okf |
| Run under P1's real kernel (T9 part 1) | ✅ on `integration/m3` |
| Real embeddings (T9 part 2) | ✅ with P3's router + `nomic-embed-text` (768-dim): gate 0.5 → 0.42; RRF graph weight checked (0/0.1 → 9/10, 0.25 slips, ≥0.5 collapses), stays 0.1. Full index of P4's 73 files: 38.7 s; model switch re-embeds 107 chunks in 14 s |
| UI: composer · timeline · tree · approvals | ✅ on `integration/m3` (mock + real gateway); the tree re-fits on resize |
| UI: audit · explorer · monitor · result | ✅ on `integration/m3`; the recovery plan and screenshots render in W7/W8 (contract 0.4.0 artifact route); firewall-flagged retrievals come from `knowledge.retrieved.flagged` |
| Retrieval QA ≥ 9/10 on data/okf | ✅ 10/10 after P4's ADR-042 wording fix (`test_retrieval_qa.py`) |
| Dress rehearsal (real P1 + P3 + P4, llama3.2:3b) | ✅ `integration/m3`, driven through the console: 65.9 s and 75.1 s, 1 approval each; flagged vendor email in W2 with no agent acting on it; cited root causes; 6.2 lakh / 31%; screenshots in W7/W8; hash chain intact in W5 |
| Live invalidation demo (S2) | ✅ cloud-bill edit (DEMO_SCRIPT step 18); policy v2 waits on P3 |
