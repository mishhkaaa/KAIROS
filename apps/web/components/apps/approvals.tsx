"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { useClient } from "@/app/providers";
import { ApprovalCard, approvalHeadline } from "@/components/approval-card";
import { PidChip, RiskBadge, formatTime } from "@/components/status";
import { cn } from "@/lib/utils";

export function ApprovalsApp() {
  const client = useClient();
  const [tab, setTab] = useState<"pending" | "history">("pending");
  const all = useQuery({ queryKey: ["approvals", "all"], queryFn: () => client.approvals(), refetchInterval: 2_000 });
  const approvals = [...(all.data ?? [])].sort((a, b) => (b.requested_at ?? "").localeCompare(a.requested_at ?? ""));
  const pending = approvals.filter((a) => (a.status ?? "pending") === "pending");
  const resolved = approvals.filter((a) => (a.status ?? "pending") !== "pending");

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">Approvals</h1>
        <p className="mt-1 text-sm text-text-2">
          Privileged syscalls that policy routed to a human. Each card shows the documents that justify the action.
        </p>
      </div>

      <div role="tablist" aria-label="Approvals" className="flex gap-1 border-b border-line">
        {(["pending", "history"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            type="button"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={cn(
              "-mb-px border-b-2 px-3 pb-2 text-sm font-medium capitalize",
              tab === t ? "border-brand text-foreground" : "border-transparent text-text-2 hover:text-foreground",
            )}
          >
            {t} <span className="font-mono">({t === "pending" ? pending.length : resolved.length})</span>
          </button>
        ))}
      </div>

      {all.isError && (
        <div className="flex items-center justify-between rounded-xl border border-st-failed/50 bg-st-failed/8 p-4 text-sm text-st-failed">
          <span>Gateway unreachable: {String(all.error)}</span>
          <button
            type="button"
            onClick={() => all.refetch()}
            className="rounded-md border border-line px-3 py-1.5 text-sm text-foreground hover:bg-surface-3"
          >
            Retry
          </button>
        </div>
      )}

      {tab === "pending" ? (
        <section aria-label="Pending approvals" className="space-y-5">
          {all.isSuccess && pending.length === 0 && (
            <div className="rounded-xl border border-line bg-surface-1 px-4 py-8 text-center shadow-panel">
              <p className="text-sm font-medium text-text-2">Nothing is waiting for your decision.</p>
              <p className="mt-1 text-xs text-muted-foreground">Pending approvals appear here when an agent requests a privileged action.</p>
            </div>
          )}
          {pending.map((a) => (
            <div key={a.approval_id} className="space-y-1.5">
              <Link href={`/tasks/${a.task_id}`} className="font-mono text-xs text-text-2 hover:text-foreground">
                task {a.task_id} →
              </Link>
              <ApprovalCard approval={a} />
            </div>
          ))}
        </section>
      ) : (
        <ul aria-label="Resolved approvals" className="divide-y divide-line rounded-xl border border-line bg-surface-1">
          {resolved.length === 0 && (
            <li className="px-4 py-8 text-center">
              <p className="text-sm text-text-2">No resolved approvals yet.</p>
            </li>
          )}
          {resolved.map((a) => (
            <li key={a.approval_id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
              <span className="w-20 font-mono text-xs text-text-2">{formatTime(a.resolved_at ?? a.requested_at)}</span>
              <span className="min-w-0 flex-1 truncate">{approvalHeadline(a)}</span>
              <PidChip pid={a.pid} />
              <RiskBadge risk={a.syscall.risk} />
              <span className={cn("font-semibold", a.status === "approved" ? "text-st-running" : "text-st-failed")}>
                {a.status}
                {a.resolved_by ? ` by ${a.resolved_by}` : ""}
              </span>
              <Link href={`/tasks/${a.task_id}`} className="font-mono text-xs text-text-2 hover:text-foreground">
                {a.task_id}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
