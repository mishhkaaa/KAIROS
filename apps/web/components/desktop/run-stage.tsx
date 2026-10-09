"use client";

import type { Event } from "@kairos/contracts";
import { BookOpenText, Globe, KeyRound, Maximize2, Users } from "lucide-react";
import { useMemo } from "react";
import { ArtifactImage } from "@/components/artifacts";
import { tokensOf } from "@/components/process-tree";
import { TaskStatusBadge } from "@/components/status";
import { ORB_LABEL, orbFor } from "@/lib/desktop/orb";
import { isActive, strList } from "@/lib/events";
import { useTaskEvents } from "@/lib/use-task-events";
import { cn } from "@/lib/utils";
import { AgentAvatar } from "./agent-avatar";
import { Orb } from "./orb";
import { TypingDots } from "./typing-dots";
import { DataTable, DocChip } from "./run-story";

function Card({ title, icon: Icon, count, children, className }: { title: string; icon: typeof Users; count?: number; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("panel stage-in rounded-2xl p-4", className)}>
      <h3 className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-text-2">
        <Icon className="size-4" aria-hidden /> {title}
        {count !== undefined && <span className="font-mono text-xs">{count}</span>}
      </h3>
      {children}
    </section>
  );
}

/** The desktop beside a docked live task: who is working, what they read, what they asked the kernel to do, what the
 *  sandboxes saw, the data, and finally the result. Everything appears as it happens. */
export function RunStage({ taskId, onZoom }: { taskId: string; onZoom: () => void }) {
  const view = useTaskEvents(taskId);
  const procs = Object.values(view.processes).sort((a, b) => a.pid - b.pid);
  const last = useMemo(() => {
    const m: Record<number, Event> = {};
    for (const e of view.timeline) if (e.pid) m[e.pid] = e;
    return m;
  }, [view.timeline]);
  const docs = useMemo(() => {
    const seen = new Map<string, { path: string; by?: string; flagged: boolean }>();
    for (const r of view.retrieved) {
      const by = r.event.pid ? view.processes[r.event.pid]?.agent : undefined;
      for (const p of strList(r.event, "paths")) if (!seen.has(p)) seen.set(p, { path: p, by, flagged: r.flagged.includes(p) });
      for (const p of r.flagged) seen.set(p, { path: p, by, flagged: true });
    }
    return [...seen.values()].reverse();
  }, [view.retrieved, view.processes]);
  const calls = useMemo(() => {
    const byCorr = new Map<string, { capability: string; agent?: string; state: string }>();
    for (const e of view.timeline) {
      const id = e.correlation_id ?? e.event_id ?? "";
      if (e.type === "syscall.requested") byCorr.set(id, { capability: String(e.payload?.capability ?? "?"), agent: e.pid ? view.processes[e.pid]?.agent : undefined, state: "asked" });
      const c = byCorr.get(id);
      if (!c) continue;
      if (e.type === "syscall.decided") c.state = e.payload?.decision === "ALLOW" ? "allowed" : e.payload?.decision === "DENY" ? "denied" : "needs approval";
      if (e.type === "syscall.completed") c.state = String(e.payload?.status ?? "done").toLowerCase();
    }
    return [...byCorr.values()];
  }, [view.timeline, view.processes]);
  const data = [...view.timeline].reverse().find((e) => e.type === "task.data");
  const shots = Object.values(view.sandboxes).flatMap((b) => b.screenshots);
  const goal = view.task?.goal ?? view.timeline.find((e) => e.type === "task.created")?.payload?.goal;
  const running = isActive(view.status);

  return (
    <div className="grid content-start gap-4 @[900px]:grid-cols-2">
      <section className="panel stage-in flex items-start gap-3 rounded-2xl p-4 @[900px]:col-span-2">
        {running ? <Orb state="working" size={32} label="running" /> : <span className="size-8" aria-hidden />}
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-base font-semibold leading-snug">{String(goal ?? "…")}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-text-2">
            <TaskStatusBadge status={view.status} /> <span className="font-mono">{taskId}</span>
          </p>
        </div>
        <button type="button" onClick={onZoom} className="win-btn size-8" aria-label="Open the full task view">
          <Maximize2 className="size-4" />
        </button>
      </section>

      <Card title="Agents" icon={Users} count={procs.length} className="@[900px]:col-span-2">
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-3">
          {procs.map((p) => {
            const orb = orbFor(p.state, last[p.pid], p.waiting_on);
            return (
              <li key={p.pid} className={cn("stage-in flex items-center gap-3 rounded-2xl bg-surface-2 p-2.5", p.waiting_on?.startsWith("approval:") && "ring-2 ring-st-waiting")}>
                <AgentAvatar agent={p.agent} state={p.state} size={60} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">{p.agent}</p>
                  <p className="font-mono text-[11px] text-text-2">
                    PID {p.pid} · {tokensOf(p).toLocaleString()} tok
                  </p>
                  <p className="mt-1 flex items-center gap-1.5 text-xs text-text-2">
                    {orb ? <Orb state={orb} size={32} label={ORB_LABEL[orb]} /> : null}
                    <span className="truncate">{orb ? ORB_LABEL[orb] : p.state?.toLowerCase()}</span>
                    {orb === "composing" && <TypingDots className="text-[#8b5cf6]" />}
                  </p>
                </div>
              </li>
            );
          })}
          {!procs.length && <li className="text-sm text-text-2">The planner is starting…</li>}
        </ul>
      </Card>

      <Card title="Referred to" icon={BookOpenText} count={docs.length}>
        <ul className="flex flex-wrap gap-1.5">
          {docs.slice(0, 24).map((d) => (
            <li key={d.path} className="stage-in max-w-full">
              <DocChip path={d.path} flagged={d.flagged} />
            </li>
          ))}
          {!docs.length && <li className="text-sm text-text-2">Nothing read yet.</li>}
        </ul>
        {docs.some((d) => d.flagged) && <p className="mt-2 text-xs font-medium text-untrusted">Red: the firewall found instructions in it. Agents read it as data only.</p>}
      </Card>

      <Card title="Asked the kernel" icon={KeyRound} count={calls.length}>
        <ul className="space-y-1.5">
          {calls.map((c, i) => (
            <li key={i} className="stage-in flex items-center gap-2 text-sm">
              <span className="font-mono text-xs">{c.capability}</span>
              <span className="truncate text-xs text-text-2">{c.agent}</span>
              <span
                className={cn(
                  "ml-auto shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold",
                  c.state === "needs approval" ? "bg-st-waiting/15 text-st-waiting" : c.state === "denied" || c.state === "failed" ? "bg-st-failed/15 text-st-failed" : "bg-st-running/12 text-st-running",
                )}
              >
                {c.state}
              </span>
            </li>
          ))}
          {!calls.length && <li className="text-sm text-text-2">No actions yet.</li>}
        </ul>
      </Card>

      {shots.length > 0 && (
        <Card title="Opened in a sandbox" icon={Globe} count={shots.length}>
          <div className="grid grid-cols-2 gap-2">
            {shots.slice(-4).map((s) => (
              <ArtifactImage key={s} artifact={s} />
            ))}
          </div>
        </Card>
      )}

      {data && (
        <Card title="Data" icon={BookOpenText} className="@[900px]:col-span-2">
          <DataTable columns={strList(data, "columns")} rows={Array.isArray(data.payload?.rows) ? (data.payload.rows as unknown[][]) : []} />
        </Card>
      )}

      {!running && view.summary && (
        <section className="panel stage-in rounded-2xl p-4 @[900px]:col-span-2">
          <p className="text-xs font-semibold text-st-running">Result</p>
          <p className="mt-1 text-sm leading-relaxed">{view.summary}</p>
          <button type="button" onClick={onZoom} className="mt-2 text-sm font-medium text-brand hover:underline">
            Open the full result
          </button>
        </section>
      )}
    </div>
  );
}
