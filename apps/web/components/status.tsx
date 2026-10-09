import { ShieldAlert } from "lucide-react";
import Link from "next/link";
import { agentTone, riskTone, taskTone, type Tone, UNTRUSTED_TONE } from "@/lib/tones";
import { cn } from "@/lib/utils";

function Pill({ tone, label, className, pulse, ...rest }: { tone: Tone; label: string; className?: string; pulse?: boolean; "data-testid"?: string }) {
  return (
    <span
      {...rest}
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border px-2 py-0.5 font-mono text-xs font-semibold uppercase tracking-wide transition-colors duration-150",
        tone.bg,
        tone.border,
        tone.text,
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", tone.dot, pulse && "activity-dot")} aria-hidden />
      {label}
    </span>
  );
}

export const AgentStateBadge = ({ state, className }: { state?: string | null; className?: string }) => (
  <Pill tone={agentTone(state)} label={state ?? "UNKNOWN"} className={className} pulse={state === "RUNNING"} />
);

export const TaskStatusBadge = ({ status, className, ...rest }: { status?: string | null; className?: string; "data-testid"?: string }) => (
  <Pill
    tone={taskTone(status)}
    label={(status ?? "unknown").replaceAll("_", " ")}
    className={className}
    pulse={status === "running" || status === "planning"}
    {...rest}
  />
);

export const PidChip = ({ pid, agent, className }: { pid?: number | null; agent?: string; className?: string }) =>
  pid ? (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-md bg-surface-3 px-1.5 py-0.5 font-mono text-xs font-semibold text-foreground", className)}>
      <span className="text-muted-foreground">PID</span> {pid}
      {agent && <span className="font-normal text-text-2">{agent}</span>}
    </span>
  ) : (
    <span className={cn("inline-flex whitespace-nowrap rounded-md px-1.5 py-0.5 font-mono text-xs text-muted-foreground", className)}>kernel</span>
  );

export const RiskBadge = ({ risk, className }: { risk?: string | null; className?: string }) =>
  risk ? (
    <span className={cn("inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-xs font-bold uppercase tracking-wide", riskTone(risk), className)}>
      risk {risk}
    </span>
  ) : null;

/** Firewall-flagged content: retrieved text that reads like instructions is treated as data, never obeyed. */
export const UntrustedBadge = ({ className }: { className?: string }) => (
  <span
    title="Flagged instruction-like by the context firewall: treated as data, not instructions"
    className={cn("inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-0.5 font-mono text-xs font-bold uppercase tracking-wide", UNTRUSTED_TONE, className)}
  >
    <ShieldAlert className="size-3.5" aria-hidden /> untrusted
  </span>
);

export function EvidenceChip({ path, flagged, className }: { path: string; flagged?: boolean; className?: string }) {
  return (
    <Link
      href={`/knowledge?path=${encodeURIComponent(path)}`}
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-md border px-2 py-0.5 font-mono text-xs transition-colors hover:bg-surface-3",
        flagged ? "border-untrusted/50 text-untrusted" : "border-line bg-surface-2 text-ev-knowledge",
        className,
      )}
    >
      <span className="truncate">{path}</span>
      {flagged && <UntrustedBadge className="px-1 py-0" />}
    </Link>
  );
}

export function formatTime(ts?: string | null) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** "+12.4s" from the task start; used by the timeline and the phone task view. */
export function offset(ts?: string | null, start?: string | null) {
  if (!ts || !start) return "";
  const s = (Date.parse(ts) - Date.parse(start)) / 1000;
  return s < 0 ? "" : s < 100 ? `+${s.toFixed(1)}s` : `+${Math.round(s)}s`;
}

export function duration(from?: string | null, to?: string | null) {
  if (!from) return "";
  const s = Math.max(0, ((to ? Date.parse(to) : Date.now()) - Date.parse(from)) / 1000);
  return s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}
