// One state/risk/trust → colour map for the whole console. Colours are the tokens in globals.css (both themes).
import type { AgentState, Risk, TaskStatus } from "@kairos/contracts";

export interface Tone {
  text: string;
  bg: string;
  border: string;
  dot: string;
  /** CSS colour for SVG strokes (React Flow edges); follows the theme. */
  stroke: string;
}

// Literal class names so Tailwind's scanner sees them.
export const TONES = {
  running: { text: "text-st-running", bg: "bg-st-running/12", border: "border-st-running/45", dot: "bg-st-running", stroke: "var(--st-running)" },
  waiting: { text: "text-st-waiting", bg: "bg-st-waiting/12", border: "border-st-waiting/50", dot: "bg-st-waiting", stroke: "var(--st-waiting)" },
  paused: { text: "text-st-paused", bg: "bg-st-paused/12", border: "border-st-paused/45", dot: "bg-st-paused", stroke: "var(--st-paused)" },
  failed: { text: "text-st-failed", bg: "bg-st-failed/12", border: "border-st-failed/50", dot: "bg-st-failed", stroke: "var(--st-failed)" },
  completed: { text: "text-st-completed", bg: "bg-st-completed/10", border: "border-st-completed/40", dot: "bg-st-completed", stroke: "var(--st-completed)" },
  terminated: { text: "text-st-terminated-fg", bg: "bg-st-terminated", border: "border-st-terminated", dot: "bg-st-terminated-fg", stroke: "var(--st-terminated)" },
  checkpoint: { text: "text-st-paused", bg: "bg-st-paused/12", border: "border-st-paused/45", dot: "bg-st-paused", stroke: "var(--st-paused)" },
  retrying: { text: "text-st-retrying", bg: "bg-st-retrying/12", border: "border-st-retrying/50", dot: "bg-st-retrying", stroke: "var(--risk-high)" },
  idle: { text: "text-muted-foreground", bg: "bg-surface-3", border: "border-line", dot: "bg-st-idle", stroke: "var(--line-strong)" },
} satisfies Record<string, Tone>;

export const AGENT_STATE_TONE: Record<AgentState, Tone> = {
  CREATED: TONES.idle,
  INITIALIZING: TONES.idle,
  READY: TONES.idle,
  RUNNING: TONES.running,
  WAITING: TONES.waiting,
  PAUSED: TONES.paused,
  CHECKPOINTING: TONES.checkpoint,
  FAILED: TONES.failed,
  RETRYING: TONES.retrying,
  COMPLETED: TONES.completed,
  TERMINATED: TONES.terminated,
};

export const TASK_STATUS_TONE: Record<TaskStatus, Tone> = {
  queued: TONES.idle,
  planning: TONES.running,
  running: TONES.running,
  waiting_approval: TONES.waiting,
  paused: TONES.paused,
  completed: TONES.completed,
  failed: TONES.failed,
  cancelled: TONES.terminated,
};

export const RISK_TONE: Record<Risk, string> = {
  low: "text-risk-low border-risk-low/50 bg-risk-low/10",
  medium: "text-risk-medium border-risk-medium/50 bg-risk-medium/12",
  high: "text-risk-high border-risk-high/50 bg-risk-high/12",
  critical: "text-risk-critical border-risk-critical/60 bg-risk-critical/15",
};

export const UNTRUSTED_TONE = "text-untrusted bg-untrusted-bg border-untrusted/60";

export const agentTone = (s?: string | null): Tone => AGENT_STATE_TONE[(s ?? "") as AgentState] ?? TONES.idle;
export const taskTone = (s?: string | null): Tone => TASK_STATUS_TONE[(s ?? "") as TaskStatus] ?? TONES.idle;
export const riskTone = (r?: string | null): string => RISK_TONE[(r ?? "") as Risk] ?? RISK_TONE.low;
