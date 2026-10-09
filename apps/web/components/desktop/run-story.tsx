"use client";

import {
  BellRing,
  BookOpenText,
  CircleCheck,
  CircleX,
  Cpu,
  Database,
  Flag,
  GitFork,
  Gauge,
  Globe,
  Lightbulb,
  type LucideIcon,
  MessageCircle,
  MessageSquareText,
  Route,
  Send,
  ShieldCheck,
  Table2,
} from "lucide-react";
import Link from "next/link";
import { useTheme } from "next-themes";
import { useEffect, useMemo, useRef } from "react";
import type { TaskView } from "@/lib/events";
import { folderHue } from "@/lib/desktop/palette";
import { buildStory, type Step, type StepKind } from "@/lib/desktop/story";
import { cn } from "@/lib/utils";
import { AgentAvatar } from "./agent-avatar";
import { BigOrb } from "./big-orb";
import { TypingDots } from "./typing-dots";
import type { OrbState } from "thinking-orbs";

const KIND: Record<StepKind, [LucideIcon, string, OrbState]> = {
  ask: [MessageSquareText, "#0e9f86", "listening"],
  understood: [Lightbulb, "#7b61ff", "shaping"],
  routed: [Gauge, "#e2a63b", "solving"],
  planned: [Route, "#00b3c7", "connecting"],
  created: [GitFork, "#16b67a", "shaping"],
  thought: [MessageCircle, "#c56cf0", "composing"],
  read: [BookOpenText, "#2f7cf6", "searching"],
  think: [Cpu, "#7b61ff", "composing"],
  message: [Send, "#14a89a", "weaving"],
  kernel: [ShieldCheck, "#5c6bc0", "solving"],
  approval: [BellRing, "#f5a623", "breathing"],
  committed: [CircleCheck, "#16b67a", "working"],
  sandbox: [Globe, "#ff8a3d", "connecting"],
  query: [Database, "#00b3c7", "solving"],
  data: [Table2, "#0e9f86", "working"],
  done: [Flag, "#16b67a", "breathing"],
  failed: [CircleX, "#ff5a5f", "breathing"],
};

const docName = (p: string) => p.split("/").pop()?.replaceAll("-", " ") ?? p;

export function DocChip({ path, flagged }: { path: string; flagged?: boolean }) {
  return (
    <Link
      href={`/knowledge?path=${encodeURIComponent(path)}`}
      title={flagged ? `${path}: flagged by the context firewall, treated as data` : path}
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs transition-colors hover:bg-surface-3",
        flagged ? "border-st-failed/60 bg-untrusted-bg text-untrusted" : "border-hairline bg-surface-1",
      )}
    >
      <span className="size-2 shrink-0 rounded-full" style={{ background: flagged ? "var(--st-failed)" : folderHue(path) }} aria-hidden />
      <span className="truncate">{docName(path)}</span>
      {flagged && <span className="font-semibold">untrusted</span>}
    </Link>
  );
}

export function DataTable({ columns, rows }: { columns: string[]; rows: unknown[][] }) {
  return (
    <div className="mt-2 max-h-72 overflow-auto rounded-lg border border-hairline">
      <table className="w-full text-left text-xs tabular-nums">
        <thead className="sticky top-0 bg-surface-2">
          <tr>
            {columns.map((c) => (
              <th key={c} className="px-2.5 py-1.5 font-mono font-semibold">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 200).map((r, i) => (
            <tr key={i} className="border-t border-hairline">
              {r.map((v, j) => (
                <td key={j} className="px-2.5 py-1">
                  {String(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Jev's probability per agent, with the spawn line at 0.5. */
export function RouteBars({ scores }: { scores: NonNullable<Step["scores"]> }) {
  return (
    <ul className="mt-2 space-y-1" aria-label="Probability that each agent is needed">
      {scores.map((r) => (
        <li key={r.role} className="grid grid-cols-[8.5rem_1fr_2.5rem] items-center gap-2 text-xs">
          <span className={cn("truncate", r.on ? "font-medium" : "text-text-2")}>{r.role.replace(/-agent$/, "")}</span>
          <span className="relative h-2 rounded-full bg-surface-3">
            <span className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-500" style={{ width: `${Math.round(r.p * 100)}%`, background: r.on ? "#0e9f86" : "var(--text-3, #9aa3b2)" }} />
            <span className="absolute -inset-y-1 left-1/2 border-l border-dashed border-[#e2a63b]" aria-hidden />
          </span>
          <span className={cn("text-right font-mono tabular-nums", r.on ? "" : "text-text-2")}>{r.p.toFixed(2)}</span>
        </li>
      ))}
    </ul>
  );
}

function StepRow({ step }: { step: Step }) {
  const [Icon, colour] = KIND[step.kind];
  return (
    <li className="stage-in relative flex gap-3 pb-4 pl-1" data-status={step.status}>
      <span
        className={cn("relative z-10 mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full text-white shadow-sm", step.status === "active" && "ring-4")}
        style={{ background: step.status === "error" ? "#ff5a5f" : colour, ["--tw-ring-color" as string]: `${colour}33` }}
        aria-hidden
      >
        <Icon className="size-3.5" strokeWidth={2.4} />
      </span>
      <div className={cn("min-w-0 flex-1 rounded-xl px-3 py-2", step.status === "active" ? "bg-surface-2 shadow-window-idle" : step.status === "waiting" ? "bg-st-waiting/10" : "")}>
        <p className={cn("text-[14px] leading-snug", step.kind === "thought" ? "italic text-text-2" : "font-semibold")}>
          {step.title}
          {step.status === "active" && (step.kind === "think" || step.kind === "thought") && <TypingDots className="ml-2 align-middle text-[#8b5cf6]" />}
        </p>
        {step.detail && <p className="mt-0.5 line-clamp-3 text-xs text-text-2">{step.detail}</p>}
        {!!step.paths?.length && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {step.paths.slice(0, 8).map((p) => (
              <DocChip key={p} path={p} flagged={step.flagged?.includes(p)} />
            ))}
            {step.paths.length > 8 && <span className="self-center text-xs text-text-2">+{step.paths.length - 8} more</span>}
          </div>
        )}
        {!!step.flagged?.length && <p className="mt-1.5 text-xs font-medium text-untrusted">The firewall flagged instruction-like text: agents read it as data, never as instructions.</p>}
        {step.code && (
          <pre className="mt-2 overflow-x-auto rounded-lg border border-hairline bg-surface-2 px-3 py-2 font-mono text-xs leading-relaxed">
            <span className="select-none text-brand">sql&gt; </span>
            {step.code}
          </pre>
        )}
        {step.table && <DataTable columns={step.table.columns} rows={step.table.rows} />}
        {!!step.scores?.length && <RouteBars scores={step.scores} />}
      </div>
    </li>
  );
}

/** The run as a story, newest at the bottom, with the step happening now under a large orb. */
export function RunStory({ view }: { view: TaskView }) {
  const { resolvedTheme } = useTheme();
  const agents = useMemo(() => Object.fromEntries(Object.values(view.processes).map((p) => [p.pid, p.agent])), [view.processes]);
  const steps = useMemo(() => buildStory(view.timeline, agents, view.status), [view.timeline, agents, view.status]);
  const now = steps.findLast((s) => s.status === "active" || s.status === "waiting");
  const nowProc = now?.pid ? view.processes[now.pid] : undefined;
  const end = useRef<HTMLLIElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [steps.length]);

  return (
    <div className="space-y-4">
      {now && (
        <section aria-live="polite" className="panel flex items-center gap-4 rounded-2xl p-4">
          <BigOrb state={KIND[now.kind][2]} size={96} dark={resolvedTheme === "dark"} />
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-brand">{now.status === "waiting" ? "Waiting for you" : "Now"}</p>
            <p className="mt-0.5 text-base font-semibold leading-snug">
              {now.title}
              {(now.kind === "think" || now.kind === "thought") && <TypingDots className="ml-2 align-middle text-[#8b5cf6]" />}
            </p>
            {now.detail && <p className="mt-0.5 line-clamp-2 text-sm text-text-2">{now.detail}</p>}
          </div>
          {nowProc && <AgentAvatar agent={nowProc.agent} state={nowProc.state} size={64} />}
        </section>
      )}
      <ol className="relative before:absolute before:top-2 before:bottom-4 before:left-[17px] before:w-px before:bg-hairline" aria-label="What KAIROS did">
        {steps.map((s) => (
          <StepRow key={s.id} step={s} />
        ))}
        <li ref={end} aria-hidden />
      </ol>
      {!steps.length && <p className="text-sm text-text-2">Starting…</p>}
    </div>
  );
}
