# P1 Kernel & Execution: what this split provides
Packages: `kernel/` (`kairos_kernel`), `execution/` (`kairos_execution`, minus `browser/`), `kairosd/`, `policies/`

| Provides | Kind | Consumers | Fake until ready | Contract |
|---|---|---|---|---|
| `AgentContext` (KernelAgentContext) | in-process ABI | P3 agents | `FakeAgentContext` | via `AgentRuntimeContract` |
| `EventBus` | interface | everyone | `InMemoryEventBus` | `EventBusContract` |
| `PolicyEngine` | interface | kernel, UI via `/policies` | `FakePolicyEngine` | `PolicyEngineContract` |
| `AuditLog` | interface | UI via `/audit/{task}` | `InMemoryAuditLog` | `AuditLogContract` |
| `ToolExecutor` (jira, fs, browser, sandbox) | interface | kernel transactions | `FakeToolExecutor` | `ToolExecutorContract` |
| `SandboxManager` | interface | executor, `/sandboxes` | `FakeSandboxManager` | `SandboxManagerContract` |
| `ArtifactStore` | interface | ctx, `/tasks/{id}/artifacts` | `InMemoryArtifactStore` | `ArtifactStoreContract` |
| Gateway REST + WS | HTTP (`shared/api/openapi.json`) | P2 UI, CLI, mobile | `kairos-mock-gateway` | route conformance |
| `ai-*` CLI | commands | humans / demo | — | — |
| mock Jira `:8090` | service | executor | `FakeToolExecutor.issues` | via `ToolExecutorContract` |

**Events published:** `task.*`, `process.*`, `agent.log`, `syscall.*`, `approval.*`, `transaction.*`, `policy.updated`, `audit.appended`, `ipc.message`, `knowledge.retrieved`, `model.invoked`, `sandbox.*`, `tool.*`, `system.*`, and the thought-process events (0.10.0): `agent.created` on spawn, `tool.query` + `task.data` after a query tool, and `task.understood` / `agent.planned` / `agent.thought` on behalf of agents via `ctx.narrate()` (pid stamped by the kernel) (payloads: `shared/catalogs/events.yaml`).

**Behaviour notes for consumers**
- `WS /ws/events?task_id=…` first **replays the task's history** (durable across restarts when Redis is up), then streams live events. Filter with `types=task.*,process.*`.
- `network_allow` in `PolicyDecision.constraints` restricts **agent-chosen destinations** (browser URLs, sandbox egress). Operator-configured connectors (`KAIROS_JIRA_URL`, MCP servers) are trusted endpoints. If the key is absent, there is no constraint; if it is present but empty, nothing is allowed.
- The kernel does **not** re-screen search results: `KnowledgeService.search` (P2) screens with the firewall. The kernel logs an `agent.log` warning for flagged hits.
- **Approvals come in two kinds.** Privileged syscalls use the capability of the tool operation. **Escalations** (`capability: agent.retry`, `policy: kernel.escalation`) mean an agent exhausted its retries and a human decides whether to try once more. Both appear in `GET /approvals` and in `approval.requested` events, and the payload includes `tool`, `operation`, `risk` and `policy`.
- **Restart semantics:** stopping `kairosd` suspends running tasks. On the next boot they resume from the root agent's last `ctx.checkpoint()` (up to `KAIROS_KERNEL_MAX_RESTARTS`), queued tasks re-queue, and pending approvals expire (the resumed run asks again). Agents that call `ctx.checkpoint(state)` receive it back through `AgentRuntime.restore`.
- **Preemption:** a `high` task arriving when every slot is busy pauses a running `background` task (its processes show `PAUSED`), which resumes afterwards.
- `KAIROS_JIRA_URL=inprocess` runs mock Jira inside `kairosd` (no Docker needed). Otherwise use `uv run kairos-mock-jira` or the compose service.
- MCP servers listed in `$KAIROS_MCP_CONFIG` (see `execution/mcp.example.yaml`) become tools. Every operation requires the configured capability (default `mcp.call`), so policies must allow it.
- Test helpers for scripting agents against a real kernel: `kairos_kernel.testing` (`kernel_factory`, `ScriptedRuntime`, `start_task`).
- Kernel knobs (`KAIROS_KERNEL_*`) are listed in `.env.example` and `kairos_kernel/config.py`.
- Scheduled agents: `KAIROS_KERNEL_SCHEDULES_FILE` (see `kernel/schedules.example.yaml`). Each firing publishes `cron.triggered` and creates a normal task owned by user `scheduler`, and a job never overlaps itself.

**Totals at hand-off:** P1 suites 97 passed, 1 skipped (waiting on P4's BrowserDriver). Whole repo 171 passed, 34 skipped (all other splits' pending work).
**Integrated (`integration/m3`, 2026-09-28):** whole repo 290 passed, 0 failed, 3 skipped (P4's document converter).

## How it is tested
| Suite | What it proves | Needs |
|---|---|---|
| `kernel/tests/*` | lifecycle, syscalls, policy, audit chain, scheduler/preemption, cron, restart/resume, escalation, hot reload, isolation, idempotency, stress (20 tasks / 80 agents), every gateway route, the CLI | nothing |
| `kernel/tests/test_redis_live.py` | event mirror + history replay across a kernel restart | Docker (starts `redis:7-alpine`) |
| `execution/tests/test_contract.py`, `test_execution_units.py`, `test_mcp.py` | artifact/tool/sandbox contracts, jails, allowlists, rollback, hardening kwargs, MCP against a real MCP server | nothing (sandbox suite needs Docker) |
| `execution/tests/test_docker_live.py` | inside a real container: uid 10001, read-only rootfs, CapEff=0, NoNewPrivs, no network, limits, timeout reaper | Docker + `kairos/sandbox-base` |
| `execution/tests/test_jira_http_live.py` | tool contract over real HTTP (starts its own container) | Docker + `kairos/mock-jira` |
| `execution/tests/test_browser_live.py` | real browser sandbox + Playwright: page, allowlist, screenshot, cleanup | Docker + `kairos/sandbox-browser` |
| `tests/integration/test_e2e_apollo.py` | the demo run through the gateway | nothing |
| `tests/integration/test_live_system.py` | the demo run with **every P1 component real** on real Redis + mock-Jira containers | Docker + `kairos/mock-jira` |

## Status (owner keeps this current)
| Item | Status |
|---|---|
| EventBus (+ Redis Stream mirror) · AuditLog (SQLite, hash chain; `RunTimeline.chain_verified` recomputes it, contract 0.6.0) · PolicyEngine (YAML, hot reload) | ✅ |
| Process table · lifecycle (retry, escalation, kill tree, pause/resume) · tasks · scheduler (priorities, GPU admission, preemption) | ✅ |
| KernelAgentContext + IPC mailboxes | ✅ |
| `ctx.narrate()` (0.10.0): validates and publishes the three agent-told events | ✅ (agent.created, tool.query, task.data emission: `b/thought-events`) |
| Dynamic agents (0.11.0): `ctx.spawn(..., capabilities, scope, why)` narrows only; `ServiceBundle.permissions` (`PermissionsProvider` → `UserPermissions`) bounds every agent a task creates | contract + scope narrowing ✅; generation, generated policies, cleanup: `b/dynamic-agents` |
| Syscalls · approvals · transactions (verify → commit / rollback) · idempotency | ✅ |
| Gateway (route conformance, WS history replay) · CLI (`ai-*`, `ai run`) | ✅ |
| Artifacts · fs (jailed, reversible) · mock Jira + jira tool · executor · MCP adapter | ✅ |
| Docker sandbox manager (hardening verified inside live containers) | ✅ |
| Browser backend | ✅ with P4's `PlaywrightDriver` on `integration/m3` (screenshots in real runs) |
| Integrated on `integration/m3` (2026-09-28) | ✅ real runs through the console (75 s, 1 approval, hash chain intact); hard kill mid-run → task resumed from its root checkpoint and completed |
| Deferred: browser sandbox egress in port mode (Docker Desktop) | ☐ default bridge is needed to publish :3000; needs a relay or kairosd on `kairos_sandbox`. `ip` mode (Linux node) is unaffected |
| Quotas · suspend/resume across restarts · checkpoints | ✅ |
| e2e: all-fake ✅ · every P1 component real on real containers ✅ | ✅ |
| Scheduled agents (cron, `KAIROS_KERNEL_SCHEDULES_FILE`) | ✅ |
| Model outages: an agent whose run fails on `MODEL_UNAVAILABLE`/`TIMEOUT` (raised, or returned as a FAILED result by the runtime) is retried after 5 s, then 15 s (`KAIROS_KERNEL_RETRY_BACKOFF_S`), unless it has spawned children or holds approval-gated capabilities (a re-run would repeat work or a write). Crashes still retry at once | ✅ live: an Ollama restart mid-run is ridden out; Ollama stopped for good → `task.failed` in 91 s with the reason |
| Wall-time quota enforced while an agent is blocked (a model call, a child, a backoff), not only at its next `ctx.*` call; floor `KAIROS_KERNEL_MIN_AGENT_WALL_S` (1800 s) | ✅ live: a 30 s task quota → `task.failed` (`QUOTA_EXCEEDED`) at 30.4 s, nothing left running |
| Stretch not done: OpenShell/microVM sandbox backend | ☐ |
