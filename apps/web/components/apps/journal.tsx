"use client";

import type { AuditEntry, AuditKind } from "@kairos/contracts";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  BookOpenText,
  Brain,
  CircleCheck,
  Cpu,
  Flag,
  Gavel,
  GitFork,
  KeyRound,
  Link2,
  Link2Off,
  type LucideIcon,
  Send,
  ShieldCheck,
  Sparkles,
  Undo2,
  Wrench,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useClient } from "@/app/providers";
import { EvidenceChip, PidChip, formatTime } from "@/components/status";
import { cn } from "@/lib/utils";

const KIND: Record<AuditKind, { icon: LucideIcon; color: string; label: string }> = {
  task: { icon: Flag, color: "text-foreground border-line-strong", label: "task" },
  spawn: { icon: GitFork, color: "text-text-2 border-line-strong", label: "spawn" },
  state: { icon: Cpu, color: "text-text-2 border-line-strong", label: "state" },
  model: { icon: Sparkles, color: "text-text-2 border-line-strong", label: "model" },
  knowledge: { icon: BookOpenText, color: "text-ev-knowledge border-ev-knowledge/60", label: "knowledge" },
  memory: { icon: Brain, color: "text-st-running border-st-running/50", label: "memory" },
  ipc: { icon: Send, color: "text-ev-tool border-ev-tool/60", label: "ipc" },
  syscall: { icon: KeyRound, color: "text-brand border-brand/60", label: "syscall" },
  policy: { icon: ShieldCheck, color: "text-brand border-brand/60", label: "policy" },
  approval: { icon: Gavel, color: "text-st-waiting border-st-waiting/60", label: "approval" },
  tool: { icon: Wrench, color: "text-ev-tool border-ev-tool/60", label: "tool" },
  verify: { icon: CircleCheck, color: "text-st-running border-st-running/50", label: "verify" },
  commit: { icon: CircleCheck, color: "text-st-running border-st-running/70", label: "commit" },
  rollback: { icon: Undo2, color: "text-st-failed border-st-failed/70", label: "rollback" },
};
const PRIVILEGED: AuditKind[] = ["syscall", "policy", "approval", "commit", "rollback"];

type Chain = "verified" | "tampered" | "intact" | "broken" | "none";

/** The kernel's verdict when the gateway reports one (it recomputes every hash); otherwise a link check in the browser,
 *  which can only say whether each prev_hash matches the previous entry's hash. */
function chainStatus(entries: AuditEntry[], verified: boolean | null | undefined): Chain {
  if (verified === true) return "verified";
  if (verified === false) return "tampered";
  if (!entries.some((e) => e.hash)) return "none";
  for (let i = 1; i < entries.length; i++) if (entries[i].prev_hash !== entries[i - 1].hash) return "broken";
  return "intact";
}

const CHAIN_TEXT: Record<Exclude<Chain, "none">, string> = {
  verified: "hash chain verified: the kernel recomputed all N entries",
  tampered: "hash chain verification failed: an entry was changed after it was written",
  intact: "chain intact: N entries link to their predecessor",
  broken: "chain broken: an entry's prev_hash doesn't match the previous entry",
};

function Stat({ value, label, tone = "text-foreground" }: { value: number | string; label: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface-2 px-3 py-2">
      <p className={cn("font-mono text-2xl font-bold", tone)}>{value}</p>
      <p className="text-xs text-text-2">{label}</p>
    </div>
  );
}

function Entry({ e }: { e: AuditEntry }) {
  const k = KIND[e.kind] ?? KIND.task;
  const Icon = k.icon;
  const privileged = PRIVILEGED.includes(e.kind);
  return (
    <li className="relative ml-4 pb-2 pl-7">
      <span className={cn("absolute -left-3.5 top-1 flex size-7 items-center justify-center rounded-full border-2 bg-background", k.color)}>
        <Icon className="size-3.5" aria-hidden />
      </span>
      <div className={cn("rounded-lg border px-3 py-2", privileged ? "border-line bg-surface-1 shadow-panel" : "border-transparent")}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-10 font-mono text-xs text-text-2">#{e.seq}</span>
          <span className="font-mono text-xs text-text-2">{formatTime(e.ts)}</span>
          <PidChip pid={e.pid} />
          <span className={cn("font-mono text-xs font-semibold uppercase", k.color.split(" ")[0])}>{e.kind}</span>
          <span className="font-mono text-xs text-text-2">{e.actor}</span>
          {e.hash && (
            <span className="ml-auto font-mono text-xs text-muted-foreground" title={`hash ${e.hash}\nprev ${e.prev_hash ?? "—"}`}>
              {e.prev_hash ? `${e.prev_hash.slice(0, 6)} → ` : "genesis → "}
              <span className="text-text-2">{e.hash.slice(0, 8)}</span>
            </span>
          )}
        </div>
        <p className={cn("mt-0.5 text-sm", privileged && "font-medium")}>{e.summary}</p>
        {!!e.refs?.length && (
          <div className="mt-1 flex flex-wrap gap-1.5">
            {e.refs.map((r) =>
              r.startsWith("/org") ? <EvidenceChip key={r} path={r} /> : <span key={r} className="font-mono text-xs text-text-2">{r}</span>,
            )}
          </div>
        )}
      </div>
    </li>
  );
}

export function JournalApp({ taskId }: { taskId: string }) {
  const client = useClient();
  const [hidden, setHidden] = useState<AuditKind[]>(["state", "model"]);
  const [pid, setPid] = useState<string>("");
  const [grouped, setGrouped] = useState(false);
  const q = useQuery({ queryKey: ["audit", taskId], queryFn: () => client.audit(taskId), refetchInterval: 5_000 });
  const entries = [...(q.data?.entries ?? [])].sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0));
  const counts = entries.reduce<Record<string, number>>((m, e) => ({ ...m, [e.kind]: (m[e.kind] ?? 0) + 1 }), {});
  const pids = [...new Set(entries.map((e) => e.pid).filter((p): p is number => !!p))].sort((a, b) => a - b);
  const chain = chainStatus(entries, q.data?.chain_verified);
  const shown = entries.filter((e) => !hidden.includes(e.kind)).filter((e) => !pid || String(e.pid ?? "") === pid);
  const s = q.data?.stats;
  const kinds = (Object.keys(KIND) as AuditKind[]).filter((k) => counts[k]);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <Link href={`/tasks/${taskId}`} className="flex items-center gap-1 text-sm text-text-2 hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden /> back to task {taskId}
      </Link>
      <header className="space-y-4 rounded-xl border border-line bg-surface-1 p-5 shadow-panel">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-text-2">Audit journal · {taskId}</p>
          <h1 className="mt-1 text-xl font-semibold">{q.data?.goal ?? "…"}</h1>
        </div>
        <div className="grid grid-cols-2 gap-2 @xl:grid-cols-4 @5xl:grid-cols-8">
          <Stat value={entries.length} label="entries" />
          <Stat value={s?.agents ?? 0} label="agents" />
          <Stat value={s?.knowledge_objects ?? 0} label="knowledge objects" tone="text-ev-knowledge" />
          <Stat value={s?.ipc_messages ?? 0} label="IPC messages" tone="text-ev-tool" />
          <Stat value={s?.tool_calls ?? 0} label="tool calls" tone="text-ev-tool" />
          <Stat value={s?.privileged_syscalls ?? 0} label="privileged syscalls" tone="text-brand" />
          <Stat value={s?.approvals ?? 0} label="approvals" tone="text-st-waiting" />
          <Stat value={s?.rollbacks ?? 0} label="rollbacks" tone={s?.rollbacks ? "text-st-failed" : "text-foreground"} />
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {chain !== "none" && (
            <p
              className={cn(
                "inline-flex items-center gap-2 rounded-md border px-2.5 py-1 text-sm font-medium",
                chain === "verified" || chain === "intact" ? "border-st-running/50 bg-st-running/10 text-st-running" : "border-st-failed/60 bg-st-failed/10 text-st-failed",
              )}
              data-testid="chain-status"
            >
              {chain === "verified" ? <ShieldCheck className="size-4" aria-hidden /> : chain === "intact" ? <Link2 className="size-4" aria-hidden /> : <Link2Off className="size-4" aria-hidden />}
              {CHAIN_TEXT[chain].replace("N", String(entries.length))}
            </p>
          )}
          {!!s?.models?.length && <p className="text-sm text-text-2">models: <span className="font-mono">{s.models.join(", ")}</span></p>}
        </div>
        {q.isError && <p className="text-sm text-st-failed">{String(q.error)}</p>}
      </header>

      <div className="flex flex-wrap items-center gap-2">
        {kinds.map((k) => {
          const on = !hidden.includes(k);
          const Icon = KIND[k].icon;
          return (
            <button
              key={k}
              type="button"
              aria-pressed={on}
              onClick={() => setHidden((h) => (on ? [...h, k] : h.filter((x) => x !== k)))}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
                on ? KIND[k].color : "border-line text-muted-foreground line-through",
              )}
            >
              <Icon className="size-3.5" aria-hidden /> {KIND[k].label} <span className="font-mono">{counts[k]}</span>
            </button>
          );
        })}
        <select value={pid} onChange={(e) => setPid(e.target.value)} aria-label="Filter by PID" className="ml-auto h-8 rounded-md border border-line bg-surface-2 px-2 font-mono text-xs">
          <option value="">all PIDs</option>
          {pids.map((p) => (
            <option key={p} value={p}>
              PID {p}
            </option>
          ))}
        </select>
        <div role="radiogroup" aria-label="Layout" className="flex overflow-hidden rounded-md border border-line text-xs">
          {[
            [false, "Chronological"],
            [true, "By kind"],
          ].map(([g, label]) => (
            <button
              key={String(label)}
              type="button"
              role="radio"
              aria-checked={grouped === g}
              onClick={() => setGrouped(g as boolean)}
              className={cn("h-8 px-2.5 text-text-2", grouped === g && "bg-surface-3 text-foreground")}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {grouped ? (
        <div className="space-y-5">
          {kinds
            .filter((k) => !hidden.includes(k))
            .map((k) => {
              const mine = shown.filter((e) => e.kind === k);
              if (!mine.length) return null;
              return (
                <section key={k}>
                  <h2 className={cn("mb-2 text-sm font-semibold uppercase tracking-wider", KIND[k].color.split(" ")[0])}>
                    {KIND[k].label} <span className="font-mono text-text-2">({mine.length})</span>
                  </h2>
                  <ol className="border-l border-line">
                    {mine.map((e) => (
                      <Entry key={e.entry_id} e={e} />
                    ))}
                  </ol>
                </section>
              );
            })}
        </div>
      ) : (
        <ol className="border-l border-line">
          {shown.map((e) => (
            <Entry key={e.entry_id} e={e} />
          ))}
        </ol>
      )}
    </div>
  );
}
