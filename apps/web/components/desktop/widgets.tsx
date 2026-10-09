"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSyncExternalStore } from "react";
import { useClient } from "@/app/providers";
import { approvalHeadline } from "@/components/approval-card";
import { TaskStatusBadge, duration } from "@/components/status";
import { byNewest } from "@/components/task-row";
import { isActive } from "@/lib/events";
import { firstName, useSession } from "@/components/session";
import { cn } from "@/lib/utils";
import { AppTile } from "./app-icons";
import { useAllDocs, useModels, usePendingApprovals, useResources, useTasks } from "./hooks";
import { Orb } from "./orb";

const subscribe = (tick: () => void) => {
  const t = setInterval(tick, 60_000);
  return () => clearInterval(t);
};
const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
};

/** The empty desktop's way in, centred on the kairos: a greeting, one line on the state of the system, the Ask bar. */
export function Hero({ onAsk, compact }: { onAsk: () => void; compact: boolean }) {
  const client = useClient();
  const { me, can } = useSession();
  const hello = useSyncExternalStore(subscribe, greeting, () => "Hello");
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => client.status(), refetchInterval: 15_000 });
  const agents = useQuery({ queryKey: ["registry-agents"], queryFn: () => client.registry(), staleTime: 60_000 });
  const models = useModels().data ?? [];
  const docs = useAllDocs().data ?? [];
  const gpu = useResources().data?.gpu;
  // The local chat model that does the reasoning: skip vision-only models (llava) and prefer the larger instruct model.
  const chatModels = models.filter((m) => m.local !== false && m.available !== false && m.capabilities?.includes("chat") && !m.capabilities?.includes("vision"));
  const chat = (chatModels.find((m) => /instruct/.test(m.name)) ?? chatModels[0])?.name?.replace(/:.*$/, "");
  const facts = [
    status.data ? (status.data.ready ? "kernel ready" : "kernel starting") : "kernel …",
    `${docs.length} documents at /org`,
    `${agents.data?.length ?? "…"} agents`,
    chat ? `${chat} local` : null,
    gpu ? gpu.name.replace(/^NVIDIA GeForce /, "") : null,
  ].filter(Boolean);
  return (
    <div className="w-full max-w-[680px] text-center">
      <h1 className={cn("font-semibold tracking-[-0.03em] text-foreground", compact ? "text-4xl" : "text-[52px] leading-[1.05]")}>
        {hello}, {firstName(me)}.
      </h1>
      <p className="mt-3 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 font-mono text-[13px] text-text-2" aria-label="System">
        <span className={cn("size-2 rounded-full", status.data?.ready ? "bg-st-running" : "bg-st-waiting")} aria-hidden />
        {facts.map((f, i) => (
          <span key={i} className="flex items-center gap-2">
            {i > 0 && <span className="text-text-2/50">/</span>}
            {f}
          </span>
        ))}
      </p>
      <button
        type="button"
        onClick={onAsk}
        className="panel group mt-7 flex h-16 w-full items-center gap-3 rounded-2xl px-5 text-left transition-transform duration-200 hover:-translate-y-0.5 active:translate-y-0"
        aria-label="Ask KAIROS (Alt Space)"
      >
        <Orb state="breathing" size={32} label="KAIROS" />
        <span className="flex-1 text-lg text-text-2">{can("task.create") ? "What should KAIROS work on?" : "Search your organization's knowledge"}</span>
        <kbd className="rounded-md border border-hairline bg-surface-2 px-2 py-0.5 font-mono text-xs text-text-2">Alt Space</kbd>
      </button>
    </div>
  );
}

function Widget({ title, tint, href, children }: { title: string; tint: string; href: string; children: React.ReactNode }) {
  return (
    <section className="panel stage-in rounded-2xl p-3.5">
      <Link href={href} className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold hover:underline" style={{ color: tint }}>
        {title}
      </Link>
      {children}
    </section>
  );
}

/** Desktop widgets, macOS-style: running work, what needs you, the machine, the knowledge. */
export function Widgets() {
  const client = useClient();
  const tasks = [...(useTasks().data ?? [])].sort(byNewest);
  const pending = usePendingApprovals().data ?? [];
  const res = useResources().data;
  const docs = useAllDocs().data ?? [];
  const valid = useQuery({ queryKey: ["knowledge-validate"], queryFn: () => client.validate(), staleTime: 5 * 60_000 });
  const running = tasks.filter((t) => isActive(t.status));
  const shown = (running.length ? running : tasks).slice(0, 3);
  const folders = new Set(docs.map((d) => d.path.split("/")[2])).size;
  const gpu = res?.gpu;
  const bar = (label: string, pct: number, text: string) => (
    <div>
      <div className="flex justify-between text-xs">
        <span className="text-text-2">{label}</span>
        <span className="font-mono tabular-nums">{text}</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-3">
        <div className={cn("h-full rounded-full", pct > 90 ? "bg-st-failed" : "bg-gradient-to-r from-[#14b8a6] to-[#3b82f6]")} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
    </div>
  );

  return (
    <div className="flex w-[300px] flex-col gap-3">
      <Widget title={running.length ? `Running now · ${running.length}` : "Recent tasks"} tint="#0e9f86" href="/tasks">
        <ul className="space-y-2">
          {shown.map((t) => (
            <li key={t.task_id}>
              <Link href={`/tasks/${t.task_id}`} className="flex items-center gap-2 rounded-lg p-1 hover:bg-black/5 dark:hover:bg-white/5">
                {isActive(t.status) ? <Orb state="working" label="running" /> : <AppTile app="task" size={20} />}
                <span className="min-w-0 flex-1 truncate text-sm">{t.goal}</span>
                {isActive(t.status) ? <span className="font-mono text-xs text-text-2">{duration(t.created_at, null)}</span> : <TaskStatusBadge status={t.status} />}
              </Link>
            </li>
          ))}
          {!shown.length && <li className="text-sm text-text-2">No tasks yet. Press Alt Space.</li>}
        </ul>
      </Widget>

      <Widget title={pending.length ? `Needs you · ${pending.length}` : "Needs you"} tint="#f5860f" href="/approvals">
        {pending.length ? (
          <Link href={`/tasks/${pending[0].task_id}`} className="block rounded-lg bg-st-waiting/10 p-2 text-sm font-medium hover:bg-st-waiting/15">
            {approvalHeadline(pending[0])}
          </Link>
        ) : (
          <p className="text-sm text-text-2">Nothing is waiting for a decision.</p>
        )}
      </Widget>

      <Widget title="This machine" tint="#e5484d" href="/system">
        <div className="space-y-2">
          {gpu && bar(`GPU · ${gpu.name.replace(/^NVIDIA GeForce /, "")}`, (100 * gpu.memory_used_mb) / Math.max(1, gpu.memory_total_mb), `${(gpu.memory_used_mb / 1024).toFixed(1)} GB`)}
          {res && bar("CPU", res.cpu_percent, `${res.cpu_percent.toFixed(0)}%`)}
          {res && bar("Memory", (100 * res.ram_used_mb) / Math.max(1, res.ram_total_mb), `${(res.ram_used_mb / 1024).toFixed(0)} GB`)}
          {!res && <p className="text-sm text-text-2">Reading the machine…</p>}
        </div>
      </Widget>

      <Widget title="Knowledge" tint="#2563eb" href="/knowledge">
        <p className="text-sm">
          <span className="font-mono text-2xl font-semibold tabular-nums">{docs.length}</span> documents in <span className="font-mono">{folders}</span> folders
        </p>
        <p className="mt-0.5 text-xs text-text-2">{valid.data ? (valid.data.ok ? "bundle valid" : `${valid.data.issues?.length ?? 0} issues`) : "checking…"}</p>
      </Widget>
    </div>
  );
}
