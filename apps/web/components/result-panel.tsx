"use client";

import type { Event } from "@kairos/contracts";
import { useQuery } from "@tanstack/react-query";
import { Box, Brain, Camera, CircleCheck, CircleX, FileText, Undo2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useClient } from "@/app/providers";
import { str, strList, type TaskView } from "@/lib/events";
import { cn } from "@/lib/utils";
import { ArtifactImage, ArtifactMarkdown, artifactName, isImage } from "./artifacts";
import { EvidenceChip, PidChip } from "./status";

interface ActionLine {
  id: string;
  capability?: string;
  outcome: "committed" | "verified" | "rolled back" | "pending";
  change?: string;
}

/** Each committed action from its syscall events; for a tracker update, the field change from the approved arguments. */
export function committedActions(ids: string[], events: Event[], view: TaskView): ActionLine[] {
  return ids.map((id) => {
    const mine = events.filter((e) => e.correlation_id === id);
    const req = mine.find((e) => e.type === "syscall.requested");
    const commit = mine.find((e) => e.type === "transaction.committed");
    const rollback = mine.find((e) => e.type === "transaction.rolled_back");
    const approval = Object.values(view.approvals).find((a) => a.syscall.syscall_id === id);
    const args = approval?.syscall.arguments as { key?: string; fields?: Record<string, unknown> } | undefined;
    const change = args?.key && args.fields ? `${args.key}: ${Object.entries(args.fields).map(([k, v]) => `${k} → ${String(v)}`).join(", ")}` : undefined;
    return {
      id,
      capability: req ? str(req, "capability") : approval?.syscall.capability,
      outcome: rollback ? "rolled back" : commit ? (commit.payload?.verified ? "verified" : "committed") : "pending",
      change,
    };
  });
}

function Side({ title, icon: Icon, children }: { title: string; icon: typeof Box; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-surface-1 p-4 shadow-panel">
      <h3 className="mb-2.5 flex items-center gap-2 text-sm font-semibold">
        <Icon className="size-4 text-text-2" aria-hidden /> {title}
      </h3>
      {children}
    </section>
  );
}

export function ResultPanel({ taskId, view }: { taskId: string; view: TaskView }) {
  const client = useClient();
  const done = view.status === "completed" || view.status === "failed" || view.status === "cancelled";
  const artifacts = useQuery({ queryKey: ["artifacts", taskId], queryFn: () => client.taskArtifacts(taskId), enabled: done });
  if (!done) return null;
  const failed = view.status !== "completed";
  const r = view.task?.result;
  const tokens = (r?.usage?.tokens_prompt ?? 0) + (r?.usage?.tokens_completion ?? 0);
  const refs = artifacts.data ?? [];
  const plan = refs.find((a) => a.endsWith("/recovery-plan.md"));
  const shots = refs.filter(isImage);
  const actions = committedActions(r?.actions ?? [], view.timeline, view);

  return (
    <div className="grid gap-4 @7xl:grid-cols-[minmax(0,1fr)_380px]">
      <article className="min-w-0 space-y-4">
        <section className={cn("rounded-xl border bg-surface-1 p-5 shadow-panel", failed ? "border-st-failed/60" : "border-line")}>
          <h2 className={cn("flex items-center gap-2 text-sm font-semibold uppercase tracking-wider", failed ? "text-st-failed" : "text-st-running")}>
            {failed ? <CircleX className="size-4" aria-hidden /> : <CircleCheck className="size-4" aria-hidden />}
            {failed ? `Task ${view.status}` : "Summary"}
          </h2>
          <div className="mt-2 text-base leading-relaxed [&_li]:ml-5 [&_ol]:list-decimal [&_ul]:list-disc">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{(failed ? view.failure : view.summary) ?? r?.summary ?? ""}</ReactMarkdown>
          </div>
        </section>
        {plan && (
          <section className="rounded-xl border border-line bg-surface-1 p-6 shadow-panel" data-testid="recovery-plan">
            <ArtifactMarkdown artifact={plan} />
          </section>
        )}
      </article>

      <aside className="space-y-4">
        <Side title={`Actions committed (${actions.length})`} icon={CircleCheck}>
          <ul className="space-y-2.5">
            {actions.length === 0 && <li className="text-sm text-text-2">No world-changing actions.</li>}
            {actions.map((a) => (
              <li key={a.id} className="text-sm">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="font-mono font-semibold text-brand">{a.capability ?? "syscall"}</span>
                  <span
                    className={cn(
                      "rounded-md px-1.5 font-mono text-xs font-semibold",
                      a.outcome === "rolled back" ? "bg-st-failed/12 text-st-failed" : a.outcome === "pending" ? "bg-surface-3 text-text-2" : "bg-st-running/12 text-st-running",
                    )}
                  >
                    {a.outcome === "rolled back" && <Undo2 className="mr-1 inline size-3" aria-hidden />}
                    {a.outcome}
                  </span>
                </p>
                {a.change && <p className="mt-0.5 font-mono text-xs text-text-2">{a.change}</p>}
                <p className="font-mono text-xs text-muted-foreground">{a.id}</p>
              </li>
            ))}
          </ul>
        </Side>

        {!!shots.length && (
          <Side title="Sandbox screenshot" icon={Camera}>
            <div className="space-y-2">
              {shots.map((s) => (
                <ArtifactImage key={s} artifact={s} />
              ))}
            </div>
          </Side>
        )}

        {!!refs.length && (
          <Side title="Artifacts" icon={FileText}>
            <ul className="space-y-1 font-mono text-sm">
              {refs.map((a) => (
                <li key={a}>
                  <a href={client.artifactUrl(a) ?? undefined} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-ev-tool hover:underline">
                    {isImage(a) ? <Camera className="size-3.5" aria-hidden /> : <FileText className="size-3.5" aria-hidden />}
                    {artifactName(a)}
                  </a>
                </li>
              ))}
            </ul>
          </Side>
        )}

        {!!r?.evidence?.length && (
          <Side title={`Evidence (${r.evidence.length})`} icon={FileText}>
            <div className="flex max-h-56 flex-wrap gap-1.5 overflow-y-auto">
              {r.evidence.map((p) => (
                <EvidenceChip key={p} path={p} flagged={view.flaggedPaths.includes(p)} />
              ))}
            </div>
          </Side>
        )}
        {r && (
          <p className="px-1 font-mono text-xs text-text-2">
            {tokens.toLocaleString()} tokens · {r.usage?.tool_calls ?? 0} tool calls · {r.usage?.children_spawned ?? 0} agents
          </p>
        )}
      </aside>
    </div>
  );
}

export function SandboxPanel({ view }: { view: TaskView }) {
  const boxes = Object.values(view.sandboxes);
  if (!boxes.length) return null;
  return (
    <div className="rounded-xl border border-line bg-surface-1 p-3 shadow-panel">
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <Box className="size-4 text-ev-tool" aria-hidden /> Sandboxes
      </h2>
      <ul className="mt-2 space-y-2">
        {boxes.map((b) => (
          <li key={b.sandboxId} className="text-sm">
            <p className="flex flex-wrap items-center gap-2">
              <PidChip pid={b.pid} />
              <span className="font-mono text-xs">{b.sandboxId}</span>
              <span className={cn("rounded px-1.5 font-mono text-xs", b.destroyed ? "bg-surface-3 text-text-2" : "bg-st-running/12 text-st-running")}>
                {b.destroyed ? "destroyed" : "running"}
              </span>
            </p>
            {b.image && <p className="mt-0.5 font-mono text-xs text-text-2">{b.image}</p>}
            {b.screenshots.map((s) => (
              <div key={s} className="mt-1.5">
                <ArtifactImage artifact={s} />
              </div>
            ))}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Knowledge changed under the agents' feet: shown prominently on purpose (the invalidation demo). */
export function InvalidationBanner({ view }: { view: TaskView }) {
  if (!view.invalidations.length) return null;
  return (
    <div className="rounded-xl border border-st-waiting/60 bg-st-waiting/10 p-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-st-waiting">
        <Brain className="size-4" aria-hidden /> Memory invalidated
      </h2>
      {view.invalidations.map((e) => (
        <div key={e.event_id} className="mt-2 space-y-1 text-sm">
          <EvidenceChip path={str(e, "source") ?? ""} />
          <p className="text-xs text-text-2">
            {strList(e, "invalidated").length} memories marked stale · affected agents: {strList(e, "affected_agents").join(", ") || "none"}
          </p>
        </div>
      ))}
    </div>
  );
}

