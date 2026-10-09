# shared/: the integration contract

Everything two work splits need to agree on lives here, and **only** here. If it isn't in `shared/`, no other split may depend on it.

```text
shared/
├── python/kairos_contracts/     SOURCE OF TRUTH (Python / Pydantic)
│   ├── schema/                  data contracts: Task, AgentProcess, SyscallRequest, SearchHit, Event, …
│   ├── interfaces/              service interfaces (typing.Protocol), grouped by provider:
│   │                              kernel.py, execution.py (P1; BrowserDriver P4) · knowledge.py (P2) ·
│   │                              inference.py, agents.py (P3) · ingestion.py, system.py (P4)
│   ├── testing/fakes.py         a WORKING fake for every interface: develop against these
│   ├── testing/contracts.py     contract test suites: fake AND real implementations must pass
│   ├── api/mock_gateway.py      the executable HTTP/WS API spec and a mock server for the UI
│   ├── examples.py              canonical example payloads (the Apollo demo run)
│   ├── errors.py                KairosError + error codes → HTTP status
│   ├── util.py                  shared semantics: path globs, capability matching, privacy, /org ↔ OKF paths
│   ├── wiring.py                Settings + ServiceBundle + the factory contract
│   └── export.py                regenerates everything below
├── schemas/                     GENERATED JSON Schema (one per model + kairos.schema.json bundle)
├── api/openapi.json             GENERATED gateway OpenAPI
├── ts/                          GENERATED TypeScript types (@kairos/contracts) for web/mobile
├── fixtures/
│   ├── okf/                     test OKF bundle (Acme / Project Apollo), used by every contract test
│   ├── manifests/               test agent manifests
│   └── json/                    GENERATED example payloads (UI mock data)
├── catalogs/                    human-readable registries: events, capabilities, errors, syscalls
└── services/                    "what my split provides", one page per person (P1–P4) with a status table
```

## How each person uses it

| You are… | You code against | You test with |
|---|---|---|
| P1 Kernel & Execution | everyone's interfaces via `ServiceBundle` | `fakes.fake_bundle()`; `EventBus/PolicyEngine/AuditLog/ToolExecutor/SandboxManager/ArtifactStoreContract`, gateway conformance, `tests/integration` |
| P2 Knowledge, Memory & Console | `ModelRouter` (embeddings), `EventBus`, `SourceConverter`s; gateway API for the UI | `FakeModelRouter`, `FakeMarkdownConverter`; `KnowledgeService/MemoryService/ContextFirewallContract`; `kairos-mock-gateway` for the UI |
| P3 Agents & Models | `AgentContext` | `FakeAgentContext` (canned LLM replies, inspect `.syscalls`/`.spawned`); `ModelRouter/AgentRegistry/AgentRuntimeContract` |
| P4 Platform, Data & Demo | `IngestRequest`→`OKFDraft`, `SandboxInfo`, `ResourceSnapshot` | `SourceConverter/BrowserDriver/ResourceProbeContract` with samples in `knowledge/tests/samples/` |

## Rules

1. **Contracts first.** Need a new field, method, event or endpoint? Change `shared/` in its own PR *before* the code that uses it.
2. **Every contract PR** bumps `CONTRACT_VERSION` in `kairos_contracts/__init__.py`, runs `uv run kairos-export-contracts` (and `npm --prefix shared/ts run generate`), updates the fake so it still passes its contract suite, and updates the relevant `catalogs/*.yaml` or `services/*.md`.
3. **Review:** `CODEOWNERS` requires the provider **and** at least one consumer of the touched interface. A breaking change (rename/remove/semantics) needs all four.
4. **Additive by default.** Add optional fields with defaults, and add methods rather than changing signatures. `extra="forbid"` means a producer can't send fields the schema doesn't know, so drift fails loudly in tests.
5. **No private back-channels.** Don't import another split's package. Only `kairosd/wiring.py` imports implementations.
6. **Fakes stay honest.** If your real implementation behaves differently from the fake in a way consumers rely on, fix the contract test and the fake in the same PR.

## Commands

```bash
uv sync --all-packages                              # once
uv run pytest shared/python/tests                   # contracts + fakes + mock gateway
uv run kairos-export-contracts                      # regenerate schemas/, fixtures/json/, api/openapi.json, ts/src/constants.ts
npm --prefix shared/ts install && npm --prefix shared/ts run generate   # regenerate ts/src/kairos.d.ts
uv run kairos-mock-gateway --port 8080 --speed 4    # mock backend: http://localhost:8080/docs
```

## ID prefixes
`T-` task · `SC-` syscall · `APR-` approval · `INV-` tool invocation · `MSG-` IPC message · `MEM-` memory · `CKPT-` checkpoint · `SB-` sandbox · `EV-` event · `RB-` rollback token · `AU-` audit entry. PIDs are integers starting at 101.
