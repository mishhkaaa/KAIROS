"""kairos: the KAIROS command line. Run ``kairos help`` for every command."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .client import Kairos, KairosError, _Store

if sys.platform == "win32":
    os.system("")  # turn on ANSI colours in the Windows console
for _stream in (sys.stdout, sys.stderr):
    try:
        # Windows writes pipes in the ANSI code page; UTF-8 is what terminals and tools downstream expect.
        _stream.reconfigure(errors="replace", **({"encoding": "utf-8"} if sys.platform == "win32" and not _stream.isatty() else {}))  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
TEAL, AMBER, RED, GREEN, DIM, BOLD, BLUE, VIOLET = "38;5;30", "38;5;172", "38;5;160", "38;5;35", "2", "1", "38;5;33", "38;5;98"
KIND = {"spawn": BLUE, "model": VIOLET, "knowledge": "38;5;37", "syscall": TEAL, "policy": AMBER, "approval": AMBER,
        "tool": TEAL, "commit": GREEN, "rollback": RED, "memory": VIOLET, "ipc": BLUE, "task": DIM}
STATUS = {"completed": GREEN, "failed": RED, "cancelled": DIM, "waiting_approval": AMBER, "running": TEAL, "planning": BLUE}


def c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if TTY else s


def org_path(p: str) -> str:
    """An /org path from what was typed: `/org/x`, `x`, or what Git Bash makes of `/org/x` (C:/Program Files/Git/org/x)."""
    p = p.replace("\\", "/")
    if p == "/org" or p.startswith("/org/"):
        return p
    m = re.search(r"/org(/.*)?$", p)
    return m.group(0) if m and ":" in p else "/org/" + p.strip("/") if p.strip("/") else "/org"


def out(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


class Exit(Exception):
    pass


def fail(msg: str) -> None:
    print(c(RED, msg), file=sys.stderr)
    raise Exit(1)


# -- commands -----------------------------------------------------------------------------------------------------


def cmd_status(m: Kairos, a: argparse.Namespace) -> None:
    status = m.status()
    try:
        me = m.me()
    except KairosError:
        me = None
    if a.json:
        return out({"status": status, "me": me})
    print(c(BOLD, "KAIROS") + c(DIM, f"  kernel {status.get('version')} · contract {status.get('contract_version')} · {m.url}"))
    if me:
        who = me["user"].get("name") or me["user"]["email"]
        how = "signed in" if m.token else "dev headers"
        print(f"{who} · {c(TEAL, me.get('role') or 'no role')} · {(me.get('org') or {}).get('name', 'no org')}" + c(DIM, f"  ({how})"))
    comps = status.get("components", [])
    ok = sum(1 for x in comps if x.get("ok"))
    real = sum(1 for x in comps if x.get("mode") == "real")
    print(c(GREEN if ok == len(comps) else AMBER, f"{ok}/{len(comps)} components healthy") + c(DIM, f" · {real} real"))
    for x in comps:
        if not x.get("ok") or a.verbose:
            print(f"  {c(GREEN if x.get('ok') else RED, '●')} {x['component']:<16} {c(DIM, x.get('mode', ''))} {x.get('detail', '')}")


def cmd_connect(m: Kairos, a: argparse.Namespace) -> None:
    url = a.url_to_save.rstrip("/")
    probe = Kairos(url, remember=False)
    if not probe.health():
        fail(f"no KAIROS gateway answers at {url}/health")
    _Store().set_url(url)
    print(c(GREEN, f"connected: {url}") + c(DIM, "  (saved as the default gateway)"))


def cmd_login(m: Kairos, a: argparse.Namespace) -> None:
    if a.as_email:
        s = m.login_dev(a.as_email)
    else:
        code = a.code or input("Code from the console (your name in the menu bar > Sign in on your phone): ")
        s = m.login_code(code)
    me = s["me"]
    print(c(GREEN, f"signed in as {me['user']['email']}") + f" · {me.get('role') or 'no role'} of {(me.get('org') or {}).get('name', 'no org')}")


def cmd_logout(m: Kairos, a: argparse.Namespace) -> None:
    m.logout()
    print("signed out")


def cmd_whoami(m: Kairos, a: argparse.Namespace) -> None:
    me = m.me()
    if a.json:
        return out(me)
    print(f"{me['user']['email']} · {me.get('role')} · {(me.get('org') or {}).get('name')}")
    print(c(DIM, "can: " + ", ".join(me.get("permissions") or [])))


def _entry(e: dict[str, Any]) -> str:
    return f"  {c(KIND.get(e.get('kind', ''), DIM), '●')} {e.get('summary', '')}  {c(DIM, e.get('actor', ''))}"


def _print_result(t: dict[str, Any]) -> None:
    print(c(STATUS.get(t.get("status", ""), DIM), f"  {t.get('status')}"))
    res = t.get("result") or {}
    if res.get("summary"):
        print("\n" + re.sub(r"\*\*", "", res["summary"]))
    if res.get("evidence"):
        print(c(DIM, "\n  evidence: ") + ", ".join(res["evidence"][:8]) + (c(DIM, f" (+{len(res['evidence']) - 8})") if len(res["evidence"]) > 8 else ""))
    if t.get("error"):
        print(c(RED, f"  {t['error']}"))


def cmd_ask(m: Kairos, a: argparse.Namespace) -> None:
    goal = " ".join(a.goal)
    t = m.create_task(goal, priority=a.priority)
    tid = t["task_id"]
    if a.no_wait:
        return out(t) if a.json else print(tid)
    print(c(BOLD, tid) + c(DIM, f"  {goal}"))

    def on_entry(e: dict[str, Any]) -> None:
        if e.get("kind") not in ("state", "verify"):
            print(_entry(e))

    def on_approval(ap: dict[str, Any]) -> None:
        sc = ap["syscall"]
        print(c(AMBER, f"  || {ap['agent']} wants {sc['capability']} ({sc.get('risk', 'medium')} risk): {ap['approval_id']}"))
        print(c(DIM, f"     decide: kairos approve {ap['approval_id']}   (or in the console, or on the phone)"))

    try:
        t = m.wait(tid, on_entry=on_entry, on_approval=on_approval)
    except KeyboardInterrupt:
        print(c(DIM, f"\n  left it running: kairos task {tid}"))
        return
    if a.json:
        return out(t)
    _print_result(t)


def cmd_tasks(m: Kairos, a: argparse.Namespace) -> None:
    rows = m.tasks(a.status)[: a.limit]
    if a.json:
        return out(rows)
    for t in rows:
        st = t.get("status", "")
        print(f"{c(DIM, t['task_id'])}  {c(STATUS.get(st, DIM), f'{st:<17}')}{t['goal'][:90]}")


def cmd_task(m: Kairos, a: argparse.Namespace) -> None:
    t = m.task(a.task_id)
    if a.json:
        return out(t)
    print(c(BOLD, t["task_id"]) + c(DIM, f"  {t['goal']}"))
    _print_result(t)


def cmd_audit(m: Kairos, a: argparse.Namespace) -> None:
    j = m.audit(a.task_id)
    if a.json:
        return out(j)
    for e in j.get("entries", []):
        print(_entry(e))
    verified = j.get("chain_verified")
    print(c(GREEN if verified else RED, f"  chain_verified: {verified}"))


def cmd_ps(m: Kairos, a: argparse.Namespace) -> None:
    rows = m.agents(a.task)
    if a.json:
        return out(rows)
    print(c(DIM, f"{'PID':>6}  {'STATE':<13} {'TASK':<14} AGENT"))
    for p in rows[-a.limit:]:
        state = p.get("state", "")
        colour = GREEN if state == "RUNNING" else AMBER if state == "WAITING" else DIM
        print(f"{p['pid']:>6}  {c(colour, f'{state:<13}')} {p.get('task_id', ''):<14} {p.get('agent', '')}")


def cmd_approvals(m: Kairos, a: argparse.Namespace) -> None:
    rows = m.approvals(a.status)
    if a.json:
        return out(rows)
    if not rows:
        print("nothing is waiting")
    for ap in rows:
        sc = ap["syscall"]
        print(f"{c(AMBER, ap['approval_id'])}  {ap['agent']} wants {c(BOLD, sc['capability'])} · {sc.get('risk', 'medium')} risk · {ap['task_id']}")
        if sc.get("justification"):
            print(c(DIM, f"    {sc['justification'][:160]}"))


def cmd_decide(m: Kairos, a: argparse.Namespace) -> None:
    fn = m.approve if a.command == "approve" else m.reject
    res = fn(a.approval_id, a.comment)
    print(c(GREEN if a.command == "approve" else AMBER, f"{res['approval_id']} {res['status']}"))


def cmd_search(m: Kairos, a: argparse.Namespace) -> None:
    res = m.search(" ".join(a.words), top_k=a.top_k)
    if a.json:
        return out(res)
    for h in res.get("hits", []):
        flag = c(RED, "  [untrusted: firewall]") if h.get("firewall_flags") else ""
        score = c(TEAL, format(float(h["score"]), ".2f"))
        print(f"{score}  {c(BOLD, h['title'])}{flag}\n      {c(DIM, h['path'])}  {h.get('snippet', '')[:120]}")


def cmd_read(m: Kairos, a: argparse.Namespace) -> None:
    obj = m.read(org_path(a.path))
    if a.json:
        return out(obj)
    fm = {k: v for k, v in (obj.get("frontmatter") or {}).items() if v not in (None, [], "")}
    print(c(DIM, "---"))
    for k, v in fm.items():
        print(c(DIM, f"{k}: {v}"))
    print(c(DIM, "---"))
    print(obj.get("body") or "")


def cmd_ls(m: Kairos, a: argparse.Namespace) -> None:
    res = m.tree(org_path(a.path))
    if a.json:
        return out(res)
    items = res if isinstance(res, list) else res.get("entries") or []
    for x in items:
        name = x.get("path", "").rsplit("/", 1)[-1]
        label = c(BLUE, name + "/") if x.get("is_dir") else name
        print(f"{label:<44} {c(DIM, x.get('title') or '')}")


def cmd_memory(m: Kairos, a: argparse.Namespace) -> None:
    rows = m.memory(a.owner, a.task)
    if a.json:
        return out(rows)
    for r in rows[-a.limit:]:
        state = c(AMBER, "stale") if r.get("stale") else c(GREEN, "fresh")
        print(f"{state}  {c(DIM, r.get('owner', ''))}  {str(r.get('summary') or r.get('content') or '')[:110]}")
        if a.verbose:
            print(c(DIM, "        from: " + ", ".join(r.get("derived_from") or [])))


def cmd_upload(m: Kairos, a: argparse.Namespace) -> None:
    for f in a.files:
        if not Path(f).is_file():
            fail(f"no such file: {f}")
    res = m.upload(a.files, org_path(a.to))
    for p in res.get("created", []) + res.get("updated", []):
        print(c(GREEN, "added ") + p)
    for s in res.get("skipped", []) + res.get("errors", []):
        print(c(AMBER, "skipped ") + str(s))


def cmd_mount(m: Kairos, a: argparse.Namespace) -> None:
    name = a.name or re.sub(r"[^a-z0-9-]+", "-", Path(a.folder).name.lower()).strip("-") or "folder"
    mnt = m.mount(a.folder, name)
    print(c(GREEN, f"{a.folder} -> {mnt['org_path']}") + f"  {mnt.get('files', 0)} files, watched")


def cmd_mounts(m: Kairos, a: argparse.Namespace) -> None:
    rows = m.mounts()
    if a.json:
        return out(rows)
    for x in rows:
        print(f"{c(TEAL, x['org_path']):<40} {x['host_path']}  {c(DIM, str(x.get('files', 0)) + ' files')}{c(GREEN, ' watching') if x.get('watching') else ''}")


def cmd_unmount(m: Kairos, a: argparse.Namespace) -> None:
    m.unmount(a.name)
    print("unmounted (the folder itself is untouched)")


def cmd_config(m: Kairos, a: argparse.Namespace) -> None:
    out(m.config())


def cmd_kill(m: Kairos, a: argparse.Namespace) -> None:
    out(getattr(m, {"kill": "kill", "pause": "pause", "resume": "resume_agent"}[a.command])(a.pid))


def cmd_cancel(m: Kairos, a: argparse.Namespace) -> None:
    t = m.cancel(a.task_id)
    print(f"{t['task_id']} {t.get('status')}")


# -- parser -------------------------------------------------------------------------------------------------------

EPILOG = """examples:
  kairos connect https://your-gateway.example      save the gateway to use
  kairos login --as priya@acme.example             dev sign-in (demo: alice owner, priya approver, sam viewer)
  kairos ask "Why is Project Apollo over budget?"  start a task and watch it run
  kairos approvals ; kairos approve APR-...        decide on what waits for a person
  kairos search apollo budget variance             hybrid search over /org

environment: KAIROS_URL, KAIROS_TOKEN, KAIROS_USER, KAIROS_ORG, KAIROS_CONFIG_DIR, NO_COLOR"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kairos", description="The KAIROS command line: governed AI agents on your own machine.",
                                epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", help="gateway URL (default: $KAIROS_URL, the saved one, or http://localhost:8089)")
    p.add_argument("--json", action="store_true", help="print raw JSON")
    p.add_argument("-V", "--version", action="version", version=f"kairos-os {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    common = argparse.ArgumentParser(add_help=False)  # so `kairos tasks --json` works as well as `kairos --json tasks`
    common.add_argument("--url", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="print raw JSON")

    def add(name: str, fn, help: str, aliases: tuple[str, ...] = ()) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help, aliases=list(aliases), description=help, parents=[common])
        sp.set_defaults(fn=fn)
        return sp

    s = add("status", cmd_status, "who you are and the state of the system")
    s.add_argument("-v", "--verbose", action="store_true", help="list every component")
    add("connect", cmd_connect, "save the gateway URL to use by default").add_argument("url_to_save", metavar="URL")
    s = add("login", cmd_login, "sign in with a console code, or --as EMAIL in dev mode")
    s.add_argument("code", nargs="?")
    s.add_argument("--as", dest="as_email", metavar="EMAIL")
    add("logout", cmd_logout, "sign out of this gateway")
    add("whoami", cmd_whoami, "your user, org, role and permissions")
    s = add("ask", cmd_ask, "start a task and watch it run, step by step")
    s.add_argument("goal", nargs="+")
    s.add_argument("--priority", default="normal", choices=["low", "normal", "high", "critical"])
    s.add_argument("--no-wait", action="store_true", help="print the task id and return")
    s = add("tasks", cmd_tasks, "recent tasks")
    s.add_argument("--status")
    s.add_argument("-n", "--limit", type=int, default=15)
    add("task", cmd_task, "one task and its result").add_argument("task_id")
    add("cancel", cmd_cancel, "cancel a task").add_argument("task_id")
    add("audit", cmd_audit, "a task's hash-chained journal").add_argument("task_id")
    s = add("ps", cmd_ps, "the agent process table")
    s.add_argument("--task")
    s.add_argument("-n", "--limit", type=int, default=40)
    for verb in ("pause", "resume", "kill"):
        add(verb, cmd_kill, f"{verb} an agent process").add_argument("pid", type=int)
    add("approvals", cmd_approvals, "what is waiting for a person").add_argument("--status", default="pending")
    for verb in ("approve", "reject"):
        s = add(verb, cmd_decide, f"{verb} a pending action")
        s.add_argument("approval_id")
        s.add_argument("-m", "--comment")
    s = add("search", cmd_search, "hybrid search over /org")
    s.add_argument("words", nargs="+")
    s.add_argument("-k", "--top-k", type=int, default=8)
    add("read", cmd_read, "print an /org document with its frontmatter", ("cat",)).add_argument("path")
    add("ls", cmd_ls, "list an /org folder").add_argument("path", nargs="?", default="/org")
    s = add("memory", cmd_memory, "what agents remember, fresh or stale")
    s.add_argument("--owner")
    s.add_argument("--task")
    s.add_argument("-n", "--limit", type=int, default=30)
    s.add_argument("-v", "--verbose", action="store_true", help="show the sources each memory was derived from")
    s = add("upload", cmd_upload, "add files to /org")
    s.add_argument("files", nargs="+")
    s.add_argument("--to", default="/org/uploads")
    s = add("mount", cmd_mount, "mirror a folder of the gateway's machine into /org/mnt/NAME (watched)")
    s.add_argument("folder")
    s.add_argument("name", nargs="?")
    add("mounts", cmd_mounts, "mounted folders")
    add("unmount", cmd_unmount, "stop mirroring a folder").add_argument("name")
    add("config", cmd_config, "the whole running system as JSON (secrets redacted)")
    add("help", lambda m, a: p.print_help(), "show this help")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "fn", None):
        args.fn, args.verbose = cmd_status, False
    m = Kairos(args.url)
    try:
        args.fn(m, args)
    except Exit as e:
        return int(str(e) or 1)
    except KairosError as e:
        if e.status == 401:
            print(c(RED, e.message) + "\n  sign in: kairos login <code from the console>", file=sys.stderr)
        elif e.status == 0:
            print(c(RED, e.message) + c(DIM, "\n  set the gateway: kairos connect <url>, --url, or $KAIROS_URL"), file=sys.stderr)
        else:
            print(c(RED, f"{e.code}: {e.message}"), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
