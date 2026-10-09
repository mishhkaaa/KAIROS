"use client";

import { Loading } from "@/components/desktop/orb";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ScrollText } from "lucide-react";
import Link from "next/link";
import { useClient } from "@/app/providers";
import { TaskStatusBadge, formatTime } from "@/components/status";
import { byNewest } from "@/components/task-row";

/** Audit journals are per task: pick one. */
export function JournalsApp() {
  const client = useClient();
  const tasks = useQuery({ queryKey: ["tasks"], queryFn: () => client.listTasks(), refetchInterval: 5_000 });
  const all = [...(tasks.data ?? [])].sort(byNewest);
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <ScrollText className="size-6 text-brand" aria-hidden /> Audit
        </h1>
        <p className="mt-1 text-sm text-text-2">
          Every model call, knowledge read, IPC message, syscall and approval is written to a hash-chained journal per task.
        </p>
      </div>
      <ul aria-label="Tasks with audit journals" className="divide-y divide-line rounded-xl border border-line bg-surface-1 shadow-panel">
        {tasks.isError && (
          <li className="flex items-center justify-between p-4 text-sm text-st-failed">
            <span>Gateway unreachable: {String(tasks.error)}</span>
            <button
              type="button"
              onClick={() => tasks.refetch()}
              className="rounded-md border border-line px-3 py-1.5 text-sm text-foreground hover:bg-surface-3"
            >
              Retry
            </button>
          </li>
        )}
        {tasks.isLoading && <li><Loading label="Reading the audit journals" /></li>}
        {tasks.isSuccess && all.length === 0 && (
          <li className="px-4 py-8 text-center">
            <p className="text-sm text-text-2">No tasks yet.</p>
            <p className="mt-1 text-xs text-muted-foreground">Run a task from the home page and its journal will appear here.</p>
          </li>
        )}
        {all.map((t) => (
          <li key={t.task_id}>
            <Link href={`/audit/${t.task_id}`} className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-surface-3">
              <TaskStatusBadge status={t.status} className="justify-center @xl:w-[10.5rem]" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">{t.goal}</p>
                <p className="font-mono text-xs text-text-2">
                  {t.task_id} · {formatTime(t.created_at)}
                </p>
              </div>
              <span className="text-sm text-brand">Journal</span>
              <ArrowRight className="size-4 text-text-2" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
