"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useClient } from "@/app/providers";
import { Orb } from "@/components/desktop/orb";
import { columns, commonPrefix, resolvePath, splitArgs } from "@/lib/desktop/shell";
import { KairosError } from "@/lib/kairos-client";
import { cn } from "@/lib/utils";

type Line = { kind: "in" | "out" | "err" | "dim" | "ok"; text: string };

const HELP = [
  "ai-ps [task]          processes (PID, parent, agent, state)",
  "ai-top                CPU, RAM, GPU, tokens in the last minute",
  "ai-run <goal>         start a task (quote the goal)",
  "ai-approvals          approvals waiting for a human",
  "ai-approve <id>       approve (ai-reject <id> to refuse)",
  "ai-kill <pid>         kill a process",
  "ai-audit <task>       the task's journal and hash-chain verdict",
  "ls [path]  cd <path>  pwd  cat <path>      browse /org",
  "search <text>         hybrid search across /org",
  "mem [agent]           memories and where they came from",
  "models  uname  whoami  open <task|path>  clear",
];

/** A shell over the kernel's API: the `ai-*` tools, plus /org as a filesystem. */
export function TerminalApp() {
  const client = useClient();
  const router = useRouter();
  const [lines, setLines] = useState<Line[]>([
    { kind: "dim", text: "KAIROS terminal. Type help for the commands; Tab completes /org paths." },
  ]);
  const [cwd, setCwd] = useState("/org");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const history = useRef<string[]>([]);
  const hpos = useRef(0);
  const end = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLInputElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [lines]);

  const print = (kind: Line["kind"], ...text: string[]) => setLines((l) => [...l, ...text.map((t) => ({ kind, text: t }))]);

  async function run(line: string) {
    const [cmd, ...args] = splitArgs(line);
    const path = resolvePath(cwd, args[0]);
    switch (cmd) {
      case undefined:
        return;
      case "help":
        return print("out", ...HELP);
      case "clear":
        return setLines([]);
      case "whoami":
        return print("out", "alice (org acme)");
      case "pwd":
        return print("out", cwd);
      case "uname": {
        const s = await client.status();
        return print("out", `KAIROS kernel ${s.version} · contract ${s.contract_version} · ${s.ready ? "ready" : "starting"}`);
      }
      case "ai-ps": {
        const ps = await client.listProcesses(args[0]);
        if (!ps.length) return print("dim", "no processes");
        return print("out", ...columns([["PID", "PPID", "AGENT", "STATE", "TASK"], ...ps.slice(-40).map((p) => [p.pid, p.ppid ?? "-", p.agent, p.state ?? "-", p.task_id ?? "-"])]));
      }
      case "ai-top": {
        const r = await client.resources();
        const g = r.gpu;
        return print(
          "out",
          `cpu ${r.cpu_percent.toFixed(0)}%   ram ${(r.ram_used_mb / 1024).toFixed(1)}/${(r.ram_total_mb / 1024).toFixed(0)} GB`,
          g ? `gpu ${g.utilization.toFixed(0)}%   vram ${(g.memory_used_mb / 1024).toFixed(1)}/${(g.memory_total_mb / 1024).toFixed(0)} GB   ${g.name}` : "gpu not reported",
          `processes ${r.running_processes ?? 0}   queued ${r.queued_tasks ?? 0}   sandboxes ${r.active_sandboxes ?? 0}   tokens/min ${r.tokens_last_minute ?? 0}`,
        );
      }
      case "ai-run": {
        const goal = args.join(" ").trim();
        if (!goal) return print("err", 'usage: ai-run "<goal>"');
        const t = await client.createTask({ goal, priority: "high" });
        print("ok", `started ${t.task_id} (${t.status})`);
        return print("dim", `open ${t.task_id} to watch it`);
      }
      case "ai-approvals": {
        const a = await client.approvals("pending");
        if (!a.length) return print("dim", "nothing is waiting");
        return print("out", ...columns([["ID", "TASK", "AGENT", "CAPABILITY", "RISK"], ...a.map((x) => [x.approval_id, x.task_id, `${x.agent}#${x.pid}`, x.syscall.capability, x.syscall.risk ?? "-"])]));
      }
      case "ai-approve":
      case "ai-reject": {
        if (!args[0]) return print("err", `usage: ${cmd} <approval id>`);
        const a = cmd === "ai-approve" ? await client.approve(args[0], "approved from the terminal") : await client.reject(args[0], "rejected from the terminal");
        return print("ok", `${a.approval_id} ${a.status}`);
      }
      case "ai-kill": {
        const pid = Number(args[0]);
        if (!pid) return print("err", "usage: ai-kill <pid>");
        const p = await client.killProcess(pid);
        return print("ok", `${p.agent}#${p.pid} ${p.state}`);
      }
      case "ai-audit": {
        if (!args[0]) return print("err", "usage: ai-audit <task id>");
        const t = await client.audit(args[0]);
        const kinds = t.entries.reduce<Record<string, number>>((m, e) => ({ ...m, [e.kind]: (m[e.kind] ?? 0) + 1 }), {});
        print("out", `${t.entries.length} entries   ${Object.entries(kinds).map(([k, n]) => `${k} ${n}`).join("   ")}`);
        return print(t.chain_verified === false ? "err" : "ok", t.chain_verified === false ? "hash chain BROKEN" : "hash chain verified");
      }
      case "ls": {
        const l = await client.tree(path);
        return print("out", ...l.entries.map((e) => (e.is_dir ? `${e.path.split("/").pop()}/` : `${e.path.split("/").pop()}`.padEnd(34) + (e.title ? `  ${e.title}` : ""))));
      }
      case "cd": {
        const l = await client.tree(path);
        if (!l) return print("err", `cd: ${path}: not a folder`);
        return setCwd(path);
      }
      case "cat": {
        if (!args[0]) return print("err", "usage: cat <path>");
        const o = await client.object(path);
        const fm = o.frontmatter as Record<string, unknown> | undefined;
        print("dim", `# ${o.path} · trust ${String(fm?.trust ?? "?")} · ${o.version ?? ""}`.trim());
        return print("out", ...(o.body ?? "").split("\n").slice(0, 80));
      }
      case "search":
      case "grep": {
        const q = args.join(" ");
        if (!q) return print("err", `usage: ${cmd} <text>`);
        const ev = await client.search(q, 8);
        return print(
          "out",
          ...ev.hits.map((h) => `${h.score.toFixed(3)}  ${h.path}${h.firewall_flags?.includes("instruction_like") ? "   [firewall: treated as data]" : ""}`),
        );
      }
      case "mem": {
        const m = await client.memory({ owner: args[0] });
        if (!m.length) return print("dim", "no memories");
        return print(
          "out",
          ...m.slice(0, 20).flatMap((x) => [`${x.memory_id}  ${x.owner}${x.stale ? "  [stale]" : ""}  ${(x.summary || x.content).slice(0, 90)}`, `    from ${(x.derived_from ?? []).slice(0, 4).join(", ")}`]),
        );
      }
      case "models": {
        const ms = await client.models();
        return print("out", ...columns([["MODEL", "PROVIDER", "LOCAL", "CAPABILITIES"], ...ms.map((m) => [m.name, m.provider, m.local === false ? "no" : "yes", (m.capabilities ?? []).join(",")])]));
      }
      case "open": {
        const t = args[0];
        if (!t) return print("err", "usage: open <task id | /org path>");
        router.push(t.startsWith("T-") ? `/tasks/${t}` : `/knowledge?path=${encodeURIComponent(resolvePath(cwd, t))}`);
        return;
      }
      default:
        return print("err", `${cmd}: command not found (try help)`);
    }
  }

  async function submit() {
    const line = input;
    setInput("");
    print("in", `${cwd}$ ${line}`);
    if (line.trim()) history.current.push(line);
    hpos.current = history.current.length;
    setBusy(true);
    try {
      await run(line.trim());
    } catch (e) {
      print("err", e instanceof KairosError ? e.message : String(e));
    } finally {
      setBusy(false);
      field.current?.focus();
    }
  }

  async function complete() {
    const words = input.split(" ");
    const last = words.at(-1) ?? "";
    const dir = last.includes("/") ? last.slice(0, last.lastIndexOf("/") + 1) : "";
    try {
      const listing = await client.tree(resolvePath(cwd, dir || "."));
      const names = listing.entries.map((e) => `${e.path.split("/").pop()}${e.is_dir ? "/" : ""}`).filter((n) => n.startsWith(last.slice(dir.length)));
      const pre = commonPrefix(names);
      if (pre) setInput([...words.slice(0, -1), dir + pre].join(" "));
      if (names.length > 1) print("dim", names.join("   "));
    } catch {
      /* nothing to complete */
    }
  }

  return (
    <div className="-m-4 flex h-[calc(100%+2rem)] flex-col bg-[#fbfcfe] dark:bg-[#0d1117] font-mono text-[13px] leading-relaxed text-[#1f2933] dark:text-[#d6dde6]" onClick={() => field.current?.focus()}>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3" role="log" aria-live="polite">
        {lines.map((l, i) => (
          <pre key={i} className={cn("whitespace-pre-wrap break-words", l.kind === "err" && "text-[#d93a4a] dark:text-[#f08a8a]", l.kind === "ok" && "text-[#0e9f6e] dark:text-[#5fd3a8]", l.kind === "dim" && "text-[#7a8594]", l.kind === "in" && "text-[#2563eb] dark:text-[#9fe3d6]")}>
            {l.text || " "}
          </pre>
        ))}
        <div ref={end} />
      </div>
      <form
        className="flex items-center gap-2 border-t border-hairline px-4 py-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!busy) submit();
        }}
      >
        <span className="text-[#2563eb] dark:text-[#9fe3d6]">{cwd}$</span>
        <input
          ref={field}
          autoFocus
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Tab") {
              e.preventDefault();
              complete();
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              hpos.current = Math.max(0, hpos.current - 1);
              setInput(history.current[hpos.current] ?? input);
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              hpos.current = Math.min(history.current.length, hpos.current + 1);
              setInput(history.current[hpos.current] ?? "");
            } else if (e.key === "l" && e.ctrlKey) {
              e.preventDefault();
              setLines([]);
            }
          }}
          aria-label="Command"
          spellCheck={false}
          autoCapitalize="off"
          autoComplete="off"
          className="min-w-0 flex-1 bg-transparent caret-[#16b67a] outline-none"
        />
        {busy && <Orb state="working" label="running" />}
      </form>
    </div>
  );
}
