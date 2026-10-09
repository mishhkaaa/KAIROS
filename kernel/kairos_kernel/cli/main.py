"""ai-* commands (blueprint §47): an HTTP/WebSocket client of the gateway. Works against the mock gateway too.

    ai-ps [--task T-…] [--all]     process table            ai-tree [--task T-…]   delegation tree
    ai-top [--once]                live resources + pids    ai-kill <pid>          terminate a process (+ children)
    ai-audit <task>                provenance timeline       ai-checkpoint <pid>    ai-resume <pid>
    ai-mount [/org/path]           browse the knowledge FS  ai run "<goal>"        submit + stream a task
    ai approve|reject <APR-…>      resolve an approval       ai tasks               recent tasks

KAIROS_URL (default http://localhost:8080) selects the gateway; KAIROS_TOKEN (a session) or, in dev mode,
KAIROS_USER / KAIROS_ORG the identity.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.tree import Tree

for _stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; our output uses → · etc.
    if (getattr(_stream, "encoding", "") or "").lower().replace("-", "") != "utf8" and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass

app = typer.Typer(help="KAIROS process & knowledge CLI", no_args_is_help=True, add_completion=False)
console = Console()

URL = os.getenv("KAIROS_URL", "http://localhost:8080").rstrip("/")
# A session token (KAIROS_TOKEN, e.g. from a sign-in code) wins; otherwise the dev headers, which only dev mode accepts.
HEADERS = ({"Authorization": f"Bearer {os.environ['KAIROS_TOKEN']}"} if os.getenv("KAIROS_TOKEN")
           else {"X-Kairos-User": os.getenv("KAIROS_USER", "alice"), "X-Kairos-Org": os.getenv("KAIROS_ORG", "acme")})
STATE_STYLE = {"RUNNING": "green", "WAITING": "yellow", "PAUSED": "blue", "FAILED": "red", "RETRYING": "magenta",
               "COMPLETED": "dim", "TERMINATED": "dim red", "CHECKPOINTING": "cyan"}


def _call(method: str, path: str, **kw: Any) -> Any:
    try:
        r = httpx.request(method, f"{URL}{path}", headers=HEADERS, timeout=15, **kw)
    except httpx.HTTPError as e:
        console.print(f"[red]cannot reach KAIROS gateway at {URL}: {e}[/red]")
        raise typer.Exit(2) from e
    if r.status_code >= 400:
        try:
            err = r.json()
            console.print(f"[red]{err.get('code', r.status_code)}: {err.get('message', err)}[/red]")
        except ValueError:
            console.print(f"[red]HTTP {r.status_code}: {r.text[:200]}[/red]")
        raise typer.Exit(1)
    return r.json()


def _state(s: str) -> str:
    return f"[{STATE_STYLE.get(s, 'white')}]{s}[/]"


def _latest_task_id() -> str | None:
    tasks = _call("GET", "/tasks")
    return tasks[-1]["task_id"] if tasks else None


def _tokens(usage: dict) -> str:
    n = usage.get("tokens_prompt", 0) + usage.get("tokens_completion", 0)
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def _process_table(procs: list[dict], title: str) -> Table:
    t = Table(title=title, header_style="bold", title_justify="left")
    for col, width in (("PID", 4), ("PPID", 4), ("AGENT", 12), ("STATE", 9), ("TOKENS", 6), ("TOOLS", 5), ("MODEL", 8),
                       ("WAITING ON", 10), ("TASK", 12)):
        t.add_column(col, no_wrap=True, min_width=width)
    for p in procs:
        u = p.get("usage", {})
        t.add_row(str(p["pid"]), str(p.get("ppid") or "-"), p["agent"], _state(p["state"]), _tokens(u),
                  str(u.get("tool_calls", 0)), p.get("model") or "-", p.get("waiting_on") or "", p["task_id"])
    return t


# ---------------------------------------------------------------------------------------------- commands

@app.command("ps")
def ps_cmd(task: str | None = typer.Option(None, "--task", "-t", help="task id (default: latest task)"),
           all_: bool = typer.Option(False, "--all", "-a", help="every process of every task")) -> None:
    """Process table: PID, agent, state, tokens, tool calls."""
    task_id = None if all_ else task or _latest_task_id()
    procs = _call("GET", "/agents", params={"task_id": task_id} if task_id else {})
    console.print(_process_table(procs, f"processes · {task_id or 'all tasks'}"))


@app.command("tree")
def tree_cmd(task: str | None = typer.Option(None, "--task", "-t")) -> None:
    """Agent delegation tree."""
    task_id = task or _latest_task_id()
    roots = _call("GET", "/agents/tree", params={"task_id": task_id} if task_id else {})

    def add(node: Tree, n: dict) -> None:
        branch = node.add(f"[bold]{n['pid']}[/] {n['agent']} {_state(n['state'])}")
        for c in n.get("children", []):
            add(branch, c)

    root = Tree(f"task {task_id}")
    for n in roots:
        add(root, n)
    console.print(root)


@app.command("top")
def top_cmd(once: bool = typer.Option(False, "--once", help="print one snapshot and exit"),
            interval: float = typer.Option(2.0, "--interval", "-n")) -> None:
    """Live resources (CPU/RAM/GPU/tokens) + running processes."""

    def render() -> Table:
        r = _call("GET", "/system/resources")
        procs = [p for p in _call("GET", "/agents") if p["state"] not in ("COMPLETED", "TERMINATED")]
        gpu = r.get("gpu")
        g = (f"GPU {gpu['name']} {gpu['utilization'] * 100:.0f}% · {gpu['memory_used_mb']}/{gpu['memory_total_mb']} MB"
             if gpu else "GPU n/a")
        title = (f"CPU {r['cpu_percent']:.0f}% · RAM {r['ram_used_mb']}/{r['ram_total_mb']} MB · {g} · "
                 f"{r['running_processes']} running · {r['queued_tasks']} queued · {r['active_sandboxes']} sandboxes · "
                 f"{r['tokens_last_minute']} tok/min")
        return _process_table(procs, title)

    if once:
        console.print(render())
        return
    with Live(render(), console=console, refresh_per_second=4) as live:
        try:
            while True:
                time.sleep(interval)
                live.update(render())
        except KeyboardInterrupt:
            pass


@app.command("kill")
def kill_cmd(pid: int) -> None:
    """Terminate a process and its children."""
    p = _call("POST", f"/agents/{pid}/kill")
    console.print(f"{pid} {p['agent']} → {_state(p['state'])}")


@app.command("checkpoint")
def checkpoint_cmd(pid: int) -> None:
    """Checkpoint a running process."""
    c = _call("POST", f"/agents/{pid}/checkpoint")
    console.print(f"checkpoint [bold]{c['checkpoint_id']}[/] for pid {pid}")


@app.command("pause")
def pause_cmd(pid: int) -> None:
    """Pause a process at its next kernel call."""
    p = _call("POST", f"/agents/{pid}/pause")
    console.print(f"{pid} {p['agent']} → {_state(p['state'])}")


@app.command("resume")
def resume_cmd(pid: int) -> None:
    """Resume a paused process."""
    p = _call("POST", f"/agents/{pid}/resume")
    console.print(f"{pid} {p['agent']} → {_state(p['state'])}")


@app.command("audit")
def audit_cmd(task_id: str) -> None:
    """Provenance timeline of a task."""
    tl = _call("GET", f"/audit/{task_id}")
    s = tl["stats"]
    t = Table(title=f"RUN {task_id} · {s['agents']} agents · {s['knowledge_objects']} knowledge objects · "
                    f"{s['ipc_messages']} IPC · {s['tool_calls']} tool calls · {s['privileged_syscalls']} privileged syscalls · "
                    f"{s['approvals']} approvals · {s['rollbacks']} rollbacks", title_justify="left", header_style="bold")
    for col in ("#", "TIME", "KIND", "ACTOR", "SUMMARY"):
        t.add_column(col)
    for e in tl["entries"]:
        if e["kind"] == "state":
            continue
        t.add_row(str(e["seq"]), e["ts"][11:19], e["kind"], e["actor"], e["summary"])
    console.print(f"[bold]goal:[/] {tl['goal']}")
    console.print(t)


@app.command("mount")
def mount_cmd(path: str = typer.Argument("/org")) -> None:
    """Browse the knowledge filesystem (lists a directory, or prints an object)."""
    if "/org" in path and not path.startswith("/org"):  # Git Bash on Windows rewrites /org/... into C:/.../org/...
        path = path[path.index("/org"):]
    try:
        listing = httpx.get(f"{URL}/knowledge/tree", params={"path": path}, headers=HEADERS, timeout=15)
    except httpx.HTTPError as e:
        console.print(f"[red]cannot reach KAIROS gateway at {URL}: {e}[/red]")
        raise typer.Exit(2) from e
    if listing.status_code == 200 and listing.json()["entries"]:
        t = Table(title=path, title_justify="left", header_style="bold")
        for col in ("PATH", "TYPE", "TITLE", "PRIVACY"):
            t.add_column(col)
        for e in listing.json()["entries"]:
            name = e["path"] + ("/" if e["is_dir"] else "")
            t.add_row(name, e["type"], e["title"], e["privacy"])
        console.print(t)
        return
    obj = _call("GET", "/knowledge/object", params={"path": path})
    fm = obj["frontmatter"]
    console.print(f"[bold]{fm['title']}[/]  ({fm['type']}, {fm.get('privacy')}, trust={fm.get('trust')}, "
                  f"source={obj['provenance']['source']})")
    console.print(obj["body"])


@app.command("tasks")
def tasks_cmd() -> None:
    """Recent tasks."""
    t = Table(header_style="bold")
    for col in ("TASK", "STATUS", "ROOT PID", "GOAL"):
        t.add_column(col)
    for task in _call("GET", "/tasks")[-20:]:
        t.add_row(task["task_id"], task["status"], str(task.get("root_pid") or "-"), task["goal"][:80])
    console.print(t)


@app.command("approve")
def approve_cmd(approval_id: str, comment: str = typer.Option("", "--comment", "-m")) -> None:
    a = _call("POST", f"/approvals/{approval_id}/approve", json={"comment": comment or None})
    console.print(f"{approval_id} → [green]{a['status']}[/]")


@app.command("reject")
def reject_cmd(approval_id: str, comment: str = typer.Option("", "--comment", "-m")) -> None:
    a = _call("POST", f"/approvals/{approval_id}/reject", json={"comment": comment or None})
    console.print(f"{approval_id} → [red]{a['status']}[/]")


@app.command("run")
def run_cmd(goal: str, auto_approve: bool = typer.Option(False, "--yes", "-y", help="approve every privileged syscall")) -> None:
    """Submit a goal and stream the run live (approvals are prompted interactively unless --yes)."""
    task = _call("POST", "/tasks", json={"goal": goal})
    console.print(f"task [bold]{task['task_id']}[/] submitted")
    asyncio.run(_stream(task["task_id"], auto_approve))


async def _stream(task_id: str, auto_approve: bool) -> None:
    import websockets

    token = f"&token={os.environ['KAIROS_TOKEN']}" if os.getenv("KAIROS_TOKEN") else ""
    ws_url = URL.replace("http", "ws", 1) + f"/ws/events?task_id={task_id}{token}"
    async with websockets.connect(ws_url) as ws:
        async for raw in ws:
            ev = json.loads(raw)
            _print_event(ev)
            if ev["type"] == "approval.requested":
                aid = ev["payload"]["approval_id"]
                ok = auto_approve or await asyncio.to_thread(typer.confirm, f"approve {aid}?", default=True)
                _call("POST", f"/approvals/{aid}/{'approve' if ok else 'reject'}", json={"comment": "via ai run"})
            if ev["type"] in ("task.completed", "task.failed"):
                break
    final = _call("GET", f"/tasks/{task_id}")
    if final.get("result"):
        console.rule("result")
        console.print(final["result"]["summary"])


def _print_event(ev: dict) -> None:
    p, pid = ev.get("payload", {}), ev.get("pid")
    who = f"[bold]{pid}[/] " if pid else ""
    detail = {
        "process.spawned": lambda: f"spawned {p.get('agent')}",
        "process.state_changed": lambda: f"{p.get('old')} → {_state(p.get('new', ''))}",
        "agent.log": lambda: f"[{'yellow' if p.get('level') == 'warning' else 'white'}]{p.get('message')}[/]",
        "knowledge.retrieved": lambda: f"retrieved {p.get('hits')} ({p.get('filtered_by_policy')} hidden by policy)",
        "model.invoked": lambda: f"{p.get('model')} · {p.get('tokens')} tokens",
        "syscall.decided": lambda: f"{p.get('decision')} ({p.get('policy')})",
        "approval.requested": lambda: f"[yellow]approval needed: {p.get('capability')} ({p.get('approval_id')})[/]",
    }.get(ev["type"], lambda: json.dumps(p)[:120] if p else "")()
    console.print(f"[dim]{ev['ts'][11:19]}[/] {who}[cyan]{ev['type']}[/] {detail}")


# ------------------------------------------------------------------ single-command entry points (ai-ps, ai-tree, …)

def _single(cmd):
    def entry() -> None:
        typer.run(cmd)

    return entry


ps, tree, top, kill = _single(ps_cmd), _single(tree_cmd), _single(top_cmd), _single(kill_cmd)
audit, checkpoint, resume, mount = _single(audit_cmd), _single(checkpoint_cmd), _single(resume_cmd), _single(mount_cmd)
