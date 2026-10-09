"use client";

import type { AgentProcess, Event } from "@kairos/contracts";
import { useQuery } from "@tanstack/react-query";
import { Hourglass, Pause, Play, Save, Skull } from "lucide-react";
import { useClient } from "@/app/providers";
import { AgentStateBadge, PidChip } from "@/components/status";
import { tokensOf } from "@/components/process-tree";
import { str } from "@/lib/events";
import { agentTone } from "@/lib/tones";
import { cn } from "@/lib/utils";
import { availableActions, type ProcessAction, useProcessActions } from "./process-actions";

const ICON = { pause: Pause, resume: Play, checkpoint: Save, kill: Skull };

function QuotaBar({ label, used, max, unit = "" }: { label: string; used: number; max?: number; unit?: string }) {
  const pct = max ? Math.min(100, (100 * used) / max) : 0;
  return (
    <div>
      <div className="flex justify-between text-xs">
        <span className="text-text-2">{label}</span>
        <span className="font-mono">
          {Math.round(used).toLocaleString()}
          {max ? ` / ${max.toLocaleString()}` : ""}
          {unit}
        </span>
      </div>
      {!!max && (
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-3" aria-hidden>
          <div
            className={cn("h-full rounded-full transition-[width] duration-300", pct > 90 ? "bg-st-failed" : pct > 70 ? "bg-st-waiting" : "bg-brand")}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</h4>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}

/** The selected process, live: identity, capabilities, quota use, model, children, last checkpoint, controls. */
export function Inspector({ pid, processes, events, active }: { pid: number | null; processes: Record<number, AgentProcess>; events: Event[]; active: boolean }) {
  const client = useClient();
  const known = pid !== null ? processes[pid] : undefined;
  const q = useQuery({
    queryKey: ["agents", "process", pid],
    queryFn: () => client.getProcess(pid!),
    enabled: pid !== null,
    refetchInterval: active ? 3_000 : false,
  });
  const { act, dialog } = useProcessActions();
  if (pid === null || !known) {
    return <p className="p-4 text-sm text-muted-foreground">Select a process in the tree to inspect it.</p>;
  }
  // Live state from the event stream wins; the snapshot adds quota, capabilities and mounts.
  const p: AgentProcess = { ...(q.data ?? {}), ...known, quota: q.data?.quota ?? known.quota, usage: known.usage ?? q.data?.usage };
  const mine = events.filter((e) => e.pid === pid);
  const model = p.model ?? [...mine].reverse().find((e) => e.type === "model.invoked")?.payload?.model;
  const checkpoint = p.checkpoint_id ?? [...mine].reverse().map((e) => (e.type === "process.checkpointed" ? str(e, "checkpoint_id") : undefined)).find(Boolean);
  const children = Object.values(processes).filter((c) => c.ppid === pid);
  const tone = agentTone(p.state);

  return (
    <div className="space-y-4 p-4">
      <header className="space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-2xl font-bold">
            <span className="text-muted-foreground">PID </span>
            {p.pid}
          </span>
          <AgentStateBadge state={p.state} />
        </div>
        <p className="text-base font-semibold">{p.agent}</p>
        <p className="font-mono text-xs text-text-2">PPID {p.ppid ?? "—"}{p.agent_version ? ` · v${p.agent_version}` : ""}</p>
        {p.waiting_on && (
          <p className={cn("flex items-center gap-1.5 font-mono text-sm", tone.text)}>
            <Hourglass className="size-4" aria-hidden /> waiting on {p.waiting_on}
          </p>
        )}
      </header>

      {availableActions(p).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {availableActions(p).map((a: ProcessAction) => {
            const Icon = ICON[a];
            return (
              <button
                key={a}
                type="button"
                onClick={() => act(a, p)}
                className={cn(
                  "flex h-8 items-center gap-1.5 rounded-md border border-line px-2.5 text-sm capitalize transition-colors hover:bg-surface-3",
                  a === "kill" && "text-st-failed hover:border-st-failed",
                )}
              >
                <Icon className="size-4" aria-hidden /> {a}
              </button>
            );
          })}
        </div>
      )}

      <div className="space-y-2.5">
        <QuotaBar label="Tokens" used={tokensOf(p)} max={p.quota?.max_tokens} />
        <QuotaBar label="Tool calls" used={p.usage?.tool_calls ?? 0} max={p.quota?.max_tool_calls} />
        <QuotaBar label="Wall time" used={p.usage?.wall_seconds ?? 0} max={p.quota?.max_wall_seconds} unit=" s" />
      </div>

      <Field label="Model">{model ? <span className="font-mono">{String(model)}</span> : <span className="text-muted-foreground">no model call yet</span>}</Field>

      <Field label={`Capabilities (${p.capabilities?.length ?? 0})`}>
        <div className="flex flex-wrap gap-1">
          {(p.capabilities ?? []).map((c) => (
            <span key={c} className={cn("rounded-md border px-1.5 py-0.5 font-mono text-xs", /write|delete|exec/.test(c) ? "border-risk-medium/50 text-risk-medium" : "border-line text-text-2")}>
              {c}
            </span>
          ))}
          {!p.capabilities?.length && <span className="text-muted-foreground">—</span>}
        </div>
      </Field>

      {!!p.memory_mounts?.length && (
        <Field label="Knowledge mounts">
          <p className="font-mono text-xs text-ev-knowledge">{p.memory_mounts.join("  ")}</p>
        </Field>
      )}

      <Field label={`Children (${children.length})`}>
        <div className="flex flex-wrap gap-1">
          {children.map((c) => <PidChip key={c.pid} pid={c.pid} agent={c.agent} />)}
          {!children.length && <span className="text-muted-foreground">none</span>}
        </div>
      </Field>

      <Field label="Last checkpoint">
        {checkpoint ? <span className="font-mono text-xs">{checkpoint}</span> : <span className="text-muted-foreground">none</span>}
      </Field>

      {p.last_error && (
        <Field label="Last error">
          <p className="font-mono text-xs text-st-failed">{p.last_error.code}: {p.last_error.message}</p>
        </Field>
      )}
      {dialog}
    </div>
  );
}
