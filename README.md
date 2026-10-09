<p align="center">
  <img src="docs/readme/hero.svg" alt="KAIROS: the operating system for organizational AI" width="100%">
</p>

<p align="center">
  <a href="https://github.com/mishhkaaa/KAIROS/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/mishhkaaa/KAIROS/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <img alt="Tests: 442 Python, 93 web" src="https://img.shields.io/badge/tests-442_Python_·_93_web-2FB344?style=flat-square&labelColor=151A21">
  <img alt="Coverage 85%" src="https://img.shields.io/badge/coverage-85%25_Python-2FB344?style=flat-square&labelColor=151A21">
  <img alt="Code quality: ruff, eslint and tsc clean" src="https://img.shields.io/badge/code_quality-ruff_·_eslint_·_tsc_clean-2BB8A3?style=flat-square&labelColor=151A21">
  <img alt="Demo gates: 4 scenarios at 8/8" src="https://img.shields.io/badge/demo_gates-4_scenarios_·_8%2F8-2FB344?style=flat-square&labelColor=151A21">
  <img alt="Accessibility: WCAG AA" src="https://img.shields.io/badge/a11y-WCAG_AA-4C86D9?style=flat-square&labelColor=151A21">
  <img alt="Contract 0.13.0" src="https://img.shields.io/badge/contract-0.13.0-9D8CE8?style=flat-square&labelColor=151A21">
  <img alt="Status: Beta" src="https://img.shields.io/badge/status-beta-D99A25?style=flat-square&labelColor=151A21">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-F1F5F9?style=flat-square&labelColor=151A21"></a>
</p>

<p align="center">
  <a href="https://kairos-site-brown.vercel.app"><img alt="Visit the project site" src="https://img.shields.io/badge/Visit-the_project_site-E2B04A?style=for-the-badge&labelColor=0D1117"></a>
  &nbsp;
  <a href="PROJECT.md"><img alt="Read the full project explanation" src="https://img.shields.io/badge/Read-the_project_explanation-2BB8A3?style=for-the-badge&labelColor=0D1117"></a>
  &nbsp;
  <a href="docs/DEMO_SCRIPT.md"><img alt="Demo run sheet" src="https://img.shields.io/badge/Read-the_demo_script-4C86D9?style=for-the-badge&labelColor=0D1117"></a>
</p>

> **KAIROS is not another chatbot. It is the runtime that organizational AI lives in.**
> Company knowledge is mounted as a filesystem. Agents are processes with PIDs, quotas and capabilities, created for
> the job in hand. Every action that touches the outside world is a syscall that policy can stop, a person can
> approve, a sandbox can contain and a hash-chained journal records. People sign in with roles and use it from a
> desktop in the browser, from their phone, or from a Linux shell. All of it runs on one machine, on local models.

<p align="center">
  <img src="docs/readme/numbers.svg" alt="Measured on the demo laptop: all four scored scenarios pass 8 of 8, 8 agent roles made per task, a person approves every write, memories go stale 0.1 s after a source edit, 16 of 16 components real, 535 tests passing" width="100%">
</p>

## Contents

1. [Context and overview](#1-context-and-overview): [pitch](#11-elevator-pitch-and-value-proposition) · [badges](#12-badges-and-status-indicators) · [how it works for a user](#13-how-it-works-for-a-user) · [what we are adding next](#14-what-we-are-adding-next)
2. [Architecture and system design](#2-architecture-and-system-design): [diagrams](#21-architecture-diagrams) · [execution flow](#22-end-to-end-execution-flow) · [documentation](#23-documentation-links)
3. [Installation and configuration](#3-installation-and-configuration): [prerequisites](#31-prerequisites-and-tech-stack) · [install](#32-step-by-step-installation) · [environment](#33-environment-variables-matrix)
4. [Developer experience and quality control](#4-developer-experience-and-quality-control): [usage](#41-usage-snippets) · [testing](#42-testing-and-qa-commands)
5. [Reliability, performance and security](#5-reliability-performance-and-security): [benchmarks](#51-benchmarks-and-maturity-status) · [troubleshooting](#52-troubleshooting-and-known-limitations) · [security](#53-security-reporting)
6. [Governance and license](#6-governance-and-license)

---

## 1. Context and overview

### 1.1 Elevator pitch and value proposition

**The problem.** Organizations want AI that can **act** on their private knowledge: update the tracker, file the report, chase the vendor. Today that means choosing between three bad options.

<table>
<tr>
<td width="33%" valign="top">

**It leaves the building.**<br>
Cloud agents need your finance sheets, tickets and email in someone else's data centre. For many teams that is a non-starter.

</td>
<td width="33%" valign="top">

**It acts without asking.**<br>
An agent that can call tools can also call the wrong one. "The model decided to" is not an audit trail, and one poisoned email can steer it

</td>
<td width="33%" valign="top">

**It forgets where facts came from.**<br>
Answers arrive without sources, memories never expire, and when a document changes nobody knows which conclusions are now wrong.

</td>
</tr>
</table>

**The answer.** KAIROS solves all three the way operating systems solved them for programs: **isolation, permissions, a kernel that mediates every privileged operation, and a journal**. Then it gives the people using it what an operating system gives its users: accounts, a desktop, a shell, and a way in from their phone.

**Who it is for.** Teams that want AI agents working on private data without sending it out: operations and finance leads who need answers with sources, approvers who must sign off before anything changes, engineers and IT who need to see and govern what agents do, and organizations that must keep data on hardware they own.

<p align="center">
  <img src="docs/readme/os-analogy.svg" alt="Classic OS concepts mapped to KAIROS: process to AI agent, filesystem to /org knowledge, system call to governed action, and more" width="100%">
</p>

<p align="center">
  <img src="docs/readme/os-analogy-people.svg" alt="More OS concepts: users and groups to orgs and roles, login to Google sign-in, fork and exec to agents made per task, mount to folders of this computer, keychain to an encrypted vault, drivers to GitHub, Calendar, SQL and MCP, tracing to thought-process events, shell to kairos-os, desktop to windows and Spotlight, system settings to the Settings centre" width="100%">
</p>

**Core features**

| | Feature | What makes it different |
|---|---|---|
| Kernel | **Agents are processes** | PIDs, parents, quotas, capabilities, pause, kill, checkpoints; a task resumes after the daemon dies |
| Governance | **Every action is a syscall** | policy, approval by a person, sandbox, verify, commit or roll back; a hash-chained audit journal (`chain_verified`) |
| Agents | **Agents made for the job** | each task's agents are generated from role templates and bounded by the role, the request, the person's permissions and org policy |
| Transparency | **A visible thought process** | `task.understood`, `agent.planned`, `agent.thought`; tool results reported by the kernel, not the agent |
| Knowledge | **A filesystem with provenance** | `/org` documents with owner, privacy, trust and source; hybrid lexical, vector and graph search |
| Safety | **A context firewall** | retrieved text is data, never instructions; regex always on, a local LLM classifier optional |
| Memory | **Memory that notices** | memories record their sources; edit a source and dependants go stale in 0.1 s and are re-derived in about 3.5 s |
| People | **Orgs, roles, sign-in** | Google sign-in, five roles enforced on every route, one-time codes for the phone |
| Tools | **Connected apps, governed** | Jira, SQL, a sandboxed browser, GitHub, Calendar and MCP servers; writes wait for a person; tokens in an encrypted vault |
| Data | **Your own files** | uploads, and folders of this computer mounted and watched |
| Surfaces | **Desktop, phone, shell** | a desktop OS in the browser, an Android app, and KAIROS OS: a Linux where `/org` is a real filesystem |
| Privacy | **Local by default** | models run on the machine's GPU through Ollama; restricted data never reaches a remote model |

### 1.2 Badges and status indicators

| Badge | Source |
|---|---|
| CI | [GitHub Actions](https://github.com/mishhkaaa/KAIROS/actions/workflows/ci.yml): ruff, the full Python suite against Postgres with pgvector and real Docker sandboxes, and a check that generated contract files are current |
| Tests | `uv run pytest -q` (442) and `npm --prefix apps/web test` (93) |
| Coverage | `pytest --cov` over the six Python packages: 85% of 10,785 statements (section [4.2](#42-testing-and-qa-commands)) |
| Code quality | `uvx ruff check .`, `eslint`, and `tsc --noEmit` for the web and phone apps, all clean |
| Demo gates | four scenarios scored on real models before every merge (section [5.1](#51-benchmarks-and-maturity-status)) |
| Accessibility | WCAG AA contrast checked in tests for both desktop themes and the phone palette |
| Status | Beta: see section [5.1](#51-benchmarks-and-maturity-status) |

### 1.3 How it works for a user

**Three ways in.** The same kernel, permissions and audit journal, whichever door you use.

<table>
<tr>
<td width="50%" valign="top"><b>The desktop</b> (<code>apps/web</code>): windows, a menu bar, a command rail, Alt Space for a floating Ask bar, and a wallpaper that <i>is</i> your knowledge. Every coloured tile is one document in <code>/org</code>, and it lights up when an agent reads it.<br><br><b>The phone</b> (<code>apps/mobile</code>): sign in with a one-time code or Google, watch a run live with agents as faces, get a notification when an action needs you, and approve it from a card that shows the policy, the exact payload and the evidence. A real Android APK.</td>
<td width="50%" valign="top"><img src="docs/readme/kairos-os.svg" alt="A terminal in kairos-os: /org listed, a document with frontmatter, search as a directory, a file copied in and found, kairos ask waiting for an approval"><br><b>KAIROS OS</b> (<code>scripts/wsl</code>): a Linux distro where <code>/org</code> is a real filesystem served live by the kernel. <code>cat</code> a document, <code>ls</code> a search, <code>cp</code> a file in, <code>kairos ask</code> to watch a run from the shell.</td>
</tr>
</table>

**A run, end to end.** *"Investigate why Project Apollo is over budget and six weeks behind schedule. Identify root causes, update the tracker, and prepare a recovery plan."* A replay of this run plays on the [project site](https://kairos-site-brown.vercel.app/#run).

<table>
<tr>
<td width="33%" valign="top"><b>1. The task docks left and tells its story.</b> What the planner understood, which agents it created and why, what each one thinks, every model call, retrieval and tool call, in order.</td>
<td width="33%" valign="top"><b>2. The run stage shows what is happening.</b> Agents are faces that work, wait and doze. Every document read appears under "Referred to"; the vendor email hiding a prompt injection is red and untrusted, read as data only.</td>
<td width="33%" valign="top"><b>3. A person decides, then the kernel commits.</b> Writing to Jira is a privileged syscall, so policy pauses it. Approve from the desktop, the phone or the shell; the write is executed, verified, committed and journaled.</td>
</tr>
</table>

The answer: Apollo is **31% (6.2 lakh) over budget**, with three root causes each cited to its documents, a recovery plan, the research agent's screenshot of the vendor's status page taken in a sandbox with no internet, and `chain_verified: true`.

| Ask it | What happens |
|---|---|
| *"Which vendors did we overpay?"* | Nobody scripted this. The planner creates a data engineer that writes SQL the kernel checks before it runs, and a writer that files the note after approval. CloudCo overpaid by 1.44 lakh, PayCo by 0.42, TalentX by 0.11. |
| *"What do we know about Priya?"* | A plain question: no specialists, no writes. The planner reads the documents that hold the rarest words of the question and answers with its sources. |
| *"What is the latest Python release? Search the web."* | The web researcher searches and reads public pages through governed `browser.open` syscalls, in a sandbox whose only route out is the public internet. |
| *"Why is Apollo over budget?"* | A focused investigation: only the finance specialist runs, and nothing is written. |

The desktop also has **Settings** (one read-only picture of the running system: model routing, agents, tools and their risk, what needs a human, the stack with live health), **Organization** (people, invitations and the role matrix, enforced on every gateway route), **Connections** (GitHub and Google Calendar as governed tools; reads allowed, writes wait for an approver; tokens encrypted and never shown to an agent) and **Add knowledge** (drag files in with live progress, or mount a folder of this computer that is watched and re-ingested as you save).

### 1.4 What we are adding next

| | What it does |
|---|---|
| **JEPA agent router** | After the planner reads a goal, a small joint-embedding predictive model trained on past runs predicts the ideal team in embedding space and gives every agent a spawn probability in one pass. Agents above the threshold start at once; when no agent is confident, the LLM planner decides and the run becomes training data. |
| **n8n workflows on a schedule** | When the same plan shape keeps repeating, it is frozen into an n8n workflow and run by a cron trigger, with no re-planning or re-spawning. Every workflow step still calls the gateway, so policy, approval and audit apply. |
| **Gemma 4 alongside Qwen 2.5** | Ollama serves both; the model router sends harder reasoning, screenshots and long documents to Gemma 4. |

<p align="center">
  <img src="docs/readme/architecture-next.svg" alt="KAIROS architecture with the JEPA agent router, n8n workflows on a cron trigger and Gemma 4 marked in gold" width="100%">
</p>

---

## 2. Architecture and system design

### 2.1 Architecture diagrams

<p align="center">
  <img src="docs/readme/architecture.svg" alt="Clients talk to one gateway; the kernel governs processes, policy, approvals, transactions and audit; services cover knowledge, firewall, memory, agents and execution; everything runs on one machine" width="100%">
</p>

**Service boundaries and infrastructure** (every arrow is a typed call through the shared contract):

```mermaid
flowchart TB
    classDef client fill:#142A45,stroke:#4C86D9,color:#E8ECF0
    classDef gate fill:#3A2A0E,stroke:#D99A25,color:#FBEBCB
    classDef core fill:#103A35,stroke:#2BB8A3,color:#E8ECF0
    classDef svc fill:#2A2342,stroke:#9D8CE8,color:#ECE8FB
    classDef ext fill:#1B222B,stroke:#8A949F,color:#E8ECF0

    D["Desktop<br/>Next.js 16"]:::client & M["Phone<br/>Expo APK"]:::client & O["kairos-os<br/>FUSE /org + kairos"]:::client & C["ai-* CLI"]:::client --> G
    G["Gateway (FastAPI)<br/>REST + WebSocket, :8089"]:::gate --> ID["Identity<br/>orgs, roles, sessions,<br/>Google, sign-in codes"]:::gate
    G --> K["Kernel<br/>processes, scheduler, quotas,<br/>policy, approvals, transactions, audit"]:::core
    K --> KN["Knowledge<br/>/org filesystem, hybrid search,<br/>firewall, memory, mounts, uploads"]:::svc
    K --> AG["Agents<br/>planner, role templates,<br/>dynamic agents, narration"]:::svc
    K --> EX["Execution<br/>Jira, files, SQL, browser,<br/>GitHub, Calendar, MCP, sandboxes"]:::svc
    K --> MO["Models<br/>router, Ollama, local GPU"]:::svc
    EX --> V["Vault<br/>encrypted connector tokens"]:::ext
    EX --> DK[("Docker sandboxes<br/>no network by default")]:::ext
    KN --> PG[("Postgres + pgvector")]:::ext
    K --> RD[("Redis event mirror")]:::ext
    MO --> OL[("Ollama<br/>qwen2.5 7B, nomic-embed")]:::ext
```

| Package | Responsibility | Talks to |
|---|---|---|
| [`kernel/`](kernel) · [`kairosd/`](kairosd) | process table, scheduler, quotas, policy engine, approvals, transactions, audit chain, dynamic agents, identity and vault, the gateway, the `ai-*` CLI | every service, through `kairos_contracts` interfaces |
| [`knowledge/`](knowledge) | the `/org` filesystem, converters, indexing, hybrid retrieval, the context firewall, memory and coherence | Postgres + pgvector, Ollama embeddings |
| [`agents/`](agents) · [`models/`](models) | role templates and the agent library, narration, the model router, the NOOA adapter | the kernel only, through `ctx` |
| [`execution/`](execution) | tool backends (Jira, files, SQL, browser, GitHub, Calendar, MCP), Docker sandboxes, artifacts | Docker, external services, the vault |
| [`apps/web/`](apps/web) · [`apps/mobile/`](apps/mobile) · [`scripts/wsl/`](scripts/wsl) | the three clients | the gateway only |
| [`shared/`](shared) | the contract: Pydantic schemas, interfaces, fakes, event and error catalogs, OpenAPI, generated TypeScript, a mock gateway | imported by everything |

Each component ships a **fake** and a **real** implementation, switchable per component (`KAIROS_MODE_<COMPONENT>=fake|real`). That is how four people built it in parallel, and how the desktop and the phone run without a GPU against the contract's mock gateway.

**Agents made for the job**: how one generated agent's rights are computed.

```mermaid
flowchart LR
    classDef role fill:#142A45,stroke:#4C86D9,color:#E8ECF0
    classDef bound fill:#2A2342,stroke:#9D8CE8,color:#ECE8FB
    classDef agent fill:#103A35,stroke:#2BB8A3,color:#E8ECF0
    classDef gate fill:#3A2A0E,stroke:#D99A25,color:#FBEBCB

    T["Role template<br/>analyst, data-engineer, writer,<br/>finance, engineering, research, action"]:::role --> I{"intersection"}:::bound
    Q["What the planner asked for<br/>(scope, capabilities, why)"]:::bound --> I
    U["What the person may do<br/>(their role in the org)"]:::bound --> I
    P["Org policy"]:::bound --> I
    I --> A["finance-agent@T-…<br/>a process with exactly these rights"]:::agent
    A -->|"every write"| G["needs a person"]:::gate
    I -.->|"anything removed"| L["audit entry saying why"]:::gate
```

### 2.2 End-to-end execution flow

**From a goal to a committed, audited action** (the Apollo run):

```mermaid
sequenceDiagram
    autonumber
    actor U as alice (desktop or phone)
    participant K as Kernel
    participant P as planner
    participant F as finance-agent@T
    participant E as engineering-agent@T
    participant R as research-agent@T
    participant S as browser sandbox
    participant A as action-agent@T
    U->>K: submit goal (Alt Space)
    K->>P: spawn root process
    P-->>U: task.understood, agent.planned (the story)
    P->>K: hybrid search over /org
    K-->>P: evidence (vendor email flagged UNTRUSTED)
    rect rgba(43,184,163,0.12)
    par agents generated for this task
        P->>F: create from template, bounded by alice's role
        P->>E: create
        P->>R: create
    end
    F-->>P: overrun 6.2 lakh (31%), cited drivers
    E-->>P: backfill failure on APOLLO-12, vendor block
    R->>S: browser.open vendor-docs (allowlisted, no internet)
    S-->>R: screenshot: SDK v5 GA slipped
    R-->>P: findings with sources
    end
    P->>A: create with the findings
    A->>K: syscall jira.write APOLLO-12
    rect rgba(217,154,37,0.14)
    K->>U: policy: approval required (payload and evidence attached)
    U->>K: approve (phone notification)
    end
    rect rgba(47,179,68,0.12)
    K->>K: execute, verify, commit, append audit
    end
    A-->>P: committed
    P->>K: 3 cited root causes + recovery-plan.md
    K-->>U: result, memories consolidated, generated agents cleaned up
```

**Every privileged action takes the same path:**

<p align="center">
  <img src="docs/readme/syscall-pipeline.svg" alt="Intent, policy, approval, execute, verify, commit; denials are refused and failed checks roll back" width="100%">
</p>

Policies are plain YAML in [`policies/`](policies) and hot-reload while the system runs: allow, deny or require approval per capability, per agent and per data scope. Writes to Jira, GitHub, Calendar and the database wait for a person by default; SQL is checked by the kernel before it runs (one statement, no DDL, a row limit).

**Knowledge in, memory out** (the data flow, including how memory notices a change):

```mermaid
flowchart LR
    classDef doc fill:#142A45,stroke:#4C86D9,color:#E8ECF0
    classDef guard fill:#3D1618,stroke:#E05252,color:#F8D7D7
    classDef mem fill:#1F3A1A,stroke:#2FB344,color:#DDF5E1
    classDef agent fill:#2A2342,stroke:#9D8CE8,color:#ECE8FB
    classDef evt fill:#3A2A0E,stroke:#D99A25,color:#FBEBCB

    S1["Uploads"]:::doc --> D
    S2["Folders of this computer<br/>/org/mnt, watched"]:::doc --> D
    S3["GitHub, Calendar sync"]:::doc --> D
    D["/org Markdown<br/>+ frontmatter"]:::doc --> I[("Index<br/>lexical + pgvector + graph")]:::doc
    I --> Q{"hybrid<br/>search"}:::doc
    Q -->|policy scope,<br/>privacy| FW["Context<br/>firewall"]:::guard
    FW -->|clean| C["Agent context"]:::agent
    FW -->|instruction-like| U["UNTRUSTED<br/>quoted as data"]:::guard
    U --> C
    C --> F["Finding + citations"]:::agent
    F --> M[("Memory<br/>derived_from = sources")]:::mem
    X["A source document<br/>is edited"]:::evt --> W["Watcher reindexes"]:::evt
    W --> V["memory.invalidated"]:::evt
    V --> M
    M -->|stale| R["memory.reconsolidate"]:::evt
    R -->|~3.5 s| NM["Re-derived memory<br/>replaces old record"]:::mem
```

**An agent's life as a process:**

```mermaid
stateDiagram-v2
    direction LR
    [*] --> CREATED
    CREATED --> INITIALIZING
    INITIALIZING --> READY
    INITIALIZING --> FAILED
    READY --> RUNNING
    RUNNING --> WAITING: approval or child
    WAITING --> RUNNING
    RUNNING --> PAUSED: pause
    PAUSED --> RUNNING
    RUNNING --> CHECKPOINTING
    CHECKPOINTING --> RUNNING
    RUNNING --> FAILED
    FAILED --> RETRYING
    RETRYING --> RUNNING
    RUNNING --> COMPLETED
    COMPLETED --> [*]
```

Every non-final state can also move to `TERMINATED` (a kill; a task is cancelled before its children). The legal transitions live in the contract, so the kernel, the CLI and the desktop's buttons agree.

### 2.3 Documentation links

| Document | What it covers |
|---|---|
| **API specification** · [`shared/api/openapi.json`](shared/api/openapi.json) | the full REST API (OpenAPI 3); a running gateway also serves **Swagger UI at `http://localhost:8089/docs`** and the live spec at `/openapi.json` |
| [`shared/schemas/`](shared/schemas) · [`shared/ts/src/kairos.d.ts`](shared/ts/src/kairos.d.ts) | JSON Schema for every contract model; the generated TypeScript types |
| [`shared/catalogs/events.yaml`](shared/catalogs/events.yaml) · [`errors.yaml`](shared/catalogs/errors.yaml) · [`capabilities.yaml`](shared/catalogs/capabilities.yaml) | every event on `WS /ws/events`, every error code, every capability and its default approval |
| [`PROJECT.md`](PROJECT.md) | the complete project explanation: concept, every feature, architecture, security, results, limits |
| [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) · [`docs/PHONE_DEMO.md`](docs/PHONE_DEMO.md) | the live demo run sheet and fallbacks; demonstrating the phone app |
| [`docs/KAIROS_OS.md`](docs/KAIROS_OS.md) · [`apps/mobile/README.md`](apps/mobile/README.md) | KAIROS OS; the phone app and its APK |
| [`docs/FOLDER_STRUCTURE.md`](docs/FOLDER_STRUCTURE.md) · [`shared/services/`](shared/services) | where everything lives; what each split provides and how it is tested |
| [`AGENTS.md`](AGENTS.md) · [`shared/README.md`](shared/README.md) | rules for contributors and coding agents; how to change the contract |

---

## 3. Installation and configuration

### 3.1 Prerequisites and tech stack

| Requirement | Version | Notes |
|---|---|---|
| Python | **>= 3.12** | managed by [uv](https://docs.astral.sh/uv/) (>= 0.4) |
| Node.js | **>= 20** (tested on 24) | the desktop (Next.js 16) and the phone app (Expo SDK 57) |
| Docker | **>= 24** (tested on Docker Desktop 28) | Postgres + pgvector, Redis, the vendor site, and the agent sandboxes |
| Ollama | **>= 0.5** (tested on 0.34) | `qwen2.5:7b-instruct` and `nomic-embed-text` |
| GPU | **NVIDIA, >= 8 GB VRAM** | tested on an RTX 5070 Laptop (8 GB); the 7B model must fit entirely on the GPU. No GPU: use the mock gateway or fake mode |
| RAM / disk | **16 GB** (32 GB recommended) / about 25 GB free | models, images and the Android SDK |
| OS | Windows 11 (the demo machine) or Linux | `scripts/win/*.ps1` for Windows; a Linux appliance installer in `infra/appliance` |
| Optional: phone | Android Studio (SDK 36, JDK 21) | to build the APK; any Android 10+ phone or the emulator |
| Optional: KAIROS OS | WSL 2 | `scripts/wsl/install-kairos-os.ps1` creates its own distro |

**Stack:** FastAPI and Pydantic v2 (gateway, kernel, contract) · Postgres 16 with pgvector · Redis 7 · Ollama · Docker (sandboxes, Playwright browser, MCP) · Next.js 16, Tailwind 4, TanStack Query · Expo SDK 57, React Native 0.86 · Ubuntu 24.04 on WSL with FUSE · Google Identity, Fernet (vault).

### 3.2 Step-by-step installation

```bash
# 1. clone and install
git clone https://github.com/mishhkaaa/KAIROS && cd KAIROS
uv sync --all-packages --all-extras
npm --prefix apps/web ci
cp .env.example .env                                   # tests read it; keep KAIROS_DEFAULT_MODE=fake there

# 2. services: Postgres + pgvector, Redis, and the internal vendor site the browser agent visits
docker compose -f infra/compose/docker-compose.yml up -d postgres redis vendor-docs
docker build -t kairos/sandbox-base:latest    execution/images/sandbox-base
docker build -t kairos/sandbox-browser:latest execution/images/sandbox-browser

# 3. local models
ollama pull qwen2.5:7b-instruct && ollama pull nomic-embed-text

# 4. the kernel and gateway, on real components
export KAIROS_DEFAULT_MODE=real KAIROS_OKF_DIR=./data/okf KAIROS_KNOWLEDGE_WATCH=true \
       KAIROS_MODELS_CONFIG=./models/models.7b-only.yaml KAIROS_GATEWAY_PORT=8089
uv run kairosd                                         # leave running; Swagger at http://localhost:8089/docs

# 5. in a second terminal: index the knowledge, seed the demo database
curl -X POST http://localhost:8089/knowledge/reindex
uv run python scripts/seed_demo_data.py

# 6. the desktop
cd apps/web && echo "NEXT_PUBLIC_KAIROS_URL=http://localhost:8089" > .env.local
npm run build && npx next start -p 3000                # open http://localhost:3000

# 7. verify
uv run python scripts/preflight.py --gateway http://127.0.0.1:8089                 # must print "all green"
uv run python scripts/demo_run.py run --auto-approve --check-story --gateway http://127.0.0.1:8089   # 8/8
```

**On the Windows demo laptop** the same steps are scripted: `scripts\win\kairos-boot.ps1` starts everything and opens the boot screen; `scripts\win\reset-demo.ps1` resets between rehearsals. On an 8 GB GPU use `models/models.7b-only.yaml`; run the stack's Postgres on 5434 if a native one holds 5432.

<details>
<summary><b>No GPU: every screen against the contract's mock gateway</b></summary>

```bash
uv run kairos-mock-gateway --speed 2                   # replays a full Apollo run on :8080, pauses at the approval
cd apps/web && NEXT_PUBLIC_KAIROS_URL=http://localhost:8080 npm run dev
```

Or the real kernel, gateway, policy, approvals and audit with fake models and knowledge: `KAIROS_DEFAULT_MODE=fake uv run kairosd`.
</details>

<details>
<summary><b>The phone and KAIROS OS</b></summary>

```powershell
powershell -File apps\mobile\scripts\build-apk.ps1      # apps/mobile/dist/kairos-<version>.apk
adb install -r apps\mobile\dist\kairos-1.1.0.apk
adb reverse tcp:8089 tcp:8089                           # a phone on USB reaches the laptop as localhost
powershell -File scripts\wsl\install-kairos-os.ps1      # then: wsl -d kairos-os
```

On a hotspot or Wi-Fi, `scripts\win\phone-access.ps1` (as administrator) opens the firewall and prints the address.
</details>

### 3.3 Environment variables matrix

Every setting is read by `kairos_contracts.wiring.Settings` with the prefix `KAIROS_` (see [`.env.example`](.env.example)). None is strictly required: the defaults run the test suite in fake mode. The **Demo** column marks what the real demo stack needs.

| Key | Description | Type | Default | Demo |
|---|---|---|---|:-:|
| `KAIROS_DEFAULT_MODE` | real or fake implementation for every component | `fake \| real` | `fake` | **yes** (`real`) |
| `KAIROS_MODE_<COMPONENT>` | override per component (`EVENTS`, `POLICY`, `AUDIT`, `KNOWLEDGE`, `MEMORY`, `FIREWALL`, `MODELS`, `AGENTS`, `TOOLS`, `SANDBOX`, `BROWSER`, `CONVERTERS`, `PROBE`, …) | `fake \| real` | the default mode | |
| `KAIROS_ENV` | environment name, shown in Settings | string | `dev` | |
| `KAIROS_DATA_DIR` | runtime data: SQLite identity, workspaces, uploads, artifacts | path | `./.data` | |
| `KAIROS_OKF_DIR` | the `/org` knowledge bundle | path | `./shared/fixtures/okf` | **yes** (`./data/okf`) |
| `KAIROS_POLICIES_DIR` · `KAIROS_MANIFESTS_DIR` | policies and agent manifests | path | `./policies` · `./agents/manifests` | |
| `KAIROS_DATABASE_URL` | Postgres with pgvector (knowledge, memory, audit) | URL | `postgresql+psycopg://kairos:kairos@localhost:5432/kairos` | **yes** |
| `KAIROS_REDIS_URL` | the event mirror | URL | `redis://127.0.0.1:6379/0` | |
| `KAIROS_DEMO_DATA_URL` | the demo company's database behind the SQL tool | URL | `postgresql+psycopg://kairos:kairos@localhost:5432/kairos_demo_data` | for vendors, multitool |
| `KAIROS_OLLAMA_URL` | the model runtime | URL | `http://localhost:11434` | **yes** |
| `KAIROS_DEFAULT_CHAT_MODEL` · `KAIROS_DEFAULT_EMBED_MODEL` | fallback models | string | `qwen2.5:7b-instruct` · `nomic-embed-text` | |
| `KAIROS_MODELS_CONFIG` | model routing per kind of task | path | `./models/models.yaml` | 8 GB GPU: `models.7b-only.yaml` |
| `KAIROS_GATEWAY_HOST` · `KAIROS_GATEWAY_PORT` | where the gateway listens | string · int | `0.0.0.0` · `8080` | demo uses `8089` |
| `KAIROS_KNOWLEDGE_WATCH` | republish edits under the bundle (memory invalidation) | bool | `false` | **yes** (`true`) |
| `KAIROS_FIREWALL_LLM` | add the local LLM classifier to the regex firewall | bool | `false` | |
| `KAIROS_JIRA_URL` | Jira, or `inprocess` for the built-in mock | URL | `http://localhost:8090` | `inprocess` |
| `KAIROS_MCP_CONFIG` | MCP servers exposed as tools (a `browser: true` server replaces the Playwright driver) | path | none | |
| `KAIROS_SANDBOX_ENDPOINT` · `KAIROS_SANDBOX_NETWORK` · `KAIROS_BROWSER_IMAGE` | how sandboxes are reached, their network and the browser image | string | `ip` · `kairos_sandbox` · `kairos/sandbox-browser:latest` | `port` on Docker Desktop |
| `KAIROS_AUTH` | `dev`: email sign-in and trusted headers; `google`: Google ID tokens and sessions | `dev \| google` | `dev` | production: `google` |
| `KAIROS_GOOGLE_CLIENT_ID` | the OAuth **web** client ID (public, not a secret) | string | none | with `google` |
| `KAIROS_VAULT_KEY` | 32 random bytes (base64) encrypting connector tokens; unset is a dev vault | secret | none | recommended |
| `KAIROS_SESSION_HOURS` | how long a sign-in lasts | int | `12` | |
| `KAIROS_KERNEL_MAX_CONCURRENT_TASKS` | tasks run at once | int | `2` | |
| `KAIROS_KERNEL_APPROVAL_TIMEOUT_S` | how long an approval may wait | int | `1800` | |
| `KAIROS_KERNEL_MAX_RESTARTS` · `KAIROS_KERNEL_RETRY_BACKOFF_S` | resume after restarts; backoff after a model error | int | `2` · `5` | |
| `KAIROS_KERNEL_PREEMPTION` · `KAIROS_KERNEL_SCHEDULES_FILE` | priority preemption; scheduled agents (cron) | bool · path | `true` · none | |
| `KAIROS_URL` · `KAIROS_TOKEN` · `KAIROS_USER` · `KAIROS_ORG` | for the `ai-*` CLI and KAIROS OS: the gateway, a session, or dev identity | URL · secret · string | `http://localhost:8080` · none · `alice` · `acme` | |
| `NEXT_PUBLIC_KAIROS_URL` | the gateway the desktop calls (baked in at build time) | URL | `http://localhost:8080` | **yes** |
| `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID` | the phone APK's Google sign-in (build time) | string | none | with `google` |

---

## 4. Developer experience and quality control

### 4.1 Usage snippets

**REST** (dev mode; with `KAIROS_AUTH=google` sign in with Google instead of `/auth/dev`):

```bash
# sign in (dev) and keep the session
TOKEN=$(curl -s -X POST localhost:8089/auth/dev -H 'content-type: application/json' \
        -d '{"email":"priya@acme.example"}' | jq -r .token)

# start a task
curl -s -X POST localhost:8089/tasks -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     -d '{"goal":"Which vendors were paid more than their contract in Q3?","priority":"high"}'

# what is waiting for a person, and approve it
curl -s "localhost:8089/approvals?status=pending" -H "Authorization: Bearer $TOKEN"
curl -s -X POST localhost:8089/approvals/APR-…/approve -H "Authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' -d '{"comment":"checked the evidence"}'

# search /org, and mount a folder of this computer
curl -s "localhost:8089/knowledge/search?q=apollo%20overrun&top_k=5"
curl -s -X POST localhost:8089/knowledge/mounts -H 'content-type: application/json' \
     -d '{"name":"team-notes","host_path":"C:\\Users\\you\\Documents\\team-notes"}'
```

**Live events** (WebSocket): `ws://localhost:8089/ws/events?types=task.*,approval.*,agent.thought&token=<session>`.

**TypeScript** (`@kairos/contracts` types, as the desktop uses them):

```ts
import { createKairosClient } from "@/lib/kairos-client";
const kairos = createKairosClient("http://localhost:8089", "alice", "acme", token);
const task = await kairos.createTask({ goal: "Brief me on Zeus budget risk", priority: "normal" });
const stop = kairos.events((e) => console.log(e.type, e.payload), { taskId: task.task_id });
```

**An agent** acts only through its context, and every action is a governed syscall (see [`agents/kairos_agents/library/`](agents/kairos_agents/library)):

```python
async def run(goal: str, ctx: AgentContext) -> AgentResult:
    evidence = await ctx.search("apollo budget variance", top_k=8)        # policy-filtered, firewall-checked
    await ctx.narrate("analyze", f"Read {len(evidence.hits)} documents")  # appears in the story
    await ctx.syscall("jira.write", resource="APOLLO-12", arguments={...},
                      justification="Record the root causes", evidence=[h.path for h in evidence.hits])
```

**Command line:**

```bash
ai run "Why is Apollo over budget?"     # submit and stream a task
ai-ps ; ai-tree --task T-… ; ai-top     # the process table, a task's tree, live resources
ai approve APR-… ; ai-audit T-…         # decide; print the hash-chained journal
wsl -d kairos-os -- kairos ask "Brief me on Zeus"     # KAIROS OS
```

**Python package** ([`kairos-os`](sdk/python), no dependencies, Python 3.9+): the client library and the `kairos`
command for any machine that can reach a gateway. Full documentation: [`sdk/python/README.md`](sdk/python/README.md).

```bash
pip install kairos-os
kairos connect https://your-gateway.example && kairos login --as priya@acme.example
kairos ask "Why is Project Apollo over budget?"
```

```python
from kairos_os import Kairos
task = Kairos("http://localhost:8089").ask("Brief me on Zeus budget risk", on_entry=lambda e: print(e["summary"]))
```

### 4.2 Testing and QA commands

| What | Command |
|---|---|
| Python unit, contract and integration suites (442) | `uv run pytest -q` |
| A single package | `uv run pytest -q kernel/tests` (also `knowledge/`, `agents/`, `execution/`, `models/`, `shared/python/tests`, `tests/integration`) |
| Coverage (85%) | `uv run --with pytest-cov pytest -q --cov=kernel/kairos_kernel --cov=knowledge/kairos_knowledge --cov=agents/kairos_agents --cov=execution/kairos_execution --cov=models/kairos_models --cov=shared/python/kairos_contracts` |
| Python lint and static analysis | `uvx ruff check .` |
| Contract artifacts are current | `uv run kairos-export-contracts && git diff --exit-code shared/` |
| Desktop: lint, unit tests (93, incl. WCAG contrast), build | `npm --prefix apps/web run lint` · `npm --prefix apps/web test` · `npm --prefix apps/web run build` |
| Phone: types and contrast | `npm --prefix apps/mobile run typecheck` · `npm --prefix apps/mobile run contrast` |
| Readiness of a live stack | `uv run python scripts/preflight.py --gateway http://127.0.0.1:8089` |
| End-to-end scenario gates on real models | `uv run python scripts/demo_run.py run --auto-approve --check-story [--scenario zeus\|vendors\|multitool]` |
| Knowledge bundle validation | `uv run python scripts/check_okf.py` |

CI runs ruff, the full Python suite against Postgres with pgvector and real Docker sandboxes, and the contract freshness check on every push to `main` and every pull request.

---

## 5. Reliability, performance and security

### 5.1 Benchmarks and maturity status

Measured on the demo laptop (RTX 5070 Laptop GPU, 8 GB; `qwen2.5:7b-instruct`, fully on the GPU).

| End-to-end scenario | Score | Wall time |
|---|---|---|
| **Apollo**: planner and specialists, firewall, sandboxed browser, one approved write | 8/8, story PASS | about 100 s |
| **Zeus**: same agents, a different project and a reworded injection | 8/8, story PASS | about 110 s |
| **Vendors**: generated data engineer and writer, checked SQL, approved write | 8/8, story PASS | about 21 s |
| **Multitool**: SQL, browser, knowledge and a write in one task | 8/8, story PASS | about 44 s |
| Zeus with the LLM classifier on | 9/9 | about 104 s |

| Component metric | Result |
|---|---|
| Model throughput | >= 25 tokens/s required by preflight, 7B fully on the GPU |
| Memory invalidation after a source edit | about 0.1 s |
| Memory re-derivation | about 3.5 s |
| Retrieval quality on the QA set | 10/10 answered, MRR 0.90 |
| Firewall LLM classifier | 3 to 4 of 5 reworded injections caught, 0 false positives, about 0.2 s per document |
| Upload or mounted file to searchable | a few seconds per document |
| Components real in the demo stack | 16 of 16 |
| Recovery | a model restart mid-run is retried and still scores 8/8; a killed kernel resumes tasks from their checkpoints |

**Maturity: Beta.** Feature-complete for the scenarios above and verified end to end on real models before every merge, on a single node.

| Area | Status |
|---|---|
| Kernel, governed syscalls, audit, policies, approvals | Beta: verified by the gates and the suites |
| Knowledge, firewall, memory, uploads, mounts | Beta |
| Dynamic agents, SQL tool, connectors | Beta; GitHub and Calendar tested on built-in demo data, not yet with real accounts |
| Desktop, phone, KAIROS OS | Beta; the phone verified on the Android emulator |
| Identity | Beta; Google sign-in verified against Google's token format in tests, not yet with a live client ID |
| Not production-ready yet | one node (no high availability), dev sign-in by default, the debug-signed APK, no push notification server |

### 5.2 Troubleshooting and known limitations

| Symptom | Cause | Fix or workaround |
|---|---|---|
| kairosd cannot reach Postgres, or the wrong one | a native Postgres already on 5432 | run the stack's Postgres on another port (`5434` on the demo laptop) and set `KAIROS_DATABASE_URL` |
| Runs are slow, preflight fails the tok/s check | the model spilled off the GPU, or a leftover runner holds VRAM | `scripts\win\restart-ollama.ps1`; use `models/models.7b-only.yaml` on an 8 GB GPU |
| The desktop shows "gateway unreachable" | a different `NEXT_PUBLIC_KAIROS_URL` was baked in at build time | rebuild (`scripts\win\start-console.ps1 -Build`) |
| `403 PERMISSION_DENIED` | the caller's role does not allow it | expected: see the role matrix in the Organization app; dev mode header callers are owners |
| Vendors or multitool fail on SQL | `kairos_demo_data` missing or not seeded | `uv run python scripts/seed_demo_data.py` (also before each rehearsal) |
| The policy engine fails at boot after adding a YAML file | every `policies/*.yaml` is loaded as a policy | put non-policy tables in a subfolder (`policies/rbac/`) |
| Browser tests skip; no sandbox screenshot | the browser image is not built | `docker build -t kairos/sandbox-browser:latest execution/images/sandbox-browser` |
| The phone cannot connect | `10.0.2.2` only works on the emulator; a phone needs the laptop's address | USB: `adb reverse tcp:8089 tcp:8089` and `http://localhost:8089`; Wi-Fi: `scripts\win\phone-access.ps1` |
| APK build dies quietly or with "insufficient memory" | Gradle killed with its shell, stderr as fatal in PowerShell, or the paging file exhausted | `apps/mobile/scripts/build-apk.ps1` handles the first two; close the emulator or pass `-Workers 2` |
| `apt` hangs while installing KAIROS OS | some networks drop large packets on WSL's NAT path | the installer relays apt through Windows (`scripts/wsl/apt-proxy.py`) |
| `ls /org` is empty in KAIROS OS | the gateway is down, or the first login raced the mount | start kairosd; `sudo systemctl restart kairos-orgfs` |
| A rehearsal's answer cites unexpected documents | uploads, mounts or synced connector data are still in `/org` | remove `data/okf/uploads`, `mnt`, `github`, `calendar`; disconnect connectors; `reset-demo.ps1` |

**Technical trade-offs**
- **A 7B local model** keeps data on the machine and fits an 8 GB laptop GPU, at the cost of shorter reasoning than large hosted models; prompts and agents are written to its strengths, and every run is scored.
- **Regex plus an optional classifier** in the firewall: the regex is fast and never misses a known pattern; the classifier catches rewordings but costs about 0.2 s per document, so it is opt-in.
- **SQL checks without a parser** (none is in the lock file): the kernel refuses any statement it cannot read with confidence, so some valid queries are refused.
- **Mounted folders are read-only mirrors**: agents never write to your disk; changes go through governed paths.
- **Notifications are local**, not push: they arrive while the app is open or recently in the background.

### 5.3 Security reporting

Please report vulnerabilities **privately** through GitHub's private vulnerability reporting: **Security**, then **Report a vulnerability** ([open a private report](https://github.com/mishhkaaa/KAIROS/security/advisories/new)). Never in a public issue. Scope, what to include and response times are in [`SECURITY.md`](SECURITY.md).

The security model in one breath: agents hold no credentials and act only through syscalls; policy decides, a person approves writes, sandboxes have no network unless allowlisted, the audit journal is hash-chained, retrieved text is treated as data, connector tokens are encrypted at rest and never reach an agent or a log, and every gateway route checks the caller's role.

---

## 6. Governance and license

**License.** KAIROS is open source under the [MIT License](LICENSE).

**Contributing.** See [`CONTRIBUTING.md`](CONTRIBUTING.md): branch from `main`, small commits with an area prefix, the full test and lint gates before every push, the scored scenarios kept at 8/8, and contract changes on their own branch with a version bump and regenerated artifacts. [`AGENTS.md`](AGENTS.md) holds the same rules for coding agents.

**Code style.** Python 3.12 with type hints and Pydantic v2, line length 130, `ruff`; packages talk only through `kairos_contracts`; agents act only through `ctx`; errors use the codes in `shared/catalogs/errors.yaml`. Web: design tokens only, container queries, both themes, WCAG AA. Docs: plain English, no emojis. Secrets never enter the repository, events, the audit journal or logs.

**Team.** KAIROS is built by **Mishka Tiwari**, **Kamal Karteek U**, **Mayeraa Singh** and **Manjunath Patil**, four ways through one shared contract. It builds on our team's earlier work on an agent kernel, extended here for this problem statement.

| | Owns |
|---|---|
| **Kamal Karteek U** ([@kamalllx](https://github.com/kamalllx)) | the kernel and governed execution, the desktop OS, KAIROS OS on WSL, the phone app and APK |
| **Mishka Tiwari** ([@mishhkaaa](https://github.com/mishhkaaa)) | agents and the planner, dynamic agents, the thought-process stream, the SQL tool, the JEPA router |
| **Mayeraa Singh** ([@mayeraasingh](https://github.com/mayeraasingh)) | knowledge, ingestion and retrieval, identity, organizations and connectors |
| **Manjunath Patil** ([@manjunath3155](https://github.com/manjunath3155)) | models and routing, n8n workflows, platform and infrastructure, the Python package, demo data |

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-FastAPI_·_Pydantic_v2-3776AB?style=flat-square&labelColor=151A21">
  <img alt="Postgres" src="https://img.shields.io/badge/Postgres-pgvector-4C86D9?style=flat-square&labelColor=151A21">
  <img alt="Redis" src="https://img.shields.io/badge/Redis-event_mirror-E05252?style=flat-square&labelColor=151A21">
  <img alt="Ollama" src="https://img.shields.io/badge/Ollama-qwen2.5_·_nomic--embed-2BB8A3?style=flat-square&labelColor=151A21">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-sandboxes-2496ED?style=flat-square&labelColor=151A21">
  <img alt="Playwright" src="https://img.shields.io/badge/Playwright-browser_·_MCP-2FB344?style=flat-square&labelColor=151A21">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-Tailwind_·_TanStack-F1F5F9?style=flat-square&labelColor=151A21">
  <img alt="Expo" src="https://img.shields.io/badge/Expo-SDK_57_·_React_Native-000020?style=flat-square&labelColor=151A21">
  <img alt="WSL" src="https://img.shields.io/badge/WSL-Ubuntu_24.04_·_FUSE-E95420?style=flat-square&labelColor=151A21">
  <img alt="Google sign-in" src="https://img.shields.io/badge/Auth-Google_·_RBAC_·_Fernet_vault-9D8CE8?style=flat-square&labelColor=151A21">
</p>

<p align="center"><sub>KAIROS: build it, run it, own it. On one box.</sub></p>
