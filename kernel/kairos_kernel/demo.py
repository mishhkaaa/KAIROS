"""P1 demo: a narrated terminal run-through of the KAIROS kernel & execution layer.

    uv run ai-demo                 # full demo (~1 minute), approvals auto-granted after a short pause
    uv run ai-demo --interactive   # you approve/reject the privileged action yourself
    uv run ai-demo --fast          # no pauses (CI / recording)

Everything P1 owns runs for real: event bus, YAML policy engine, SQLite audit log (hash chain), state store,
artifact store, tool executor with the Jira connector (mock Jira in-process) and workspace files, plus the Docker
sandbox scene when Docker is available. Knowledge / models / agents belong to P2/P3, so the demo uses the shared
stand-ins for them and small scripted "Apollo" agents that exercise the full agent API (ctx.*).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    A2AMessage,
    AgentResult,
    AgentResultStatus,
    AgentState,
    ChatMessage,
    ManifestCapabilities,
    ManifestResources,
    ManifestRuntime,
    MessageType,
    ModelRequest,
    Priority,
    Risk,
    Role,
    SearchQuery,
    SyscallRequest,
    TaskCreate,
)
from kairos_contracts.schema.agents import AgentManifest
from kairos_contracts.schema.common import new_id
from kairos_contracts.testing.fakes import (
    FakeAgentRegistry,
    FakeBrowserDriver,
    FakeSandboxManager,
    fake_bundle,
    load_manifests,
    user_principal,
)
from kairos_contracts.wiring import REPO_ROOT, Settings

from .audit.log import SqliteAuditLog
from .config import KernelConfig
from .events.bus import KernelEventBus
from .kernel import Kernel
from .policy.engine import YamlPolicyEngine

for _s in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
    if hasattr(_s, "reconfigure") and (getattr(_s, "encoding", "") or "").lower().replace("-", "") != "utf8":
        try:
            _s.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.tree import Tree  # noqa: E402

console = Console(highlight=False)
STATE_STYLE = {"RUNNING": "green", "WAITING": "yellow", "PAUSED": "blue", "FAILED": "red", "RETRYING": "magenta",
               "COMPLETED": "dim", "TERMINATED": "red", "CHECKPOINTING": "cyan"}
GOAL = ("Investigate why Project Apollo is over budget and six weeks behind schedule. "
        "Identify root causes, update the tracker, and prepare a recovery plan.")


class Pace:
    def __init__(self, fast: bool) -> None:
        self.fast = fast

    async def __call__(self, seconds: float) -> None:
        if not self.fast:
            await asyncio.sleep(seconds)


def scene(n: int, title: str, what: str) -> None:
    console.print()
    console.rule(f"[bold cyan]Scene {n} · {title}")
    console.print(f"[dim]{what}[/]")


def state(s: str) -> str:
    return f"[{STATE_STYLE.get(s, 'white')}]{s}[/]"


# ============================================================================ the "Apollo" agents (scripted)
# Real P3 agents will reason with LLMs; these deterministic ones exercise the same kernel API.

def result(ctx: Any, summary: str, **output: Any) -> AgentResult:
    return AgentResult(pid=ctx.pid, agent=ctx.manifest.name, status=AgentResultStatus.COMPLETED, summary=summary,
                       output=output, evidence=output.pop("_evidence", []))


async def share_with_parent(ctx: Any, content: str, paths: list[str]) -> None:
    if ctx.ppid:
        await ctx.send(A2AMessage(message_id=new_id("MSG"), task_id=ctx.task_id, sender_pid=ctx.pid,
                                  receiver_pid=ctx.ppid, sender="", receiver="", type=MessageType.EVIDENCE,
                                  content=content, provenance=paths))


async def planner(goal: str, ctx: Any) -> AgentResult:
    restored = ctx.inputs.get("_restored")
    await ctx.log("Decomposing the goal into specialist subtasks" if not restored else
                  f"Resumed from checkpoint: {restored}")
    overview = await ctx.search(SearchQuery(text="Project Apollo status budget schedule", top_k=4))
    await ctx.llm(ModelRequest(messages=[ChatMessage(role=Role.USER, content=f"Plan: {goal}")]))
    specialists = {"finance-agent": "Explain the Apollo budget variance",
                   "engineering-agent": "Find the engineering causes of the 6-week slip",
                   "research-agent": "Collect vendor SDK context"}
    pids = {name: await ctx.spawn(name, sub) for name, sub in specialists.items()}
    results = {name: await ctx.wait(pid) for name, pid in pids.items()}
    await ctx.checkpoint({"stage": "specialists-done", "findings": {n: r.summary for n, r in results.items()}})
    inbox = []
    while (msg := await ctx.receive(timeout=0.05)) is not None:
        inbox.append(f"{msg.sender}: {msg.content}")
    causes = [r.output["cause"] for r in results.values() if r.output.get("cause")]
    action = await ctx.wait(await ctx.spawn("action-agent", "Record the root causes on APOLLO-12",
                                            {"root_causes": causes}))
    plan = ("# Apollo recovery plan\n\n## Root causes\n" + "".join(f"- {c}\n" for c in causes)
            + "\n## Actions\n1. Stop the dual-run as soon as the ledger backfill passes parity (ADR-042)\n"
              "2. Re-run the backfill with deduplicated reconciliation ids (APOLLO-12)\n"
              "3. Escalate the SDK v5 certification with the vendor; keep the v4 path until GA (APOLLO-31)\n"
            + f"\n## Tracker\nAPOLLO-12 update: {action.summary}\n")
    ref = await ctx.put_artifact("recovery-plan.md", plan, "text/markdown")
    evidence = sorted({p for r in results.values() for p in r.evidence} | {h.path for h in overview.hits})
    summary = (f"Apollo is 31% over budget and 6 weeks late. Root causes: {'; '.join(causes)}. "
               f"Tracker: {action.summary}. Recovery plan: {ref}")
    out = result(ctx, summary, root_causes=causes, ipc_messages=inbox, _evidence=evidence)
    out.artifacts.append(ref)
    return out


async def finance(goal: str, ctx: Any) -> AgentResult:
    ev = await ctx.search(SearchQuery(text="Apollo budget overrun cloud cost variance", top_k=3))
    budget = await ctx.read("/org/finance/apollo-budget")
    await ctx.llm(ModelRequest(messages=[ChatMessage(role=Role.USER, content=budget.body[:500])]))
    cause = "dual-run cloud cost (+1.9 lakh) caused by the migration slip and ADR-042"
    await share_with_parent(ctx, f"Overrun 6.2 lakh (31%); biggest driver: {cause}", [budget.path])
    return result(ctx, "31% overrun (6.2 lakh); cloud dual-run is the largest driver", cause=cause,
                  _evidence=[h.path for h in ev.hits])


async def engineering(goal: str, ctx: Any) -> AgentResult:
    ev = await ctx.search(SearchQuery(text="Apollo migration delay blocker schedule", top_k=3))
    issues = []
    for key in ("APOLLO-12", "APOLLO-31"):
        res = await ctx.syscall(SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid,
                                               capability="jira.read", tool="jira", operation="get_issue",
                                               arguments={"key": key}, justification="read the tracker"))
        if res.tool_result:
            issues.append(f"{key} {res.tool_result.output['status']}")
    cause = "ledger backfill failed on duplicate reconciliation ids (APOLLO-12)"
    await share_with_parent(ctx, f"{cause}; tracker says {', '.join(issues)}", [h.path for h in ev.hits])
    return result(ctx, f"6-week slip: {cause}", cause=cause, issues=issues, _evidence=[h.path for h in ev.hits])


async def research(goal: str, ctx: Any) -> AgentResult:
    ev = await ctx.search(SearchQuery(text="vendor SDK v5 delayed", top_k=3))
    page = await ctx.syscall(SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid,
                                            capability="browser.open", tool="browser", operation="open",
                                            arguments={"url": "http://vendor-docs/sdk-v5.html"},
                                            justification="confirm the vendor's release date"))
    text = page.tool_result.output.get("text", "") if page.tool_result else ""
    cause = "vendor SDK v5 blocked on certification (APOLLO-31)"
    await share_with_parent(ctx, f"{cause}. Vendor page: {text[:60]}", [h.path for h in ev.hits])
    return result(ctx, f"Vendor: {text[:70]}", cause=cause, _evidence=[h.path for h in ev.hits])


async def action(goal: str, ctx: Any) -> AgentResult:
    causes = ctx.inputs.get("root_causes", [])
    res = await ctx.syscall(SyscallRequest(
        syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid, capability="jira.write", tool="jira",
        operation="update_issue", resource="APOLLO-12", risk=Risk.MEDIUM,
        arguments={"key": "APOLLO-12", "fields": {"status": "At Risk"},
                   "comment": "KAIROS root causes: " + "; ".join(causes)},
        justification="Record the root causes on the migration ticket",
        evidence=["/org/finance/apollo-budget", "/org/engineering/apollo-status", "/org/decisions/ADR-042"]))
    await ctx.syscall(SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid, capability="fs.write",
                                     tool="fs", operation="write_file",
                                     arguments={"path": "reports/apollo-root-causes.md",
                                                "content": "\n".join(f"- {c}" for c in causes)}))
    return result(ctx, f"jira.write {res.status.value}", syscall=res.status.value)


# --- agents used by the "OS controls" scenes
async def long_runner(goal: str, ctx: Any) -> AgentResult:
    child = await ctx.spawn("research-agent", "background research")
    for i in range(600):
        await ctx.log(f"working… step {i}")
        await asyncio.sleep(0.02)
    await ctx.wait(child)
    return result(ctx, "done")


async def chatty(goal: str, ctx: Any) -> AgentResult:
    while True:
        await ctx.llm(ModelRequest(messages=[ChatMessage(role=Role.USER, content="think " * 300)]))


async def rogue(goal: str, ctx: Any) -> AgentResult:
    outcomes = {}
    for cap, tool, op, args in [("jira.write", "jira", "update_issue", {"key": "APOLLO-31", "fields": {"status": "Done"}}),
                                ("sandbox.exec", "sandbox", "exec", {"command": ["rm", "-rf", "/workspace"]})]:
        res = await ctx.syscall(SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid,
                                               capability=cap, tool=tool, operation=op, arguments=args))
        outcomes[f"{tool}.{op}"] = f"{res.status.value}: {res.decision.reason}"
    try:
        await ctx.read("/org/finance/payroll-2026")
        outcomes["read payroll"] = "ALLOWED"
    except KairosError as e:
        outcomes["read payroll"] = f"{e.code}"
    return result(ctx, "tried", **outcomes)


async def resumable(goal: str, ctx: Any) -> AgentResult:
    if "_restored" in ctx.inputs:
        return result(ctx, f"resumed after restart from checkpoint {ctx.inputs['_restored']}")
    await ctx.checkpoint({"stage": "evidence-gathered", "hits": 3})
    await asyncio.sleep(3600)
    return result(ctx, "unreachable")


class DemoRuntime:
    SCRIPTS = {"planner-agent": planner, "finance-agent": finance, "engineering-agent": engineering,
               "research-agent": research, "action-agent": action, "long-runner": long_runner, "chatty-agent": chatty,
               "rogue-agent": rogue, "resumable-agent": resumable}

    async def run(self, manifest: AgentManifest, goal: str, ctx: Any) -> AgentResult:
        return await self.SCRIPTS[manifest.name](goal, ctx)

    async def restore(self, manifest: AgentManifest, goal: str, ctx: Any, state: dict) -> AgentResult:
        ctx.inputs["_restored"] = dict(state)
        return await self.run(manifest, goal, ctx)


def extra_manifests() -> list[AgentManifest]:
    def m(name: str, tools: list[str] | None = None, agents: list[str] | None = None, tokens: int = 12_000,
          mounts: list[str] | None = None) -> AgentManifest:
        return AgentManifest(name=name, description=f"demo {name}", runtime=ManifestRuntime(entrypoint="demo:x"),
                             memory={"mounts": mounts or ["/org"]}, resources=ManifestResources(max_tokens_per_task=tokens),
                             capabilities=ManifestCapabilities(tools=tools or [], agents=agents or []))
    return [m("long-runner", agents=["research-agent"]), m("chatty-agent", tokens=400),
            m("rogue-agent", tools=["jira.read", "sandbox.exec"], mounts=["/org/projects"]), m("resumable-agent")]


# ============================================================================ building the kernel

def build_kernel(data_dir: Path, config: KernelConfig | None = None) -> Kernel:
    from kairos_execution.artifacts.store import FsArtifactStore
    from kairos_execution.connectors.jira import JiraBackend
    from kairos_execution.files.workspace import FsBackend
    from kairos_execution.tools.executor import Executor
    from kairos_execution.tools.sandboxed import BrowserBackend, SandboxExecBackend, SandboxPool

    settings = Settings(data_dir=data_dir, jira_url="inprocess")
    b = fake_bundle(settings)                                   # stand-ins for P2 / P3 / P4
    b.event_bus = KernelEventBus()                              # P1 real
    b.policy = YamlPolicyEngine(REPO_ROOT / "policies", event_bus=b.event_bus)
    b.audit = SqliteAuditLog(data_dir / "audit.db")
    b.artifacts = FsArtifactStore(data_dir / "artifacts")
    b.sandbox, b.browser = FakeSandboxManager(), FakeBrowserDriver()  # browser driver is P4's
    pool = SandboxPool(b)
    b.tools = Executor([JiraBackend("inprocess"), FsBackend(data_dir / "workspaces"), BrowserBackend(b, pool),
                        SandboxExecBackend(b, pool)], event_bus=b.event_bus, on_task_end=pool.release_task)
    b.agent_registry = FakeAgentRegistry(manifests=load_manifests(REPO_ROOT / "agents" / "manifests") + extra_manifests())
    b.agent_runtime = DemoRuntime()
    b.modes = {**b.modes, **{k: "real" for k in ("event_bus", "policy", "audit", "artifacts", "tools")},
               "agent_runtime": "demo-script", "sandbox": "fake (see scene 8)", "browser": "fake (P4)"}
    return Kernel(settings, b, config or KernelConfig(policy_watch_interval_s=0, max_concurrent_tasks=2))


# ============================================================================ event printer

class Narrator:
    """Prints the live event stream of one task as a readable timeline."""

    SKIP = {"process.usage", "audit.appended", "syscall.completed", "tool.started"}

    def __init__(self, k: Kernel, t0: float) -> None:
        self.k, self.t0, self.task_id = k, t0, None

    async def __call__(self, ev: Any) -> None:
        if ev.task_id != self.task_id or ev.type in self.SKIP:
            return
        if ev.type == "process.state_changed" and ev.payload["new"] in ("INITIALIZING", "READY", "RUNNING") \
                and ev.payload["old"] in ("CREATED", "INITIALIZING", "READY"):
            return  # boot-up transitions of every new process: noise in a demo
        p, pid = ev.payload, ev.pid
        proc = self.k.procs.find(pid)
        who = f"[bold]{pid}[/] {proc.agent:<18}" if proc else " " * 23
        text = {
            "task.created": lambda: f"[bold]task created[/] by {p.get('user_id')}",
            "task.status_changed": lambda: f"task status → [bold]{p['new']}[/]",
            "process.spawned": lambda: f"[green]spawned[/] {p['agent']} (parent {p.get('ppid') or '-'})",
            "process.state_changed": lambda: f"{p['old']} → {state(p['new'])}" + (
                f"  [dim]({p['reason'][:50]})[/]" if p.get("reason") and p['new'] in ("FAILED", "TERMINATED", "PAUSED") else ""),
            "agent.log": lambda: f"[{'yellow' if p['level'] == 'warning' else 'white'}]“{p['message'][:90]}”[/]",
            "knowledge.retrieved": lambda: f"knowledge: {p['hits']} hits, [magenta]{p['filtered_by_policy']} hidden by policy[/] "
                                           f"[dim]{', '.join(x.rsplit('/', 1)[-1] for x in p['paths'])}[/]",
            "model.invoked": lambda: f"model {p['model']} ({p['tokens']} tokens, local={p['local']})",
            "ipc.message": lambda: f"IPC {p['type']} → {p['receiver']}",
            "syscall.requested": lambda: f"[cyan]syscall[/] {p['capability']} {p['tool']}.{p['operation']} (risk {p['risk']})",
            "syscall.decided": lambda: f"policy [bold]{p['decision']}[/] by {p['policy']}",
            "approval.requested": lambda: f"[yellow bold]approval required[/] {p['approval_id']}",
            "approval.resolved": lambda: f"approval {p['status']} by {p['resolved_by']}",
            "tool.completed": lambda: f"tool {p['tool']}.{p['operation']} → {p['status']}",
            "transaction.committed": lambda: "[green]transaction committed[/] (post-condition verified)",
            "transaction.rolled_back": lambda: f"[red]rolled back[/]: {p['reason']}",
            "sandbox.started": lambda: f"sandbox {p['sandbox_id']} started",
            "sandbox.screenshot": lambda: f"screenshot saved {p['artifact']}",
            "sandbox.destroyed": lambda: f"sandbox {p['sandbox_id']} destroyed",
            "process.checkpointed": lambda: f"checkpoint {p['checkpoint_id']}",
            "task.completed": lambda: "[bold green]task completed[/]",
            "task.failed": lambda: f"[bold red]task failed[/]: {p.get('reason', '')[:80]}",
        }.get(ev.type)
        if text:
            console.print(f"[dim]{time.monotonic() - self.t0:5.2f}s[/] {who} {text()}")


def ps_table(k: Kernel, task_id: str, title: str) -> Table:
    t = Table(title=title, title_justify="left", header_style="bold")
    for col in ("PID", "PPID", "AGENT", "STATE", "TOKENS", "TOOLS", "WAITING ON"):
        t.add_column(col, no_wrap=True)
    for p in k.procs.list(task_id):
        t.add_row(str(p.pid), str(p.ppid or "-"), p.agent, state(p.state.value), str(p.usage.tokens_total),
                  str(p.usage.tool_calls), p.waiting_on or "")
    return t


def tree(k: Kernel, task_id: str) -> Tree:
    root = Tree(f"task {task_id}")

    def add(node: Tree, n: Any) -> None:
        br = node.add(f"[bold]{n.pid}[/] {n.agent} {state(n.state.value)}")
        for c in n.children:
            add(br, c)

    for n in k.procs.tree(task_id):
        add(root, n)
    return root


# ============================================================================ the show

async def main_demo(interactive: bool, fast: bool) -> None:
    pace = Pace(fast)
    data_dir = Path(tempfile.mkdtemp(prefix="kairos-demo-"))
    t0 = time.monotonic()
    console.print(Panel.fit("[bold]KAIROS · P1 Kernel & Execution demo[/]\n"
                            "Agents are processes · actions are governed syscalls · everything is audited",
                            border_style="cyan"))

    # ---------------------------------------------------------------- 1 boot
    scene(1, "Boot", "The kernel boots on a ServiceBundle; every P1 component is the real implementation.")
    k = build_kernel(data_dir)
    await k.boot()
    t = Table(header_style="bold")
    t.add_column("service")
    t.add_column("implementation")
    t.add_column("mode")
    for c in k.components():
        svc = getattr(k.services, c.component, None)
        impl = type(svc).__name__ if svc is not None else "Kernel"
        t.add_row(c.component, impl, "[green]real[/]" if c.mode == "real" else f"[dim]{c.mode}[/]")
    console.print(t)
    console.print(f"policies loaded: {', '.join(d.policy for d in k.policy.documents())}")
    await pace(1)

    # ---------------------------------------------------------------- 2 input
    scene(2, "Input", "A user submits a goal (POST /tasks · `ai run` · the web console all produce this TaskCreate).")
    body = TaskCreate(goal=GOAL, priority=Priority.HIGH)
    console.print_json(body.model_dump_json(exclude_defaults=False, include={"goal", "priority", "privacy", "data_scope"}))
    console.print("identity from headers → X-Kairos-User: [bold]alice[/], X-Kairos-Org: [bold]acme[/]")
    await pace(1)

    # ---------------------------------------------------------------- 3 processing
    scene(3, "Processing (live event stream)", "Planner spawns specialists; every ctx.* call is checked, charged, evented and audited.")
    narrator = Narrator(k, t0)
    k.bus.subscribe("*", narrator)

    async def on_approval(ev: Any) -> None:
        if ev.task_id != narrator.task_id:
            return
        a = k.approvals.get(ev.payload["approval_id"])
        console.print(Panel(
            f"[bold]{a.agent}#{a.pid}[/] wants [bold]{a.syscall.capability}[/] → {a.syscall.tool}.{a.syscall.operation}"
            f" on {a.syscall.resource}\nrisk: {a.syscall.risk.value} · policy: {a.decision.policy}"
            f" ({a.decision.reason})\narguments: {_short(json.dumps(a.syscall.arguments), 190)}\n"
            f"justification: {a.syscall.justification}\nevidence: {', '.join(a.syscall.evidence)}",
            title=f"APPROVAL CENTER · {a.approval_id}", border_style="yellow"))
        k.spawn_background(decide(a.approval_id, a.task_id))

    async def decide(approval_id: str, task_id: str) -> None:
        await asyncio.sleep(0.1)  # let the requesting process settle into WAITING
        console.print(ps_table(k, task_id, "ai-ps while the kernel waits for a human"))
        console.print(f"task status: [yellow bold]{k.tasks.get(task_id).status.value}[/]")
        if interactive:
            from rich.prompt import Confirm

            ok = await asyncio.to_thread(Confirm.ask, "approve?", default=True)
        else:
            await pace(2)
            ok = True
        await k.approvals.resolve(approval_id, ok, "alice", "looks right" if ok else "not now")

    k.bus.subscribe("approval.requested", on_approval)
    task = await k.tasks.create(body, user_principal())
    narrator.task_id = task.task_id
    before = (await k.services.tools.execute(_inv("jira", "get_issue", key="APOLLO-12"))).output
    done = await k.tasks.wait_terminal(task.task_id, timeout=120)
    await pace(1)

    # ---------------------------------------------------------------- 4 output
    scene(4, "Output", "TaskResult, artifacts, the world change (Jira) and the process tree.")
    console.print(Panel(done.result.summary, title=f"TaskResult · {done.task_id} · {done.status.value}", border_style="green"))
    console.print(f"artifacts: {done.result.artifacts}")
    console.print(f"committed actions: {done.result.actions}")
    console.print(f"usage: {done.result.usage.tokens_total} tokens, {done.result.usage.tool_calls} tool calls")
    plan = (await k.services.artifacts.get(done.result.artifacts[0])).decode()
    console.print(Panel(plan.strip(), title="artifact · recovery-plan.md", border_style="blue"))
    after = (await k.services.tools.execute(_inv("jira", "get_issue", key="APOLLO-12"))).output
    console.print(f"Jira APOLLO-12 status: [red]{before['status']}[/] → [green]{after['status']}[/]; "
                  f"new comment: “{after['comments'][-1][:90]}…”")
    console.print(tree(k, done.task_id))
    await pace(1)

    # ---------------------------------------------------------------- 5 audit
    scene(5, "Audit & provenance", "Every decision is journaled; the per-task hash chain makes tampering detectable.")
    tl = await k.audit.timeline(done.task_id)
    s = tl.stats
    at = Table(title=f"ai-audit {done.task_id} · {s.agents} agents · {s.knowledge_objects} knowledge objects · "
                     f"{s.ipc_messages} IPC · {s.tool_calls} tool calls · {s.privileged_syscalls} privileged · "
                     f"{s.approvals} approval", title_justify="left", header_style="bold")
    for col in ("#", "KIND", "ACTOR", "SUMMARY"):
        at.add_column(col)
    for e in tl.entries:
        if e.kind.value in ("state", "model"):
            continue
        at.add_row(str(e.seq), e.kind.value, e.actor, e.summary if len(e.summary) < 95 else e.summary[:92] + "…")
    console.print(at)
    console.print(f"hash chain verified: [bold green]{k.audit.verify_chain(done.task_id)}[/] "
                  f"({len(tl.entries)} entries, sha256-linked)")
    await pace(1)

    k.bus._subs = [(pat, h) for pat, h in k.bus._subs if h not in (narrator, on_approval)]

    # ---------------------------------------------------------------- 6 governance
    scene(6, "Governance: what the kernel refuses",
          "A rogue agent tries an ungranted write, an unallowed command, and confidential data.")
    rt = await k.tasks.create(TaskCreate(goal="rogue", metadata={"root_agent": "rogue-agent"}), user_principal())
    r = await k.tasks.wait_terminal(rt.task_id)
    root = k.store.result(r.root_pid)
    gt = Table(header_style="bold")
    gt.add_column("attempt")
    gt.add_column("kernel answer")
    for key, val in root.output.items():
        gt.add_row(key, f"[red]{val}[/]")
    console.print(gt)
    await pace(1)

    # ---------------------------------------------------------------- 7 OS controls
    scene(7, "OS controls: pause · resume · kill · quotas",
          "Processes are real: they can be paused mid-run, killed with their children, and stopped by quotas.")
    lt = await k.tasks.create(TaskCreate(goal="long job", metadata={"root_agent": "long-runner"}), user_principal())
    while len(k.procs.list(lt.task_id)) < 2 or k.procs.list(lt.task_id)[1].state != AgentState.COMPLETED:
        await asyncio.sleep(0.02)
    pid = k.tasks.get(lt.task_id).root_pid
    await k.lifecycle.pause(pid)
    console.print(f"ai pause {pid}   → {state(k.procs.get(pid).state.value)}  (task: {k.tasks.get(lt.task_id).status.value})")
    await pace(0.5)
    await k.lifecycle.resume(pid)
    console.print(f"ai resume {pid}  → {state(k.procs.get(pid).state.value)}")
    await asyncio.sleep(0.1)
    await k.lifecycle.kill(pid)
    console.print(f"ai kill {pid}    → {state(k.procs.get(pid).state.value)}  "
                  f"(task: {(await k.tasks.wait_terminal(lt.task_id)).status.value})")
    qt = await k.tasks.create(TaskCreate(goal="talk forever", metadata={"root_agent": "chatty-agent"}), user_principal())
    q = await k.tasks.wait_terminal(qt.task_id)
    console.print(f"chatty agent with a 400-token budget → task {q.status.value}: [red]{q.error.code}[/] "
                  f"({q.error.message})")
    await pace(1)

    # ---------------------------------------------------------------- 8 sandbox
    scene(8, "Execution sandbox (real Docker)", "Commands run in a disposable, locked-down container.")
    await sandbox_scene(data_dir)
    await pace(1)

    # ---------------------------------------------------------------- 9 restart
    scene(9, "Crash-safe: shutdown suspends, boot resumes",
          "The kernel is stopped mid-task; a brand-new kernel on the same data resumes it from its checkpoint.")
    st = await k.tasks.create(TaskCreate(goal="resumable job", metadata={"root_agent": "resumable-agent"}),
                              user_principal())
    while not (k.tasks.get(st.task_id).root_pid and k.store.latest_checkpoint(k.tasks.get(st.task_id).root_pid)):
        await asyncio.sleep(0.02)
    old_pid = k.tasks.get(st.task_id).root_pid
    await k.shutdown()
    console.print(f"kernel #1 stopped while pid {old_pid} was running (task stays [bold]{k.tasks.get(st.task_id).status.value}[/])")
    k2 = build_kernel(data_dir)
    await k2.boot()
    resumed = await k2.tasks.wait_terminal(st.task_id)
    console.print(f"kernel #2 booted → task {resumed.status.value} with new pid {resumed.root_pid}: "
                  f"[green]{resumed.result.summary}[/]")
    await k2.shutdown()

    console.print()
    console.rule("[bold green]Demo complete")
    console.print(f"state, audit log and artifacts are in {data_dir}")


async def sandbox_scene(data_dir: Path) -> None:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        client.images.get("kairos/sandbox-base:latest")
    except Exception:
        console.print("[dim]Docker or the kairos/sandbox-base image is not available — skipping. Build it with:\n"
                      "  docker build -t kairos/sandbox-base:latest execution/images/sandbox-base[/]")
        return
    from kairos_contracts.schema import ExecRequest, NetworkMode, SandboxSpec
    from kairos_execution.sandbox.docker_manager import DockerSandboxManager

    mgr = DockerSandboxManager(data_dir / "workspaces", client=client)
    info = await mgr.provision(SandboxSpec(task_id="T-demo", network=NetworkMode.NONE, memory_mb=256, cpu=0.5))
    checks = [("whoami (uid)", ["id", "-u"]), ("write to /etc", ["sh", "-c", "touch /etc/x 2>&1 || echo DENIED"]),
              ("write to /workspace", ["sh", "-c", "echo ok > /workspace/f && cat /workspace/f"]),
              ("capabilities", ["sh", "-c", "grep CapEff /proc/self/status"]),
              ("internet", ["python", "-c", "import socket\ntry:\n socket.create_connection(('1.1.1.1',53),2);print('OPEN')\n"
                                           "except OSError as e: print('BLOCKED:', e.__class__.__name__)"])]
    t = Table(title=f"sandbox {info.sandbox_id} (kairos/sandbox-base, network none, 256 MB, 0.5 CPU)",
              title_justify="left", header_style="bold")
    t.add_column("check", no_wrap=True)
    t.add_column("result", no_wrap=True, min_width=28)
    try:
        for name, cmd in checks:
            res = await mgr.exec(info.sandbox_id, ExecRequest(command=cmd, timeout_s=20))
            t.add_row(name, (res.stdout or res.stderr).strip().splitlines()[-1][:70])
    finally:
        await mgr.destroy(info.sandbox_id)
    console.print(t)
    console.print(f"sandbox destroyed: container removed = "
                  f"{not client.containers.list(all=True, filters={'label': f'kairos.sandbox={info.sandbox_id}'})}")


def _short(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _inv(tool: str, op: str, **args: Any):
    from kairos_contracts.schema import ToolInvocation

    return ToolInvocation(invocation_id=new_id("INV"), syscall_id=new_id("SC"), task_id="T-demo", pid=1, tool=tool,
                          operation=op, arguments=args)


def main() -> None:
    ap = argparse.ArgumentParser(prog="ai-demo", description="Narrated run-through of the KAIROS kernel (P1)")
    ap.add_argument("--interactive", action="store_true", help="approve or reject the privileged action yourself")
    ap.add_argument("--fast", action="store_true", help="no pauses between scenes")
    args = ap.parse_args()
    asyncio.run(main_demo(args.interactive, args.fast))


if __name__ == "__main__":
    main()

_ = shutil  # kept for callers that want to clean the demo data dir
