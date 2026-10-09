"use client";

import type { Approval } from "@kairos/contracts";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { useClient } from "@/app/providers";
import { approvalHeadline } from "@/components/approval-card";
import { RiskBadge } from "@/components/status";
import { KairosError } from "@/lib/kairos-client";
import { usePendingApprovals } from "./hooks";
import { Orb } from "./orb";

/** Pending approvals as system notifications, top right. Hidden for the task whose window is in front (its approval
 *  drawer is already open there). */
export function Notifications({ focusedTask }: { focusedTask?: string }) {
  const pending = usePendingApprovals().data ?? [];
  const [dismissed, setDismissed] = useState<string[]>([]);
  const shown = pending.filter((a) => !dismissed.includes(a.approval_id) && a.task_id !== focusedTask).slice(0, 3);
  if (!shown.length) return null;
  return (
    <div aria-live="polite" className="pointer-events-none absolute top-3 right-3 z-[6000] flex w-[min(380px,calc(100vw-24px))] flex-col gap-2">
      {shown.map((a) => (
        <ApprovalNotice key={a.approval_id} a={a} onDismiss={() => setDismissed((d) => [...d, a.approval_id])} />
      ))}
    </div>
  );
}

function ApprovalNotice({ a, onDismiss }: { a: Approval; onDismiss: () => void }) {
  const client = useClient();
  const qc = useQueryClient();
  const resolve = useMutation({
    mutationFn: (approve: boolean) => (approve ? client.approve(a.approval_id, "approved from a desktop notification") : client.reject(a.approval_id, "rejected from a desktop notification")),
    onSuccess: (_, approve) => toast.success(approve ? "Approved" : "Rejected", { description: a.syscall.capability }),
    onError: (e) => toast.error("Couldn't send your decision", { description: e instanceof KairosError ? e.message : String(e) }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
  });
  return (
    <section aria-label="Approval needed" className="notice-in pointer-events-auto rounded-[12px] border border-st-waiting/60 bg-surface-1 p-3 shadow-window">
      <div className="flex items-start gap-3">
        <Orb state="breathing" size={32} label="waiting for you" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-st-waiting">Approval needed</p>
          <p className="mt-0.5 text-sm font-medium leading-snug">{approvalHeadline(a)}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 font-mono text-xs text-text-2">
            {a.syscall.capability} <RiskBadge risk={a.syscall.risk} />
          </p>
        </div>
        <button type="button" onClick={onDismiss} aria-label="Dismiss" className="win-btn">
          <X className="size-3.5" />
        </button>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <Link href={`/tasks/${a.task_id}`} className="mr-auto text-sm text-brand hover:underline">
          Review evidence
        </Link>
        <button type="button" disabled={resolve.isPending} onClick={() => resolve.mutate(false)} className="h-8 rounded-md border border-line px-3 text-sm hover:bg-surface-3 disabled:opacity-50">
          Reject
        </button>
        <button type="button" disabled={resolve.isPending} onClick={() => resolve.mutate(true)} className="h-8 rounded-md bg-brand px-3 text-sm font-semibold text-[var(--on-brand)] hover:bg-brand-hover disabled:opacity-50">
          Approve
        </button>
      </div>
    </section>
  );
}
