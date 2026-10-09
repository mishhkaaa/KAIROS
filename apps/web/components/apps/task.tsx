"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Play, Save, ScrollText, Square } from "lucide-react";
import Link from "next/link";
import type { Event } from "@kairos/contracts";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useClient } from "@/app/providers";
import { ApprovalDrawer } from "@/components/approval-drawer";
import { KnowledgePanel } from "@/components/knowledge-panel";
import { ProcessTree } from "@/components/process-tree";
import { InvalidationBanner, ResultPanel, SandboxPanel } from "@/components/result-panel";
import { TaskStatusBadge, duration } from "@/components/status";
import { Inspector } from "@/components/task/inspector";
import { RunStory } from "@/components/desktop/run-story";
import { Timeline } from "@/components/timeline";
import { Button } from "@/components/ui/button";
import { isActive } from "@/lib/events";
import { KairosError, type StreamStatus } from "@/lib/kairos-client";
import { useTaskEvents } from "@/lib/use-task-events";
import { cn } from "@/lib/utils";

const STREAM_LABEL: Record<StreamStatus, [string, string]> = {
  connecting: ["connecting", "bg-st-idle"],
  open: ["live", "bg-st-running"],
  reconnecting: ["reconnecting", "bg-st-waiting"],
  closed: ["offline", "bg-st-failed"],
};

/** Re-renders every second while `on`, for the elapsed clock. */
function useTick(on: boolean) {
  const [, setN] = useState(0);
  useEffect(() => {
    if (!on) return;
    const t = setInterval(() => setN((n) => n + 1), 1_000);
    return () => clearInterval(t);
  }, [on]);
}

export function TaskApp({ id }: { id: string }) {
  const client = useClient();
  const qc = useQueryClient();
  const view = useTaskEvents(id);
  const active = isActive(view.status);
  const done = view.status === "completed" || view.status === "failed" || view.status === "cancelled";
  const [tab, setTab] = useState<"live" | "result" | null>(null);
  const shownTab = tab ?? (done ? "result" : "live"); // switches to the result by itself when the run ends
  const [picked, setPicked] = useState<number | null>(null);
  useTick(active);

  const control = useMutation({
    mutationFn: (what: "cancel" | "resume" | "checkpoint"): Promise<unknown> =>
      what === "cancel" ? client.cancelTask(id) : what === "resume" ? client.resumeTask(id) : client.checkpointTask(id),
    onSuccess: (_, what) => toast(what === "cancel" ? "Task cancelled" : what === "resume" ? "Task resumed" : "Checkpoint saved"),
    onError: (e) => toast.error("Task control failed", { description: e instanceof KairosError ? e.message : String(e) }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["task", id] }),
  });

  const [streamLabel, streamDot] = STREAM_LABEL[view.stream];
  const goal = view.task?.goal ?? view.timeline.find((e) => e.type === "task.created")?.payload?.goal;
  const start = view.task?.created_at ?? view.timeline[0]?.ts;
  const end = done ? (view.task?.updated_at ?? view.timeline.at(-1)?.ts) : null;
  const procs = Object.values(view.processes);
  const last = useMemo(() => {
    const m: Record<number, Event> = {};
    for (const e of view.timeline) if (e.pid) m[e.pid] = e;
    return m;
  }, [view.timeline]);
  // Default selection: whoever is waiting (usually the action agent at the approval), else the root.
  const selected = picked ?? procs.find((p) => p.state === "WAITING" && p.waiting_on?.startsWith("approval:"))?.pid ?? procs.find((p) => !p.ppid)?.pid ?? null;

  return (
    <div className="flex flex-col gap-4 @3xl:h-full">
      <header className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <TaskStatusBadge status={view.status} className="text-sm" data-testid="task-status" />
            <span className="font-mono text-sm text-text-2">{id}</span>
            {start && <span className="font-mono text-sm text-text-2" title="Elapsed">{duration(start, end)}</span>}
            <span className="flex items-center gap-1.5 text-xs text-text-2" title="Event stream">
              <span className={cn("size-2 rounded-full", streamDot)} aria-hidden /> {streamLabel}
            </span>
          </div>
          <h1 className="mt-1.5 line-clamp-2 text-xl font-semibold leading-snug @3xl:text-2xl">{String(goal ?? "…")}</h1>
        </div>
        <div className="flex w-full flex-wrap items-center gap-2 @3xl:w-auto @3xl:shrink-0">
          <ApprovalDrawer view={view} />
          {active && (
            <Button variant="outline" size="sm" onClick={() => control.mutate("checkpoint")} disabled={control.isPending}>
              <Save className="size-4" /> Checkpoint
            </Button>
          )}
          {(view.status === "paused" || view.status === "failed") && (
            <Button variant="outline" size="sm" onClick={() => control.mutate("resume")} disabled={control.isPending}>
              <Play className="size-4" /> Resume
            </Button>
          )}
          {active && (
            <Button variant="outline" size="sm" className="text-st-failed hover:text-st-failed" onClick={() => control.mutate("cancel")} disabled={control.isPending}>
              <Square className="size-4" /> Cancel
            </Button>
          )}
          <Button variant="outline" size="sm" asChild>
            <Link href={`/audit/${id}`}>
              <ScrollText className="size-4" /> Audit
            </Link>
          </Button>
        </div>
      </header>

      <div className="@3xl:hidden">
        <RunStory view={view} />
      </div>

      <div className="hidden min-h-0 flex-1 flex-col gap-3 @3xl:flex">
        <div role="tablist" aria-label="Task view" className="flex gap-1 border-b border-line">
          {(["live", "result"] as const).map((t) => (
            <button
              key={t}
              role="tab"
              type="button"
              aria-selected={shownTab === t}
              disabled={t === "result" && !done}
              onClick={() => setTab(t)}
              className={cn(
                "-mb-px border-b-2 px-3 pb-2 text-sm font-medium capitalize transition-colors disabled:opacity-40",
                shownTab === t ? "border-brand text-foreground" : "border-transparent text-text-2 hover:text-foreground",
              )}
            >
              {t === "live" ? "Live" : "Result"}
            </button>
          ))}
        </div>

        {shownTab === "live" ? (
          <div className="grid min-h-0 flex-1 grid-cols-[minmax(340px,1fr)_minmax(0,1.55fr)_minmax(300px,0.85fr)] gap-4">
            <section className="min-h-0 rounded-xl border border-line bg-surface-1 p-3 shadow-panel">
              <Timeline events={view.timeline} retrieved={view.retrieved} start={start} />
            </section>
            <section className="flex min-h-0 flex-col rounded-xl border border-line bg-surface-1 p-3 shadow-panel">
              <h2 className="px-1 text-[17px] font-semibold">
                Processes <span className="font-mono text-sm font-normal text-text-2">({procs.length})</span>
              </h2>
              <div className="min-h-0 flex-1">
                <ProcessTree processes={view.processes} last={last} selected={selected} onSelect={setPicked} />
              </div>
            </section>
            <section className="min-h-0 space-y-3 overflow-y-auto">
              <div className="rounded-xl border border-line bg-surface-1 shadow-panel">
                <Inspector pid={selected} processes={view.processes} events={view.timeline} active={active} />
              </div>
              <InvalidationBanner view={view} />
              <KnowledgePanel view={view} />
              <SandboxPanel view={view} />
            </section>
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <ResultPanel taskId={id} view={view} />
          </div>
        )}
      </div>
    </div>
  );
}
