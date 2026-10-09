# KAIROS: the complete project explanation

> **KAIROS is an operating system for organizational AI.** Company knowledge is a filesystem. AI agents are
> processes. Every action an agent takes in the real world is a system call that policy can stop, a person can
> approve, a sandbox can contain and a tamper-evident journal records. People sign in with roles and use it from a
> desktop in the browser, from their phone, or from a Linux shell. All of it runs on one machine, on local models.

This document explains the whole project: the concept, every feature and what is new about it, how it is built, the
technology behind it, how well it works, and its limits. It is written for anyone who needs to explain or evaluate
KAIROS end to end.

| | |
|---|---|
| Repository | https://github.com/mishhkaaa/KAIROS |
| Team | Mishka Tiwari, Kamal Karteek U, Manjunath Patil, Mayeraa Singh |
| Status | Beta: feature-complete for the demo scenarios, verified end to end on real models, single node |
| Headline results | 4 scored scenarios at 8/8 · 535 tests (442 Python, 93 web) · 85% Python coverage · 16 of 16 components real · 100% local on an 8 GB laptop GPU |

---

## Contents

1. [The problem](#1-the-problem)
2. [The concept: why an operating system](#2-the-concept-why-an-operating-system)
3. [The flagship demo, step by step](#3-the-flagship-demo-step-by-step)
4. [Every feature, explained](#4-every-feature-explained)
5. [The three ways in: desktop, phone, shell](#5-the-three-ways-in-desktop-phone-shell)
6. [What is novel](#6-what-is-novel)
7. [Architecture](#7-architecture)
8. [Technology stack](#8-technology-stack)
9. [Security model](#9-security-model)
10. [Results and measurements](#10-results-and-measurements)
11. [Quality: testing and engineering process](#11-quality-testing-and-engineering-process)
12. [Limitations, trade-offs and future work](#12-limitations-trade-offs-and-future-work)
13. [Team](#13-team)
14. [Questions people ask](#14-questions-people-ask)
15. [Glossary](#15-glossary)

---

## 1. The problem

Organizations want AI that does more than answer questions. They want AI that **acts** on their private knowledge:
update the project tracker, file the report, chase the vendor, reconcile the invoices. Today that forces a choice
between three bad options.

| Problem | What goes wrong today |
|---|---|
| **The data leaves the building** | Cloud agents need your finance sheets, tickets, contracts and email inside someone else's data centre. For regulated or cautious teams that rules them out entirely. |
| **The AI acts without asking** | An agent that can call tools can call the wrong one. "The model decided to" is not an audit trail. Worse, any document the agent reads can carry hidden instructions: one poisoned email can steer it (prompt injection). |
| **The AI forgets where facts came from** | Answers arrive without sources. Memories never expire. When a document changes, nobody knows which earlier conclusions are now wrong. |

Agent frameworks today are libraries: they help a developer chain model calls and tools. They do not answer the
questions an organization actually asks before letting AI touch its systems: *Who allowed this? Who approved it? What
exactly did it read? Can it reach the internet? Can I see what it is doing right now? Can I stop it? Can I prove
afterwards what happened?*

---

## 2. The concept: why an operating system

Operating systems solved exactly these problems for programs decades ago. Programs are untrusted, so the OS gives
them **isolation** (processes), **permissions** (users, capabilities), a **kernel that mediates every privileged
operation** (system calls), and a **journal** (logs). KAIROS applies the same design to AI agents, then gives the
people using it what an OS gives its users: accounts, a desktop, a shell, and a way in from their phone.

| Classic OS concept | KAIROS equivalent |
|---|---|
| Program / process | An **AI agent** is a process: a PID, a parent, a state machine, quotas (tokens, tool calls, wall time), capabilities, pause, kill, checkpoint and resume |
| `fork` / `exec` | The planner **creates agents for the job** from role templates, each bounded by the role, the request, the person and policy |
| Filesystem | **Company knowledge** as `/org/...` paths: Markdown documents with frontmatter (owner, type, trust, privacy, links) |
| System call | Every action that changes the world (write Jira, write a file, open a browser, write the database) is a **governed syscall** |
| Kernel mediation | **Policy, then approval by a person, then sandboxed execution, then verify, then commit or roll back** |
| Kernel log | A **hash-chained audit journal** per task; the kernel verifies the chain |
| Memory protection | The **context firewall**: retrieved text is data, never instructions |
| Cache coherence | **Memory with provenance**: memories record their sources and go stale when a source changes, then are re-derived |
| Users and groups | **Organizations, members and roles** (owner, admin, approver, member, viewer) enforced on every route |
| Login | **Google sign-in**, sessions, and one-time codes for the phone |
| Keychain | An **encrypted vault** for connector tokens; agents never see them |
| Device drivers | **Connectors and tools**: Jira, SQL database, browser, GitHub, Google Calendar, MCP servers |
| `mount` | **Folders of this computer** mounted into `/org/mnt/...`, watched, re-ingested on save |
| Sandboxing / containers | **Docker sandboxes** with no network by default, a non-root user, read-only roots |
| Scheduler | Priorities, concurrency limits, preemption, scheduled agents |
| `top`, `ps`, tracing | A **visible thought process**: every step of every agent streamed live as events |
| Shell | **KAIROS OS**: a Linux distro where `/org` is a real FUSE filesystem and `kairos` is a command |
| Desktop | A **desktop OS in the browser**: windows, a menu bar, a dock, Spotlight-style Ask, a wallpaper made of your knowledge |
| System settings | The **Settings centre**: the whole running system in one view |

The analogy is not decoration. Each row is implemented as real code with tests, and it is what makes the guarantees
hold: an agent physically cannot change anything except by asking the kernel, and the kernel always applies policy,
approval and audit.

**Design principles that run through everything**
1. **Local first.** Models run on the machine's own GPU through Ollama. Data marked `restricted` is never sent to a
   remote model.
2. **Agents hold no power of their own.** They act only through a context object (`ctx`); every world-changing action
   is `ctx.syscall()`.
3. **Retrieved text is data, never instructions.**
4. **A person decides on writes.** By default every write to an external system waits for an approver.
5. **Everything is observable and provable.** Every step is an event; every action is journaled in a hash chain.
6. **Every component is swappable.** One shared, typed contract; each component has a fake and a real implementation.

---

## 3. The flagship demo, step by step

**The goal typed by Alice (owner of Acme Corp):**
*"Investigate why Project Apollo is over budget and six weeks behind schedule. Identify root causes, update the
tracker, and prepare a recovery plan."*

| Step | What happens | What it shows |
|---|---|---|
| 1. Submit | Alice presses Alt+Space on the desktop and types the goal (or uses the phone, or `kairos ask` in the shell). | One kernel, three surfaces |
| 2. Understand | The task docks on the left. The planner emits `task.understood`: the intent, the entities (Apollo, budget, schedule) and the capabilities needed. | A transparent thought process |
| 3. Plan and create | The planner emits `agent.planned` for each specialist and why, then the kernel creates `finance-agent@T-…`, `engineering-agent@T-…`, `research-agent@T-…`, later `action-agent@T-…`. Each is a process with a PID, generated from a role template and bounded by Alice's role and policy. | Agents made for the job; agents as processes |
| 4. Retrieve | Agents run hybrid search over `/org`. Every document read appears on the desktop under "Referred to", and its tile on the wallpaper lights up. | Knowledge as a filesystem; observability |
| 5. Catch the attack | One vendor email contains hidden instructions addressed to the AI, disguised as a system note. The context firewall flags it **UNTRUSTED** (shown in red). Agents read it as quoted data and never act on it. | Context firewall against prompt injection |
| 6. Research safely | The research agent opens the vendor's status page in a **browser sandbox with no internet access** (only the allowlisted internal site) and brings back a screenshot as evidence: the PayCo SDK v5 release slipped. | Sandboxed tools |
| 7. Request an action | The action agent issues the syscall `jira.write` on APOLLO-12 with a justification and evidence. | Every action is a syscall |
| 8. Stop for a person | Policy says `jira.write` requires approval. The kernel pauses the process and raises an approval with the exact payload, the policy that triggered it and the evidence. A notification appears on the desktop and on the phone. | Human in the loop |
| 9. Approve and commit | Alice (or Priya, the approver, from her phone) approves. The kernel executes, verifies the write took effect, commits the transaction and appends to the audit chain. | Transactions, verification, audit |
| 10. Answer | Apollo is **31% (6.2 lakh) over budget**. Three root causes, each cited to its documents: dual-running cloud costs, a failed data backfill (duplicate reconciliation IDs), and the PayCo certification delay with an emergency contract. Plus a recovery plan file and `chain_verified: true`. | Cited, grounded answers |
| 11. Memory notices change | Edit `finance/cloud-bill-2026-09.md`. In about **0.1 s** the finance memories derived from it go stale (engineering's stay fresh); in about **3.5 s** the local model re-derives them from the new text. | Memory with provenance |

The run is scored automatically by `scripts/demo_run.py` out of 8 checks (task completed, three cited causes, the
injection flagged and not obeyed, the browser screenshot, the approval honoured, the write committed, the audit chain
verified, and the story of the run complete).

**Other scored scenarios**
- **Zeus:** a different project (Q4 budget risk briefing) with a reworded injection; same guarantees, 8/8.
- **Vendors:** *"Which vendors were paid more than their contract in Q3, and by how much? Draft a note."* Nobody
  scripted these agents: the planner creates a **data engineer** that writes SQL (checked by the kernel before it
  runs) and a **writer** that files the note after approval. Result: CloudCo overpaid by 1.44 lakh, PayCo by 0.42,
  TalentX by 0.11.
- **Multitool:** SQL, the browser, knowledge search and an approved write in one task.

---

## 4. Every feature, explained

### 4.1 The kernel: agents are processes

The kernel (`kernel/kairos_kernel`) keeps a **process table**. Every agent is a process with:
- a **PID**, a parent PID and a task ID (so a task is a tree of processes);
- a **state machine**: `CREATED → INITIALIZING → READY → RUNNING ⇄ WAITING / PAUSED / CHECKPOINTING → COMPLETED`, with
  `FAILED → RETRYING` and `TERMINATED` (kill) from any non-final state. The legal transitions live in the shared
  contract, so the kernel, the CLI and the UI buttons agree;
- **quotas**: model tokens, tool calls and wall time. A process that exceeds them is stopped;
- **capabilities**: the exact list of syscalls it may make, and **data scopes**: the `/org` paths it may read.

Operations: spawn, pause, resume, kill (a task is cancelled before its children), checkpoint. A **scheduler** runs a
limited number of tasks at once, with priorities and **preemption**, and supports scheduled agents (cron).
**Checkpoints** make tasks survive a crash: we verified by killing the daemon in the middle of a run; on restart the
task resumed and still scored 8/8. If the model server dies mid-run, the call is retried with backoff.

Agents talk to each other through kernel-mediated **IPC** messages (for example, specialists sending evidence to the
planner), which are also events.

### 4.2 Governed syscalls: the path every action takes

```
intent → policy → approval → execute (sandbox) → verify → commit
            │          │                             │
          deny      reject                     check fails → roll back
```

1. **Intent.** The agent calls `ctx.syscall(capability, resource, arguments, justification, evidence)`.
2. **Policy.** The policy engine evaluates YAML policies (`policies/*.yaml`): allow, deny, or require approval, per
   capability, per agent and per data scope. Policies **hot-reload** while the system runs.
3. **Approval.** If required, the process moves to `WAITING`, an approval record is created with the payload, the
   policy and the evidence, and notifications go out. It times out after a configurable period.
4. **Execute.** The tool runs, in a Docker sandbox where relevant.
5. **Verify.** The kernel checks the effect actually happened (for example, re-reads the Jira issue).
6. **Commit or roll back.** A transaction ID is recorded; a failed check rolls back.

Every step is an event and an audit entry. Writes to Jira, GitHub, Calendar and the database require approval by
default.

### 4.3 The audit journal: hash-chained

Every significant action (spawn, policy decision, approval, syscall, commit, rollback) is appended to a per-task
journal where each entry contains the hash of the previous one. Changing or deleting any entry breaks the chain. The
kernel verifies the chain and reports `chain_verified: true|false` with the result; the Audit app shows it.

### 4.4 Agents made for the job (dynamic agents)

Instead of a fixed cast, the planner decides which specialists a goal needs and the kernel **generates** them from
**role templates** (`agents/manifests/`): planner, finance, engineering, research, action, analyst, data-engineer and
writer. A generated agent's rights are an **intersection**:

```
capabilities = role template ∩ what the planner asked for ∩ what the person may do ∩ org policy
data scope   = template mounts ∩ requested scope ∩ the person's data scopes
```

- A viewer's task can never create an agent that writes, no matter what the planner asks for.
- A generated agent's own sub-agents can never get wider rights.
- Anything removed by the intersection produces an audit entry explaining why.
- Each generated agent gets a generated policy that can only narrow; writes always need a person.
- Generated manifests live only for the task and are cleaned up when it ends (and swept at boot).

What a person may ask of KAIROS is in `policies/rbac/roles.yaml`; what their task's agents may do is in
`policies/rbac/role-capabilities.yaml`.

### 4.5 The visible thought process

Agents narrate what they are doing through `ctx.narrate()`, and the kernel reports what actually happened. Six event
types make a run readable:

| Event | Meaning |
|---|---|
| `task.understood` | the intent, entities and capabilities the planner extracted |
| `agent.planned` | which role is needed, with what scope, and why |
| `agent.created` | the generated manifest of a new agent |
| `agent.thought` | a short visible step ("Read 8 documents, 2 flagged") |
| `tool.query` | the query a tool ran (for example the SQL text and the row count) |
| `task.data` | tabular results (columns and rows) |

Crucially, **tool results are reported by the kernel, not by the agent**, so the story cannot claim something
happened that did not. The desktop renders this as a story docked next to the run; the phone shows the same story.
A checker (`scripts/check_story.py`) verifies the story is complete for every scored scenario.

### 4.6 Knowledge as a filesystem

Company knowledge lives under `/org/...` as Markdown documents with **frontmatter**: type, owner, trust level,
privacy (`public`, `internal`, `restricted`), source and links. Folders such as `/org/finance`, `/org/engineering`,
`/org/inbox`, `/org/meetings`, `/org/projects`. The demo organization has 64 documents in 13 folders. Everything the
agents learn is traceable to a path.

**Ingestion** (`knowledge/kairos_knowledge/ingestion`): converters for Markdown, text and code, PDF, DOCX, PPTX, XLSX
(via markitdown), CSV, Slack exports and Jira JSON. Three ways in:
- **Upload**: drag files into the Add knowledge app; progress streams live as `ingest.progress` events.
- **Mount a folder of this computer**: it appears at `/org/mnt/<name>`, is converted and indexed, and is **watched**:
  save a file and it is re-ingested; delete it and it leaves. Mounts are read-only mirrors, so agents never write to
  your disk.
- **Connector sync**: GitHub issues and READMEs into `/org/github`, calendar meetings into `/org/calendar`.

### 4.7 Hybrid retrieval

Search combines three signals:
- **lexical** (keyword) matching, good for names, IDs and exact terms like `APOLLO-12`;
- **vector** similarity with `nomic-embed-text` embeddings stored in **pgvector**, good for meaning (with the model's
  query/document prefixes);
- the **knowledge graph** of links between documents, people and projects.

Results are filtered by **policy scope and privacy** before an agent sees them. On the QA set: 10 of 10 answered,
mean reciprocal rank 0.90.

### 4.8 The context firewall

Every retrieved document passes through the firewall before an agent reads it:
- a **regex layer**, always on, catches known injection patterns ("ignore previous instructions", fake system notes,
  requests to change policy);
- an optional **local LLM classifier** (`KAIROS_FIREWALL_LLM=true`) catches reworded injections: 3 to 4 of 5 caught,
  0 false positives, about 0.2 s per document.

Flagged text is marked **UNTRUSTED** and quoted to the agent as data, never placed where it could act as an
instruction. The UI shows it in red; the Knowledge app shows the flag on the document itself.

### 4.9 Memory that notices change

When an agent concludes something, it is consolidated into **memory** together with `derived_from`: the exact
documents it came from. A **file watcher** reindexes edited documents; a `knowledge.changed` event triggers
**invalidation**: within about **0.1 s** every memory derived from that document is marked stale (others stay fresh).
Then **re-derivation** asks the local model to reconsider the memory against the new text, in about **3.5 s**, and
replaces the old record. This is cache coherence for AI memory: the system knows which of its beliefs depend on which
facts.

### 4.10 Models and routing

The **model router** (`models/`) picks a model per kind of task and privacy level from a YAML file
(`models/models.yaml`, or `models.7b-only.yaml` for an 8 GB GPU). The demo runs **Qwen 2.5 7B Instruct** for reasoning
and **nomic-embed-text** for embeddings, both through **Ollama** on the laptop GPU (about 57 tokens/s, fully in VRAM).
A GPU probe reports utilisation and VRAM; `preflight.py` refuses to start a demo below 25 tokens/s. Restricted data is
never routed to a remote model.

### 4.11 Tools and connectors

| Tool | Capabilities | Safety |
|---|---|---|
| **Jira** (real or in-process mock) | `jira.read`, `jira.write` | writes need approval; verified after execution |
| **Files** | `fs.read`, `fs.write` | the task's own workspace only |
| **SQL database** | `db.query`, `db.write` | the kernel checks every statement before it runs: one statement, SELECT only for queries, no DDL, LIMIT at most 200, UPDATE and DELETE need WHERE; the backend adds a read-only transaction and a 5 s timeout; writes need approval |
| **Browser** | `browser.open` | Playwright in a Docker sandbox with no internet, only allowlisted internal origins; screenshots become evidence |
| **MCP servers** | `mcp.*` | any Model Context Protocol server can be exposed as governed tools; the Playwright MCP browser can replace the built-in driver (off by default) |
| **GitHub** | `github.*` | reads allowed, writes (issues, comments) need approval; demo data until a token is given |
| **Google Calendar** | `calendar.*` | reads allowed, creating events needs approval |

Connector tokens live in the **vault**, encrypted with Fernet (`KAIROS_VAULT_KEY`). They never reach an agent, an
event, the audit journal or a log.

### 4.12 Sandboxes

Docker containers (`execution/`) run tools that touch code or the web: a base image and a browser image. Defaults:
**no network** (an internal network with only the allowlisted vendor site for the browser), a non-root user (uid
10001), resource limits, and a per-task workspace. On Docker Desktop a relay makes the internal network reachable
without opening the internet.

### 4.13 Identity, organizations and roles

- **Organizations and members**, invitations, and five roles: **owner > admin > approver > member > viewer**.
- **Permissions** such as `task.create`, `task.cancel`, `approval.resolve`, `knowledge.read`, `knowledge.ingest`,
  `connectors.manage`, `config.read`, `members.manage`, defined in `policies/rbac/roles.yaml`. **Every gateway route
  checks** the caller's permission and answers `403 PERMISSION_DENIED` otherwise.
- **Sign-in**: `KAIROS_AUTH=google` verifies Google ID tokens and issues sessions; `KAIROS_AUTH=dev` allows email
  sign-in for development and demos.
- **One-time sign-in codes**: from the desktop, "Sign in on your phone" shows a short code; typing it on the phone
  signs the same person in, which works for Google accounts too.
- The UIs hide what a role may not do and say why (a viewer sees "can read results but not start tasks").

### 4.14 Observability and governance apps

- **Tasks / Task**: every task, its process tree, the live run and the result with evidence and artifacts.
- **Approvals**: pending decisions with risk, policy, payload and evidence; approve or reject with a comment.
- **Audit**: the journal per task and the chain verdict.
- **Agents**: the registry of templates with capabilities and limits.
- **System**: health of all 16 components, GPU and model gauges, sandboxes, a Terminal.
- **Settings**: `GET /system/config` rendered as one searchable picture of the running system: model routing, agents,
  tools and their risk, what needs a human, how people sign in, and the stack as layers with live health. Secrets are
  redacted.

---

## 5. The three ways in: desktop, phone, shell

All three use the same gateway, the same permissions and the same audit journal.

### 5.1 The desktop (`apps/web`, Next.js 16)

A desktop operating system in the browser:
- **The wallpaper is your knowledge**: a tiled floor where every coloured tile is one `/org` document, grouped by
  folder; tiles light up when an agent reads them. This is where the name comes from.
- **Windows** you can drag, resize, maximise, minimise and close; each app adapts to its window's width (container
  queries). A menu bar with the signed-in person and org; a centred command rail of apps.
- **Alt+Space** opens a floating Ask bar; Alt+1…9 opens apps; Alt+, opens Settings; Alt+/ lists all shortcuts.
- **The visible run**: the task docks left with its story; the stage shows agents as animated bot faces that work,
  wait and doze, documents and tools as they are used, and the approval when it comes.
- Apps: Tasks, Approvals, Knowledge (tree, frontmatter, trust flags, graph), Memory, Audit, Agents, System, Terminal,
  Add knowledge, Connections, Organization, Settings.
- Light and dark themes, WCAG AA contrast checked in tests.

### 5.2 The phone (`apps/mobile`, Expo SDK 57, a real Android APK)

- Sign in as a demo person, any email (dev), Google (native sign-in), or a **one-time code** from the desktop.
- **Home**: the role, live status, running and recent tasks.
- **Ask**: start a task (only roles with `task.create`).
- **Task**: the live run with agents as faces, the story, the answer and its evidence.
- **Approvals**: a card with the policy, the exact payload and the evidence; approve or reject (only roles with
  `approval.resolve`). A **notification** arrives when an action needs you.
- **Knowledge** search and **Me** (role, permissions, notification switch, sign out).
- Live over the WebSocket event stream; WCAG AA palette checked by a script.

### 5.3 KAIROS OS (`scripts/wsl`, Ubuntu 24.04 on WSL)

A real Linux distro where **`/org` is a FUSE filesystem served live by the gateway**:
- `ls /org/finance`, `cat` a document (with its frontmatter);
- **search as a directory**: `ls /org/.search/apollo overrun`;
- **`cp` a file into `/org`** to add knowledge;
- the `kairos` command: `kairos ask "…"` streams a run and waits for approvals, plus approve, search, mount and sign
  in with a desktop code.

There is also the `ai-*` CLI on the host: `ai run`, `ai-ps`, `ai-tree`, `ai-top`, `ai approve`, `ai-audit`.

### 5.4 The Python package (`sdk/python`, `pip install kairos-os`)

A dependency-free Python client library and the same `kairos` command for any machine that can reach a gateway,
including a teammate's laptop over a public URL. It covers tasks with a live story, approvals, search, reading `/org`,
uploads, mounts, memory, the process table and the audit chain, with `--json` on every command for scripting. Its
documentation is `sdk/python/README.md`.

---

## 6. What is novel

| Novelty | Why it matters | Typical agent frameworks |
|---|---|---|
| **Agents as OS processes** with PIDs, quotas, capabilities, pause, kill, checkpoint and resume | Agents become manageable, limitable and recoverable like programs | an agent is a loop in your script |
| **One mediated path for every action** (policy, approval, sandbox, verify, commit or roll back) | No action can bypass governance; failures roll back | tools are called directly |
| **Hash-chained audit with a kernel verdict** | You can prove what happened and detect tampering | logs, if any |
| **Agents generated per task, bounded by a four-way intersection** (template, request, person, policy) | Least privilege by construction; a viewer's task can never write | fixed agents with fixed tools |
| **Kernel-reported thought process** | The visible story cannot claim actions that did not happen | the model's own text, unverifiable |
| **Context firewall** treating retrieved text as data, regex plus an optional local classifier | Defends against prompt injection in documents and email | retrieved text pasted into the prompt |
| **Memory with provenance and cache coherence** (stale in 0.1 s, re-derived in 3.5 s) | The system knows which beliefs a changed fact invalidates | memories never expire |
| **Knowledge as a filesystem**, including a real FUSE mount and watched folders | Familiar, scriptable, auditable data access with privacy and trust per document | an opaque vector store |
| **SQL checked by the kernel before it runs** | Agents can use databases without arbitrary writes or DDL | raw SQL access |
| **Three surfaces on one kernel**: a desktop OS, a phone app and a Linux shell | Approve from your pocket; script from a shell; watch on a desktop | a chat window |
| **Fully local on an 8 GB laptop GPU** | Private data never leaves the machine | cloud APIs |
| **Fake and real implementation of every component behind one typed contract** | Four people built it in parallel; UIs work with no GPU | tightly coupled code |

---

## 7. Architecture

```
  Desktop (Next.js, :3000)     Phone (Expo APK)     KAIROS OS (FUSE /org, kairos)     ai-* CLI
                 │         HTTP + WebSocket /ws/events        │
                 ▼                                            ▼
  ┌──────────────────────── kairosd: one Python process, FastAPI gateway on :8089 ───────────────────────┐
  │ identity   orgs, members, roles, sessions, Google sign-in, sign-in codes, vault                        │
  │ kernel     process table, scheduler, quotas, syscalls, policy, approvals, transactions, audit chain,   │
  │            dynamic agents, event bus, lifecycle (resume after a crash)                                 │
  │ agents     runtime, role templates and library agents, narration, IPC, registry, NOOA adapter          │
  │ knowledge  ingestion and converters, indexing, hybrid retrieval, context firewall, memory, coherence,   │
  │            uploads and mounts                                                                          │
  │ models     router, Ollama provider, GPU probe                                                          │
  │ execution  sandbox manager, tools (Jira, files, SQL, browser, GitHub, Calendar), MCP backend            │
  └──────────┬───────────────────┬──────────────────┬──────────────────────┬──────────────────────────────┘
             ▼                   ▼                  ▼                      ▼
     Postgres + pgvector    Redis (events)     Ollama (GPU)      Docker: sandbox-base, sandbox-browser,
     (knowledge, memory,                                          vendor-docs, internal sandbox network
      audit, demo data)
```

**Packages**

| Package | Responsibility |
|---|---|
| `shared/` | **The contract**: Pydantic schemas, Protocol interfaces, fakes and contract test suites, catalogs of events, errors and capabilities, the generated OpenAPI spec and TypeScript types, a mock gateway |
| `kernel/`, `kairosd/` | the kernel, identity, the gateway, the CLI, and `wiring.py` (the only place that chooses implementations) |
| `knowledge/` | `/org`, ingestion, indexing, retrieval, firewall, memory |
| `agents/`, `models/` | agent runtime and library, model router |
| `execution/` | tools, connectors, sandboxes, browser, MCP |
| `apps/web/`, `apps/mobile/`, `scripts/wsl/` | the three clients |
| `policies/` | YAML policies and the role tables |
| `data/okf/` | the demo organization's knowledge bundle |

**The contract and fake/real wiring.** Everything that crosses a package boundary is defined once in
`shared/python/kairos_contracts` (contract version 0.13.0), and TypeScript types are generated from it. Each
component (events, policy, audit, knowledge, memory, firewall, models, agents, tools, sandbox, browser, converters,
probe and more) has a **fake** and a **real** implementation, chosen per component with `KAIROS_MODE_<COMPONENT>`.
This let four people build in parallel against the same interfaces, lets the whole UI run against a mock gateway with
no GPU, and makes every component independently replaceable. A test keeps the mock gateway's routes identical to the
real gateway's.

**APIs.** REST (documented in `shared/api/openapi.json`, Swagger at `/docs`) grouped as system, identity, connectors,
tasks, agents, registry, knowledge, memory, governance and execution, plus one WebSocket (`/ws/events`) that streams
every event in `shared/catalogs/events.yaml`.

---

## 8. Technology stack

| Layer | Technology | Why |
|---|---|---|
| Language (backend) | **Python 3.12**, async, type hints | the AI ecosystem; async for many concurrent agents and streams |
| API | **FastAPI**, **Pydantic v2**, WebSockets | typed models shared with the contract; OpenAPI generated for free |
| Packaging | **uv** workspaces | six packages, one lock file, fast installs |
| Database | **Postgres 16 + pgvector** | knowledge, embeddings, memory and audit in one transactional store |
| Events | **Redis 7** | event mirror for streaming to clients |
| Models | **Ollama**, **Qwen 2.5 7B Instruct**, **nomic-embed-text** | strong local reasoning that fits in 8 GB VRAM; private by design |
| Sandboxes | **Docker** (internal networks, non-root, resource limits) | isolation for tools that touch code or the web |
| Browser | **Playwright** (Chromium), **@playwright/mcp** | real page rendering and screenshots inside a sandbox |
| Tool protocol | **Model Context Protocol (MCP)** | plug in any MCP server as a governed tool |
| Conversion | **markitdown** | PDF, Office and other formats to Markdown |
| Identity | **Google Identity** (ID tokens), sessions, **Fernet** vault | real sign-in; tokens encrypted at rest |
| Desktop | **Next.js 16**, **React**, **Tailwind 4**, **TanStack Query**, container queries | a fast, responsive desktop-in-a-browser |
| Phone | **Expo SDK 57**, **React Native 0.86**, native Google sign-in | one codebase, a real Android APK |
| Shell OS | **Ubuntu 24.04 on WSL 2**, **FUSE** (fusepy), systemd | `/org` as a real filesystem |
| Quality | **pytest**, pytest-cov, **ruff**, **eslint**, **tsc**, Vitest, GitHub Actions | 535 tests, lint and type checks, CI on every push |
| Demo ops | PowerShell scripts, `preflight.py`, `demo_run.py` | one-command boot, readiness checks, scored runs |

---

## 9. Security model

| Threat | Defence |
|---|---|
| An agent takes a harmful action | Agents hold no credentials; every action is a syscall through policy; writes need a person; verification and rollback |
| Prompt injection in documents or email | Context firewall: regex plus an optional LLM classifier; untrusted text is quoted as data |
| Over-privileged agents | Capabilities and data scopes are the intersection of template, request, person and policy; sub-agents never widen |
| Data exfiltration | Sandboxes have no network unless allowlisted; restricted data stays on local models; everything runs on one machine |
| Arbitrary SQL | The kernel refuses anything it cannot read with confidence; read-only transactions; timeouts; row limits |
| Unauthorized people | Sessions, Google sign-in, five roles enforced on every route; one-time codes for phones |
| Credential leaks | Connector tokens encrypted in the vault, never in events, logs, audit or agent context |
| Tampering with history | Hash-chained audit journal; the kernel verifies the chain |
| Runaway agents | Quotas on tokens, tool calls and wall time; pause and kill |

Vulnerabilities are reported privately through GitHub's private vulnerability reporting (see `SECURITY.md`).

---

## 10. Results and measurements

Measured on the demo laptop: RTX 5070 Laptop GPU (8 GB), `qwen2.5:7b-instruct` fully on the GPU.

| Scenario | Score | Wall time |
|---|---|---|
| Apollo | 8/8, story check pass | about 100 s |
| Zeus | 8/8, story check pass | about 110 s |
| Vendors | 8/8, story check pass | about 21 s |
| Multitool | 8/8, story check pass | about 44 s |
| Zeus with the LLM classifier | 9/9 | about 104 s |

| Metric | Result |
|---|---|
| Model throughput | about 57 tokens/s (preflight requires at least 25) |
| Memory invalidation after a source edit | about 0.1 s |
| Memory re-derivation | about 3.5 s |
| Retrieval QA | 10/10 answered, MRR 0.90 |
| Firewall classifier | 3 to 4 of 5 reworded injections, 0 false positives, about 0.2 s per document |
| Components running real (not fake) | 16 of 16 |
| Recovery | daemon killed mid-run: resumed from checkpoint, 8/8; model server restarted mid-run: retried, 8/8 |

---

## 11. Quality: testing and engineering process

- **535 tests**: 442 Python (unit, contract suites run against both fakes and real implementations, integration) and
  93 web (including WCAG AA contrast for both themes). Python coverage 85%.
- **Static checks**: ruff for Python; eslint and TypeScript for the desktop and the phone; a contrast script for the
  phone palette.
- **CI** (GitHub Actions): ruff, the full Python suite against Postgres with pgvector and real Docker sandboxes, and a
  check that generated contract files are up to date.
- **"The demo is sacred"**: anything that touches retrieval, prompts, agents, policies or knowledge must keep all four
  scored scenarios at 8/8 on real models before it is merged.
- **Contract discipline**: contract changes go on their own branch with a version bump and regenerated artifacts;
  generated files are never hand-edited.
- **Readiness**: `preflight.py` checks every component is real, models are loaded fully on the GPU at speed, sandboxes
  and the knowledge bundle are ready, and search works; it must print "all green".

---

## 12. Limitations, trade-offs and future work

**Trade-offs we chose**
- **A 7B local model**: privacy and an 8 GB GPU over the reasoning depth of large hosted models. Prompts and agents
  are designed for its strengths, and every run is scored.
- **Firewall classifier opt-in**: the regex layer is instant and never misses a known pattern; the classifier catches
  rewordings at about 0.2 s per document.
- **Conservative SQL checks without a full parser**: some valid queries are refused rather than risk an unsafe one.
- **Read-only mounts**: agents never write to your disk; changes go through governed paths.

**Current limits (beta)**
- One node; no high availability yet.
- GitHub and Calendar tested with built-in demo data, not yet with live accounts; Google sign-in verified against
  Google's token format in tests, not yet with a live client ID.
- Phone notifications are local (while the app is open or recently backgrounded), not push.
- The APK is debug-signed.

**Future work**
- Multi-node kernel with a shared process table and queue; horizontal scaling of tool workers and sandboxes.
- Push notifications and approval from a watch or chat.
- More connectors (email, Slack, Drive) through MCP.
- Policy authoring UI with simulation ("what would this policy have blocked last week?").
- Larger local models or mixed routing per privacy level as hardware allows.

---

## 13. Team

**Team KAIROS:** Mishka Tiwari, Kamal Karteek U, Manjunath Patil, Mayeraa Singh.

KAIROS is built four ways through one shared contract (`shared/`), each person owning an interface boundary:

| Person | Owns |
|---|---|
| **Kamal Karteek U** (`@kamalllx`) | the kernel and governed execution, the desktop OS, KAIROS OS on WSL, the phone app and APK |
| **Mishka Tiwari** (`@mishhkaaa`) | agents and the planner, dynamic agents, the thought-process stream, the SQL tool, the web researcher |
| **Mayeraa Singh** (`@mayeraasingh`) | knowledge, ingestion and retrieval, identity, organizations and connectors |
| **Manjunath Patil** (`@manjunath3155`) | models and routing, platform and infrastructure, settings, the Python package, demo data |

---

## 14. Questions people ask

**Is this just a chatbot with a nice UI?** No. The UI is one of three clients. The core is a kernel that runs agents
as processes and mediates every action through policy, approval, sandboxing, verification and a hash-chained journal.
You can drive it from a Linux shell with no UI at all.

**What stops an agent from ignoring the approval?** Agents have no direct access to tools or credentials. The only way
to act is `ctx.syscall()`, and the kernel executes the tool itself, only after policy and approval.

**What if the model is tricked by a document?** The firewall flags instruction-like text and quotes it as data. Even if
a model were persuaded, it still cannot act outside its capabilities, and every write still needs a person.

**Why local models?** Because the target users are organizations that cannot send private data to a cloud. A 7B model
on an 8 GB laptop GPU is enough for all four scored scenarios.

**How do you know it works, rather than worked once?** Every scenario is scored automatically out of 8, including the
story of the run, and must pass on real models before any merge; plus 535 tests and CI on every push.

**How does it scale?** Components sit behind one typed contract and can be swapped or moved independently; the
scheduler already enforces quotas, concurrency and preemption, and checkpoints let tasks survive restarts. Today it is
a single node; multi-node is future work.

**How are agents created for a new kind of question?** The planner picks role templates that fit the goal (for example
a data engineer and a writer for a vendor-payments question), and the kernel generates them with rights limited by the
intersection described in section 4.4.

**What happens when data changes?** Memories record their sources; an edit marks dependent memories stale in about
0.1 s, and they are re-derived in about 3.5 s.

---

## 15. Glossary

| Term | Meaning |
|---|---|
| **kairosd** | the single Python daemon: kernel, services and the FastAPI gateway |
| **Kernel** | the part that owns processes, policy, approvals, transactions and audit |
| **Syscall** | a request by an agent to perform a world-changing action |
| **Capability** | the name of an action an agent may request, such as `jira.write` or `db.query` |
| **Data scope** | the `/org` paths an agent may read |
| **Role template** | a manifest describing a kind of agent (finance, research, data engineer…) from which agents are generated |
| **Planner** | the first process of a task; it understands the goal and creates the specialists |
| **Approval** | a pending decision by a person on a syscall that policy marked as requiring one |
| **Audit chain** | the per-task journal in which each entry hashes the previous one |
| **Context firewall** | the layer that flags untrusted, instruction-like text in retrieved documents |
| **`derived_from`** | the list of source documents a memory was built from |
| **OKF** | the Markdown-with-frontmatter format of the `/org` knowledge bundle |
| **Contract** | the shared, versioned schemas and interfaces in `shared/` |
| **Fake / real** | the two implementations of every component, chosen per component |
| **MCP** | Model Context Protocol, a standard for exposing tools to AI agents |
| **FUSE** | Filesystem in Userspace; how `/org` becomes a real directory in KAIROS OS |
