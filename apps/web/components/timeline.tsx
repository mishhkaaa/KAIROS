"use client";

import type { Event } from "@kairos/contracts";
import { ChevronRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { EMPHASISED, FAMILY_TEXT, describeEvent, type Family } from "@/lib/describe";
import { type Retrieval, strList } from "@/lib/events";
import { cn } from "@/lib/utils";
import { EvidenceChip, PidChip, UntrustedBadge, formatTime, offset } from "./status";

/** Kept for existing imports; the chips live in ./status. */
export const FlagBadge = UntrustedBadge;
export const EvidencePath = EvidenceChip;

// Chatty events that add little on a projector; one click shows them.
const NOISE = new Set(["process.usage", "audit.appended", "tool.started", "syscall.completed", "system.health"]);
// Every real process walks CREATED → INITIALIZING → READY → RUNNING in its first milliseconds.
const BOOT = new Set(["INITIALIZING", "READY"]);
export const isNoise = (e: Event) =>
  NOISE.has(e.type) ||
  (e.type === "process.state_changed" &&
    (BOOT.has(String(e.payload?.new)) || (e.payload?.old === "READY" && e.payload?.new === "RUNNING")));

const RULE: Partial<Record<Family, string>> = {
  syscall: "border-l-brand bg-brand-subtle/40",
  policy: "border-l-brand bg-brand-subtle/40",
  approval: "border-l-st-waiting bg-st-waiting/8",
  warning: "border-l-st-waiting bg-st-waiting/6",
  transaction: "border-l-st-running bg-st-running/8",
  danger: "border-l-st-failed bg-st-failed/8",
};

function Row({ e, retrieval, start }: { e: Event; retrieval?: Retrieval; start?: string | null }) {
  const [openState, setOpen] = useState<boolean | null>(null);
  const line = describeEvent(e);
  const Icon = line.icon;
  const emphasised = EMPHASISED.includes(line.family);
  const expandable = e.type === "knowledge.retrieved";
  const paths = expandable ? strList(e, "paths") : [];
  const flagged = retrieval?.flagged ?? [];
  const extraFlagged = flagged.filter((p) => !paths.includes(p));
  const open = openState ?? flagged.length > 0; // a flagged retrieval opens by itself: the demo's firewall moment

  return (
    <li className={cn("row-in rounded-md border-l-2 border-l-transparent px-2 py-1.5", RULE[line.family])}>
      <button
        type="button"
        disabled={!expandable}
        aria-expanded={expandable ? open : undefined}
        onClick={() => setOpen(!open)}
        className="flex w-full items-start gap-2 text-left disabled:cursor-default"
      >
        <span className="mt-0.5 w-14 shrink-0 text-right font-mono text-xs text-muted-foreground" title={formatTime(e.ts)}>
          {offset(e.ts, start) || formatTime(e.ts)}
        </span>
        <Icon className={cn("mt-0.5 size-4 shrink-0", FAMILY_TEXT[line.family])} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <PidChip pid={e.pid} />
            <span className={cn("text-sm leading-snug", emphasised && "font-medium", FAMILY_TEXT[line.family])}>{line.title}</span>
            {flagged.length > 0 && <UntrustedBadge />}
          </span>
          {line.detail && <span className="mt-0.5 block truncate text-xs text-text-2">{line.detail}</span>}
        </span>
        {expandable && (
          <ChevronRight className={cn("mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform duration-150", open && "rotate-90")} aria-hidden />
        )}
      </button>
      {expandable && open && (
        <div className="ml-[5.5rem] mt-1.5 space-y-1">
          {[...paths.map((p) => [p, flagged.includes(p)] as const), ...extraFlagged.map((p) => [p, true] as const)].map(([p, f]) => (
            <div key={p} className="flex flex-wrap items-center gap-2">
              <EvidenceChip path={p} flagged={f} />
              {f && <span className="text-xs text-untrusted">treated as data, not instructions</span>}
            </div>
          ))}
        </div>
      )}
    </li>
  );
}

export function Timeline({ events, retrieved, start }: { events: Event[]; retrieved: Retrieval[]; start?: string | null }) {
  const [showNoise, setShowNoise] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const byEvent = new Map(retrieved.map((r) => [r.event, r]));
  const shown = showNoise ? events : events.filter((e) => !isNoise(e));
  const t0 = start ?? events[0]?.ts;

  useEffect(() => {
    if (pinned.current) bottom.current?.scrollIntoView({ block: "end" });
  }, [shown.length]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between px-1 pb-2">
        <h2 className="text-[17px] font-semibold">Timeline</h2>
        <button
          type="button"
          onClick={() => setShowNoise((s) => !s)}
          className="rounded px-1 text-xs text-text-2 underline-offset-2 hover:text-foreground hover:underline"
        >
          {showNoise ? "hide" : "show"} low-level ({events.length - events.filter((e) => !isNoise(e)).length})
        </button>
      </div>
      <div
        onScroll={(ev) => {
          const el = ev.currentTarget;
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
        className="min-h-0 flex-1 overflow-y-auto pr-1"
      >
        {shown.length === 0 ? (
          <p className="px-2 py-6 text-sm text-muted-foreground">Waiting for events…</p>
        ) : (
          <ol className="space-y-0.5" aria-live="polite">
            {shown.map((e, i) => (
              <Row key={e.event_id ?? i} e={e} retrieval={byEvent.get(e)} start={t0} />
            ))}
          </ol>
        )}
        <div ref={bottom} />
      </div>
    </div>
  );
}
