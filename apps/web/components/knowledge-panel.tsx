"use client";

import { BookOpenText, EyeOff, ShieldAlert, ShieldCheck } from "lucide-react";
import { num, str, strList, type TaskView } from "@/lib/events";
import { EvidencePath } from "./timeline";
import { PidChip } from "./status";

/** Demo steps 4–5: what each agent retrieved, what policy hid, and what the context firewall flagged. */
export function KnowledgePanel({ view }: { view: TaskView }) {
  const hidden = view.retrieved.reduce((n, r) => n + (num(r.event, "filtered_by_policy") ?? 0), 0);
  return (
    <div className="rounded-xl border border-line bg-surface-1 p-3 shadow-panel">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          <BookOpenText className="size-4 text-ev-knowledge" /> Knowledge
        </h2>
        <span className="flex items-center gap-1 text-xs text-muted-foreground" title="Objects removed by scope or privacy">
          <EyeOff className="size-3.5" /> {hidden} hidden by policy
        </span>
      </div>

      {view.flaggedPaths.length > 0 && (
        <div
          className="mt-3 rounded-lg border-2 border-untrusted/70 bg-untrusted-bg p-3"
          role="alert"
          aria-label="Context firewall: instruction-like content detected"
        >
          <div className="flex items-center gap-2">
            <ShieldAlert className="size-5 shrink-0 text-untrusted" aria-hidden />
            <p className="text-sm font-bold uppercase tracking-wide text-untrusted">
              Instruction-like content blocked
            </p>
          </div>
          <p className="mt-1 text-xs text-text-2">
            Retrieved text contained instruction-like patterns. It was passed to agents as quoted data — never obeyed as instructions.
          </p>
          <div className="mt-2 space-y-2">
            {view.flaggedPaths.map((p) => (
              <FirewallHit key={p} path={p} />
            ))}
          </div>
          <div className="mt-2 flex items-center gap-1.5 rounded-md border border-st-running/40 bg-st-running/8 px-2 py-1">
            <ShieldCheck className="size-3.5 shrink-0 text-st-running" aria-hidden />
            <span className="text-xs font-medium text-st-running">treated as data, not instructions</span>
          </div>
        </div>
      )}

      <ul className="mt-3 space-y-2.5">
        {view.retrieved.length === 0 && <li className="text-sm text-muted-foreground">No retrievals yet.</li>}
        {view.retrieved.map((r) => (
          <li key={r.event.event_id ?? r.event.ts} className="space-y-0.5">
            <p className="flex items-center gap-2 text-sm">
              <PidChip pid={r.event.pid} />
              <span className="truncate text-foreground/90" title={str(r.event, "query")}>
                &ldquo;{str(r.event, "query")}&rdquo;
              </span>
            </p>
            <p className="pl-11 text-xs text-text-2">
              {num(r.event, "hits") ?? 0} hits · {num(r.event, "filtered_by_policy") ?? 0} hidden by policy
              {r.flagged.length > 0 && (
                <span className="ml-1 font-semibold text-untrusted"> · {r.flagged.length} flagged</span>
              )}
            </p>
            <div className="pl-9">
              {strList(r.event, "paths").map((p) => (
                <EvidencePath key={p} path={p} flagged={r.flagged.includes(p)} />
              ))}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A single flagged path with its "offending text" treatment label. */
function FirewallHit({ path, detectedBy }: { path: string; detectedBy?: "regex" | "classifier" }) {
  return (
    <div className="rounded-md border border-untrusted/40 bg-untrusted-bg px-2.5 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <ShieldAlert className="size-3.5 shrink-0 text-untrusted" aria-hidden />
        <span className="truncate font-mono text-xs font-semibold text-untrusted">{path}</span>
        {detectedBy && (
          <span className="ml-auto shrink-0 rounded border border-untrusted/40 px-1.5 py-0.5 font-mono text-xs text-untrusted opacity-80">
            {detectedBy === "classifier" ? "caught by classifier" : "caught by regex"}
          </span>
        )}
      </div>
      <p className="mt-0.5 text-xs text-text-2">offending text — treated as data, not instructions</p>
    </div>
  );
}
