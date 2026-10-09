# KAIROS: folder structure guide

What every folder is for, who owns it, and which files are hand-written, generated or frozen.
Owner key: **P1** Kernel & Execution · **P2** Knowledge, Memory & Console · **P3** Agents & Models · **P4** Platform, Data & Demo · **ALL** shared (contract; changes need review).
Legend: ✍️ hand-written · ⚙️ generated (never edit by hand) · 🧊 frozen test data (contract) · 🚧 skeleton, implementation pending.

## 1. Top level

```text
KAIROS/
├── AGENTS.md / CLAUDE.md        ALL  rules for coding agents (CLAUDE.md imports AGENTS.md); nested copies per folder
├── README.md                    ALL  entry point + repo map
├── pyproject.toml               ALL  uv workspace root: members, pytest + ruff config
├── uv.lock                      ⚙️   resolved Python deps (commit it; don't edit by hand)
├── .env.example                 ALL  every setting (KAIROS_*) and the fake|real switches → copy to .env
├── .github/                     ALL  CODEOWNERS, CI workflow, PR template
├── docs/                        ALL  master plan, per-person briefs, this guide, demo script
├── shared/                      ALL  THE CONTRACT between the four splits
├── kernel/                      P1   AI kernel + gateway + CLI            (python package kairos_kernel)
├── execution/                   P1   tools, sandboxes, artifacts, mock Jira (kairos_execution; browser/ is P4)
├── kairosd/                     P1   server process / composition root    (kairosd)
├── policies/                    P1   execution policies (YAML)
├── knowledge/                   P2   knowledge fabric + memory            (kairos_knowledge; ingestion/ is P4)
├── apps/                        P2   web console (Next.js); mobile later
├── agents/                      P3   agent SDK, runtime, registry, agents (kairos_agents; adapters/ is P2)
├── models/                      P3   model providers + router             (kairos_models; gpu/ is P4)
├── infra/                       P4   docker compose, systemd, appliance, GPU
├── data/                        P4   demo organization's OKF bundle
├── scripts/                     P4   dev tooling (context packs for non-Claude-Code members)
└── tests/integration/           ALL  end-to-end Apollo scenario (the integration gate)
```

Each Python package is a **uv workspace member** with its own `pyproject.toml`, a `factory.py` (its only public entry point), a `tests/` folder with a `test_contract.py` that skips until implemented, and a `README.md`.

## 2. `shared/`: the contract (ALL)

```text
shared/
├── README.md                    rules for changing contracts; who uses what
├── python/                      package "kairos-contracts"
│   ├── pyproject.toml
│   ├── kairos_contracts/
│   │   ├── __init__.py          ✍️ CONTRACT_VERSION (bump on every change)
│   │   ├── schema/              ✍️ Pydantic data contracts, one module per domain:
│   │   │   ├── common.py            ids (TaskId, Pid, ArtifactRef, KnowledgePath, Capability), enums, Principal,
│   │   │   │                        ResourceQuota/Usage, Provenance, ErrorInfo
│   │   │   ├── task.py              TaskCreate, Task, TaskResult, TaskStatus
│   │   │   ├── process.py           AgentProcess, AgentState + ALLOWED_TRANSITIONS, SpawnRequest, Checkpoint
│   │   │   ├── syscall.py           SyscallRequest, PolicyDecision, SyscallResult, Approval
│   │   │   ├── tools.py             ToolSpec/Operation, ToolInvocation, ToolResult, Verification, Sandbox*, BrowserPage
│   │   │   ├── knowledge.py         OKFFrontmatter, KnowledgeObject, OKFDraft, SearchQuery/Hit, EvidenceSet, Graph*, Ingest*
│   │   │   ├── memory.py            MemoryRecord, MemoryQuery, WorkingSet, InvalidationReport
│   │   │   ├── inference.py         ModelRequest/Response, ChatMessage, Embed*, ModelInfo, RoutingDecision
│   │   │   ├── agents.py            AgentManifest (agent package format), Plan, AgentResult
│   │   │   ├── ipc.py               A2AMessage
│   │   │   ├── events.py            Event envelope + EventType catalog
│   │   │   ├── audit.py             AuditEntry, RunTimeline
│   │   │   ├── policy.py            PolicyDocument (policies/*.yaml)
│   │   │   └── system.py            ComponentHealth, ResourceSnapshot, SystemStatus
│   │   ├── interfaces/          ✍️ typing.Protocol service interfaces, by provider:
│   │   │   ├── kernel.py            P1: EventBus, PolicyEngine, AuditLog, AgentContext (the agent ABI)
│   │   │   ├── execution.py         P1: ToolExecutor, SandboxManager, ArtifactStore · P4: BrowserDriver
│   │   │   ├── knowledge.py         P2: KnowledgeService, ContextFirewall, MemoryService
│   │   │   ├── inference.py         P3: ModelProvider, ModelRouter
│   │   │   ├── agents.py            P3: AgentRegistry, AgentRuntime
│   │   │   ├── ingestion.py         P4: SourceConverter
│   │   │   └── system.py            P4: ResourceProbe
│   │   ├── testing/
│   │   │   ├── fakes.py         ✍️ a WORKING in-memory fake of every interface + fake_bundle() + FakeAgentContext
│   │   │   └── contracts.py     ✍️ contract test suites (<Interface>Contract): the fake AND the real impl must pass
│   │   ├── api/
│   │   │   ├── __init__.py          auth headers, WS path, route_signatures() for conformance
│   │   │   └── mock_gateway.py      executable HTTP/WS spec + mock server (replays the Apollo run)
│   │   ├── examples.py          ✍️ canonical example payloads (the demo run frozen in time)
│   │   ├── errors.py            ✍️ KairosError + error code → HTTP status
│   │   ├── util.py              ✍️ shared semantics: path globs, capability matching, privacy, /org↔OKF paths, tokens
│   │   ├── wiring.py            ✍️ Settings (KAIROS_* env), ServiceBundle, the factory contract, component list
│   │   └── export.py            ✍️ regenerates everything marked ⚙️ below
│   └── tests/                   ✍️ fakes pass their suites; examples validate; mock gateway end-to-end flow
├── schemas/                     ⚙️ JSON Schema per model + kairos.schema.json bundle
├── api/openapi.json             ⚙️ gateway OpenAPI (from mock_gateway)
├── ts/                          TypeScript package @kairos/contracts used by apps/web
│   ├── package.json             ✍️ `npm run generate` (json-schema-to-typescript)
│   └── src/                     ⚙️ kairos.d.ts (types), constants.ts (EventType, ALLOWED_TRANSITIONS, headers); index.ts ✍️
├── fixtures/
│   ├── okf/                     🧊 test OKF bundle "Acme / Project Apollo" (incl. a prompt-injection email)
│   ├── manifests/               🧊 test agent manifests (planner, finance, engineering, research, action)
│   └── json/                    ⚙️ example payloads (UI mock data)
├── catalogs/                    ✍️ events.yaml (producer/consumer/payload), capabilities.yaml, errors.yaml, syscalls.yaml
└── services/                    ✍️ one "what I provide" sheet per split, with a status table the owner keeps current
```

## 3. P1: `kernel/`, `execution/`, `kairosd/`, `policies/`

```text
kernel/kairos_kernel/
├── factory.py        build_event_bus / build_policy_engine / build_audit_log / build_kernel_app
├── tasks/            TaskManager: create/queue/cancel/resume; derives TaskStatus from the process tree
├── process/          ProcessTable: PIDs (from 101), AgentProcess records, tree, state-machine enforcement
├── scheduler/        priority queues (high/normal/background), admission control, agent matching
├── lifecycle/        spawn/run/pause/resume/kill/retry/checkpoint, one asyncio.Task per PID
├── quota/            token / tool-call / wall-clock / children budgets
├── context/          KernelAgentContext (implements AgentContext) + IPC mailboxes
├── syscalls/         SyscallGateway: validate → policy → approval → transaction
├── policy/           YAML PolicyEngine over policies/*.yaml
├── approvals/        approval queue; futures resolved by the UI/API
├── transactions/     execute → verify → commit | rollback
├── events/           EventBus (in-memory → Redis Streams) + event-driven wake-ups
├── audit/            append-only journal (SQLite), RunTimeline
├── persistence/      state store + boot recovery
├── gateway/          FastAPI REST + WebSocket (must match shared/api/openapi.json)
└── cli/              ai-ps, ai-tree, ai-top, ai-kill, ai-audit, ai-checkpoint, ai-resume, ai-mount
kernel/tests/test_contract.py   EventBus/Policy/Audit suites + gateway route conformance

execution/
├── kairos_execution/
│   ├── factory.py    build_artifact_store / build_sandbox_manager / build_tool_executor
│   ├── artifacts/    FsArtifactStore (artifact://task/name ↔ $KAIROS_DATA_DIR/artifacts)
│   ├── sandbox/      DockerSandboxManager (limits, network none/allowlist, cleanup)
│   ├── tools/        ToolExecutor dispatching to backends (jira, fs, browser, sandbox, mcp)
│   ├── files/        workspace file ops with path jail + rollback
│   ├── connectors/   jira_mock.py: mock Jira service (:8090) + jira tool backend
│   ├── mcp/          MCP client adapter (stretch)
│   └── browser/      ── P4 ── BrowserDriver (Playwright client into the sandbox)
├── images/sandbox-base/Dockerfile       P1  generic task sandbox
├── images/sandbox-browser/Dockerfile    P4  Playwright run-server image
└── tests/  test_contract.py (P1) · test_browser_contract.py (P4)

kairosd/kairosd/wiring.py   REGISTRY: component → fake | real factory; build_services(); build_app()
kairosd/kairosd/main.py     `uv run kairosd [--print-wiring]`
policies/*.yaml             default-v1 (baseline), finance-agent-v1, project-updates-v1 (the demo's approval gate)
```

## 4. P2: `knowledge/` (except ingestion) and `apps/`

```text
knowledge/kairos_knowledge/
├── factory.py        build_context_firewall / build_knowledge_service / build_memory_service
├── okf/              OKF bundle I/O: parse/serialize frontmatter, links, hashing, write drafts
├── validation/       OKF linter → ValidationReport
├── indexing/         chunking, embeddings, Postgres (FTS + pgvector) schema & upserts
├── retrieval/        hybrid search: lexical + semantic + graph → RRF fusion, scope/privacy filters
├── graph/            relationship edges + traversal
├── kfs/              KnowledgeFS: the KnowledgeService implementation tying it all together (+ ingest pipeline)
├── firewall/         ContextFirewall: flags instruction-like text in evidence
├── memory/           MemoryManager: store/recall/working set/summarize/consolidate/invalidate/rehydrate
├── coherence/        knowledge.changed → invalidate → reindex → notify
├── cli.py            kairos-okf validate|ingest|reindex|search
└── ingestion/        ── P4 ── SourceConverters (markdown, jira-json, slack, csv, pdf) + factory.build_converters
knowledge/tests/  test_contract.py (P2) · test_ingestion_contract.py + samples/ (P4)

apps/web/          Next.js console. lib/kairos-client.ts = the only backend access (typed by @kairos/contracts)
agents/kairos_agents/adapters/   ── P2 (stretch) ── NOOA adapter
```

## 5. P3: `agents/`, `models/` (except gpu)

```text
agents/
├── manifests/*.yaml  the agent "packages" (AgentManifest): planner, finance, engineering, research, action
└── kairos_agents/
    ├── factory.py    build_agent_registry / build_agent_runtime
    ├── sdk/          KairosAgent base class + helpers (ask_json, gather_evidence, cite, propose_action)
    ├── runtime/      AgentRuntime: loads entrypoints, picks adapter, runs agents
    ├── registry/     AgentRegistry over manifests/
    ├── ipc/          A2A helpers (ask/reply/share_evidence)
    ├── prompts/      system prompts + JSON schemas for structured outputs
    ├── library/      planner.py, finance.py, engineering.py, research.py, action.py
    └── adapters/     ── P2 ── NOOA adapter (stretch)

models/
├── models.yaml       routing config: task_class → model, embedding model, latency model, remote on/off
└── kairos_models/
    ├── factory.py    build_model_router
    ├── providers/    OllamaProvider, OpenAICompatProvider (llama.cpp / vLLM), optional remote
    ├── router/       PolicyRouter
    └── gpu/          ── P4 ── ResourceProbe (psutil + nvidia-smi) + factory.build_resource_probe
```

## 6. P4: `infra/`, `data/`, `scripts/`, plus the modules marked P4 above

```text
infra/
├── compose/docker-compose.yml   postgres (pgvector), redis, ollama (GPU), mock-jira, kairosd (appliance profile)
├── compose/*.Dockerfile         kairosd + mock-jira images
├── systemd/kairosd.service      boot-time service on the appliance
├── appliance/README.md          Ubuntu autoinstall, /sovereign-data partition, network
└── gpu/README.md                NVIDIA driver + container toolkit + model pulls
data/okf/                        the DEMO organization bundle (grows from shared/fixtures/okf)
docs/DEMO_SCRIPT.md              live demo run-sheet + fallback plan
```

## 7. `docs/`

| File | For |
|---|---|
| `team/P1-kernel-execution.md` | P1's full brief (inputs/outputs, specs, ordered tasks, DoD). Load it into your coding agent |
| `team/P2-knowledge-console.md` | P2's full brief |
| `team/P3-agents-models.md` | P3's full brief (includes code skeletons for chat-based assistants) |
| `team/P4-platform-data-demo.md` | P4's full brief (includes code skeletons and ops runbooks) |
| `FOLDER_STRUCTURE.md` | this guide |
| `DEMO_SCRIPT.md` | the live demo run-sheet (P4) |

## 8. Where does X go? (quick lookup)

| I need to… | Put it in |
|---|---|
| add a field or model used by two splits | `shared/python/kairos_contracts/schema/` (contract PR) |
| add a method another split calls | `shared/python/kairos_contracts/interfaces/` + fake + contract suite (contract PR) |
| add an event type | `schema/events.py` `EventType` + `shared/catalogs/events.yaml` |
| add a tool capability | `shared/catalogs/capabilities.yaml` + ToolSpec in `execution/.../tools` (P1) + a policy rule in `policies/` |
| add an HTTP endpoint | `mock_gateway.py` first (contract), then `kernel/.../gateway` (P1), then `kairos-client.ts` (P2) |
| add an agent | `agents/manifests/<name>.yaml` + `agents/kairos_agents/library/<name>.py` (P3) + a policy if it writes |
| add knowledge for the demo | `data/okf/` (P4). Never `shared/fixtures/okf/` |
| add a document type to ingestion | `knowledge/kairos_knowledge/ingestion/converters/` + a sample in `knowledge/tests/samples/` (P4) |
| change a setting | `Settings` in `shared/.../wiring.py` (contract) + `.env.example` |
| wire a new implementation | its package `factory.py` + one row in `kairosd/kairosd/wiring.py` `REGISTRY` |
