"use client";

import type { Approval } from "@kairos/contracts";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, FileSearch, KeyRound, ShieldCheck, Undo2, X } from "lucide-react";
import { Orb } from "@/components/desktop/orb";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useClient } from "@/app/providers";
import { useSession } from "@/components/session";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { KairosError } from "@/lib/kairos-client";
import { cn } from "@/lib/utils";
import { EvidenceChip, PidChip, RiskBadge, formatTime } from "./status";

const VERB: Record<string, string> = { write: "write to", read: "read from", delete: "delete from", open: "open", exec: "run code in", send: "send via" };
const TARGET: Record<string, string> = { jira: "Jira", fs: "the file system", browser: "a web page", email: "email", slack: "Slack" };

/** "action-agent#105 wants to write to Jira" from the capability (jira.write). */
export function approvalHeadline(a: Approval): string {
  const [tool, op] = a.syscall.capability.split(".");
  const verb = VERB[op];
  const target = TARGET[tool] ?? tool;
  return `${a.agent}#${a.pid} wants ${verb ? `to ${verb} ${target}` : a.syscall.capability}`;
}

/** Renders JSON with light syntax colouring (keys, strings, numbers) without a dependency. */
function JsonView({ value }: { value: unknown }) {
  const json = JSON.stringify(value ?? {}, null, 2);
  const parts = json.split(/("(?:\\.|[^"\\])*"(?:\s*:)?|\b-?\d+(?:\.\d+)?\b|\btrue\b|\bfalse\b|\bnull\b)/g);
  return (
    <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line bg-surface-2 p-3 font-mono text-[13px] leading-relaxed">
      {parts.map((p, i) => {
        if (/^".*":$/.test(p.replace(/\s/g, ""))) return <span key={i} className="text-ev-knowledge">{p}</span>;
        if (p.startsWith('"')) return <span key={i} className="text-st-running">{p}</span>;
        if (/^(-?\d|true|false|null)/.test(p)) return <span key={i} className="text-st-waiting">{p}</span>;
        return <span key={i}>{p}</span>;
      })}
    </pre>
  );
}

function Section({ label, icon: Icon, children }: { label: string; icon?: typeof KeyRound; children: React.ReactNode }) {
  return (
    <section>
      <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {Icon && <Icon className="size-3.5" aria-hidden />} {label}
      </h4>
      <div className="mt-1.5">{children}</div>
    </section>
  );
}

export function ApprovalCard({
  approval,
  flaggedPaths = [],
  onShown,
  onResolved,
}: {
  approval: Approval;
  flaggedPaths?: string[];
  compact?: boolean;
  onShown?: (approvalId: string) => void;
  onResolved?: (approvalId: string) => void;
}) {
  const client = useClient();
  const qc = useQueryClient();
  const { me, can } = useSession();
  const [comment, setComment] = useState("");
  const sc = approval.syscall;
  const pending = (approval.status ?? "pending") === "pending";
  useEffect(() => {
    onShown?.(approval.approval_id);
  }, [onShown, approval.approval_id]);

  const resolve = useMutation({
    mutationFn: (approve: boolean) =>
      approve ? client.approve(approval.approval_id, comment || undefined) : client.reject(approval.approval_id, comment || undefined),
    onSuccess: (a) => {
      onResolved?.(a.approval_id);
      if (a.status === "approved") toast.success(`Approved ${a.approval_id}`, { description: `${sc.capability} runs now; the task continues.` });
      else toast(`Rejected ${a.approval_id}`, { description: "The syscall is refused; the agent is told why." });
    },
    onError: (e) => {
      if (e instanceof KairosError && e.code === "APPROVAL_ALREADY_RESOLVED") {
        toast.info("Already resolved", { description: "Someone else (or the phone) resolved this approval first." });
      } else {
        toast.error("Couldn't resolve the approval", { description: e instanceof KairosError ? e.message : String(e) });
      }
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
  });

  return (
    <article
      className={cn(
        "rounded-xl border bg-surface-1 p-5 shadow-panel",
        pending ? "border-st-waiting/70" : "border-line",
      )}
      data-testid="approval-card"
    >
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs text-text-2">
          <span>{approval.approval_id}</span>
          {approval.requested_at && <span>· requested {formatTime(approval.requested_at)}</span>}
          {!pending && (
            <span className={approval.status === "approved" ? "text-st-running" : "text-st-failed"}>
              · {approval.status}
              {approval.resolved_by && ` by ${approval.resolved_by}`}
            </span>
          )}
        </div>
        <h3 className="text-xl font-semibold leading-snug">{approvalHeadline(approval)}</h3>
        <div className="flex flex-wrap items-center gap-2">
          <PidChip pid={approval.pid} agent={approval.agent} />
          <RiskBadge risk={sc.risk} />
        </div>
      </header>

      <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
        <dt className="text-text-2">Capability</dt>
        <dd className="font-mono font-semibold text-brand">{sc.capability}</dd>
        <dt className="text-text-2">Operation</dt>
        <dd className="font-mono">{sc.tool}.{sc.operation}</dd>
        <dt className="text-text-2">Target</dt>
        <dd className="font-mono">{sc.resource ?? String((sc.arguments as Record<string, unknown> | undefined)?.key ?? "—")}</dd>
      </dl>

      <div className="mt-4 space-y-4">
        <Section label="Policy" icon={ShieldCheck}>
          <p className="text-sm">
            <span className="font-mono font-semibold text-brand">{approval.decision.policy}</span>
            <span className="text-text-2"> · {approval.decision.reason}</span>
          </p>
          {!!approval.decision.matched_rules?.length && (
            <p className="mt-0.5 font-mono text-xs text-text-2">rules: {approval.decision.matched_rules.join(", ")}</p>
          )}
        </Section>
        {sc.justification && (
          <Section label="Justification">
            <blockquote className="border-l-2 border-brand pl-3 text-[15px]">{sc.justification}</blockquote>
          </Section>
        )}
        <Section label="Arguments" icon={KeyRound}>
          <JsonView value={sc.arguments} />
        </Section>
        <Section label={`Evidence (${sc.evidence?.length ?? 0})`} icon={FileSearch}>
          {sc.evidence?.length ? (
            <div className="flex flex-wrap gap-1.5">
              {sc.evidence.map((p) => (
                <EvidenceChip key={p} path={p} flagged={flaggedPaths.includes(p)} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-st-waiting">No evidence cited for this action.</p>
          )}
        </Section>
      </div>

      {pending && !can("approval.resolve") ? (
        <p className="mt-5 flex items-center gap-2 rounded-xl border border-dashed border-line bg-surface-2 px-3 py-2.5 text-sm text-text-2">
          <ShieldCheck className="size-4 shrink-0" aria-hidden />
          Waiting for an approver. Your role ({me?.role ?? "none"}) can see this request but not decide it.
        </p>
      ) : pending ? (
        <footer className="mt-5 space-y-3">
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Comment (optional, recorded in the audit journal)"
            aria-label="Comment"
            className="min-h-16 text-sm"
          />
          <div className="flex gap-3">
            <Button
              size="lg"
              className="h-12 flex-1 bg-st-running text-base font-semibold text-white hover:bg-st-running/90 dark:text-black"
              disabled={resolve.isPending}
              onClick={() => resolve.mutate(true)}
            >
              {resolve.isPending && resolve.variables ? <Orb state="solving" label="Sending your decision" /> : <Check className="size-5" />}
              Approve
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="h-12 flex-1 border-st-failed/60 text-base font-semibold text-st-failed hover:bg-st-failed/10 hover:text-st-failed"
              disabled={resolve.isPending}
              onClick={() => resolve.mutate(false)}
            >
              {resolve.isPending && resolve.variables === false ? <Orb state="solving" label="Sending your decision" /> : <X className="size-5" />}
              Reject
            </Button>
          </div>
          <p className="flex items-center gap-1.5 text-xs text-text-2">
            <Undo2 className="size-3.5" aria-hidden /> The action runs in a transaction: verify → commit, or automatic rollback.
          </p>
        </footer>
      ) : (
        approval.comment && <p className="mt-4 text-sm text-text-2">Comment: “{approval.comment}”</p>
      )}
    </article>
  );
}
