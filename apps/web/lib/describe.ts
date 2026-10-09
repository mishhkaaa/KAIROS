// One formatter for every event type in shared/catalogs/events.yaml: icon, colour family, title, detail.
// Used by the timeline, the audit journal and anywhere else an event is shown as a line.
import type { Event } from "@kairos/contracts";
import {
  Activity,
  BellRing,
  BookOpenText,
  Box,
  Brain,
  Camera,
  CircleCheck,
  CircleX,
  Clock,
  Cpu,
  Flag,
  GitFork,
  KeyRound,
  type LucideIcon,
  MessageSquare,
  RefreshCw,
  Save,
  Send,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  Sparkles,
  TriangleAlert,
  Undo2,
  Wrench,
} from "lucide-react";
import { flaggedPathsFromLog, num, str, strList } from "./events";

export type Family =
  | "task"
  | "process"
  | "log"
  | "warning"
  | "syscall"
  | "policy"
  | "approval"
  | "transaction"
  | "knowledge"
  | "memory"
  | "model"
  | "sandbox"
  | "tool"
  | "ipc"
  | "system"
  | "danger";

export interface EventLine {
  icon: LucideIcon;
  family: Family;
  title: string;
  detail?: string;
}

export const FAMILY_TEXT: Record<Family, string> = {
  task: "text-foreground",
  process: "text-muted-foreground",
  log: "text-foreground/90",
  warning: "text-st-waiting",
  syscall: "text-ev-syscall",
  policy: "text-ev-policy",
  approval: "text-ev-approval",
  transaction: "text-st-running",
  knowledge: "text-ev-knowledge",
  memory: "text-ev-memory",
  model: "text-muted-foreground",
  sandbox: "text-ev-tool",
  tool: "text-ev-tool",
  ipc: "text-foreground/80",
  system: "text-muted-foreground",
  danger: "text-ev-danger",
};

/** Families that get a highlighted row: governance decisions and anything that went wrong. */
export const EMPHASISED: Family[] = ["syscall", "policy", "approval", "warning", "danger", "transaction"];

const plural = (n: number | undefined, word: string) => `${n ?? 0} ${word}${n === 1 ? "" : "s"}`;

export function describeEvent(e: Event): EventLine {
  const p = (k: string) => str(e, k);
  switch (e.type) {
    case "task.created":
      return { icon: Flag, family: "task", title: `Task submitted by ${p("user_id") ?? "user"}`, detail: p("goal") };
    case "task.status_changed":
      return { icon: Activity, family: "task", title: `Task ${p("old")} → ${p("new")}` };
    case "task.completed":
      return { icon: CircleCheck, family: "transaction", title: "Task completed", detail: p("summary") };
    case "task.failed":
      return { icon: CircleX, family: "danger", title: "Task failed", detail: p("reason") };

    case "process.spawned":
      return { icon: GitFork, family: "process", title: `Spawned ${p("agent")}`, detail: num(e, "ppid") ? `parent pid ${num(e, "ppid")}` : "root process" };
    case "process.state_changed": {
      const next = p("new");
      const fam: Family = next === "FAILED" || next === "TERMINATED" ? "danger" : next === "WAITING" ? "warning" : "process";
      return { icon: Cpu, family: fam, title: `${p("old")} → ${next}`, detail: p("reason") };
    }
    case "process.checkpointed":
      return { icon: Save, family: "process", title: "Checkpoint saved", detail: p("checkpoint_id") };
    case "process.usage": {
      const tokens = (num(e, "tokens_prompt") ?? 0) + (num(e, "tokens_completion") ?? 0);
      return { icon: Activity, family: "system", title: `Usage: ${tokens} tokens · ${plural(num(e, "tool_calls"), "tool call")}` };
    }
    case "agent.log": {
      const level = p("level") ?? "info";
      const flagged = flaggedPathsFromLog(e);
      if (flagged.length) return { icon: ShieldAlert, family: "danger", title: "Context firewall flagged evidence", detail: `${flagged.join(", ")} (treated as data, never as instructions)` };
      return { icon: level === "warning" || level === "error" ? TriangleAlert : MessageSquare, family: level === "warning" || level === "error" ? "warning" : "log", title: p("message") || "(empty log line)" };
    }

    case "syscall.requested":
      return { icon: KeyRound, family: "syscall", title: `Syscall ${p("capability")}`, detail: `${p("tool")}.${p("operation")} · risk ${p("risk")}` };
    case "syscall.decided": {
      const d = p("decision");
      const icon = d === "ALLOW" ? ShieldCheck : d === "DENY" ? ShieldX : ShieldAlert;
      return { icon, family: d === "DENY" ? "danger" : "policy", title: `Policy: ${d?.replaceAll("_", " ")}`, detail: [p("policy"), p("reason")].filter(Boolean).join(" · ") };
    }
    case "syscall.completed":
      return { icon: KeyRound, family: "syscall", title: `Syscall ${p("status")}` };
    case "approval.requested":
      return { icon: BellRing, family: "approval", title: `Approval required: ${p("capability")}`, detail: p("approval_id") };
    case "approval.resolved":
      return { icon: p("status") === "approved" ? CircleCheck : CircleX, family: p("status") === "approved" ? "approval" : "danger", title: `Approval ${p("status")} by ${p("resolved_by")}`, detail: p("approval_id") };
    case "transaction.committed":
      return { icon: CircleCheck, family: "transaction", title: e.payload?.verified ? "Committed (post-condition verified)" : "Committed" };
    case "transaction.rolled_back":
      return { icon: Undo2, family: "danger", title: "Rolled back", detail: p("reason") };
    case "policy.updated":
      return { icon: ShieldCheck, family: "policy", title: "Policies reloaded", detail: strList(e, "policies").join(", ") };
    case "audit.appended":
      return { icon: BookOpenText, family: "system", title: `Audit: ${p("summary") ?? p("kind")}` };

    case "ipc.message":
      return { icon: Send, family: "ipc", title: `IPC ${p("type")}: ${p("sender")} → ${p("receiver")}`, detail: p("message_id") };

    case "knowledge.changed":
      return { icon: BookOpenText, family: "knowledge", title: `Knowledge ${p("change")}: ${p("path")}` };
    case "knowledge.reindexed":
      return { icon: RefreshCw, family: "knowledge", title: `Knowledge reindexed (${plural(num(e, "count"), "object")})` };
    case "knowledge.retrieved": {
      const hidden = num(e, "filtered_by_policy") ?? 0;
      const flagged = strList(e, "flagged").length;
      const title = `Retrieved ${plural(num(e, "hits"), "document")}${hidden ? ` · ${hidden} hidden by policy` : ""}${flagged ? ` · ${flagged} flagged by the firewall` : ""}`;
      return { icon: flagged ? ShieldAlert : BookOpenText, family: flagged ? "danger" : "knowledge", title, detail: p("query") };
    }
    // The thought process (B): what the planner understood, which agents it planned and created, what they think.
    case "task.understood":
      return { icon: Sparkles, family: "model", title: `Understood: ${p("intent")}`, detail: strList(e, "capabilities_needed").join(", ") || undefined };
    case "agent.planned":
      return { icon: Sparkles, family: "process", title: `Planned a ${p("role")} agent`, detail: p("why") };
    case "agent.created":
      return { icon: Sparkles, family: "process", title: `Created ${p("manifest_name")}`, detail: e.payload?.generated ? `generated from the ${p("template")} template` : `from its manifest` };
    case "agent.thought":
      return { icon: Brain, family: "model", title: p("text") ?? "Thinking", detail: p("step") };
    case "tool.query":
      return { icon: Wrench, family: "tool", title: `${p("tool")}: ${num(e, "rows") ?? 0} rows in ${num(e, "ms") ?? 0} ms`, detail: p("query") };
    case "task.data":
      return { icon: Activity, family: "tool", title: `Data: ${strList(e, "columns").length} columns`, detail: p("source") };
    case "ingest.progress":
      return { icon: BookOpenText, family: p("stage") === "error" ? "danger" : "knowledge", title: `Ingest ${p("file")}: ${p("stage")}`, detail: e.payload?.path ? p("path") : e.payload?.error ? p("error") : undefined };
    case "mount.synced":
      return { icon: RefreshCw, family: "knowledge", title: `Folder ${p("org_path")} synced (${plural(num(e, "files"), "file")})`, detail: p("host_path") };
    case "connector.changed":
      return { icon: Wrench, family: "tool", title: `Connector ${p("connector_id")} ${p("status")}` };
    case "memory.invalidated": {
      const n = strList(e, "invalidated").length;
      return { icon: Brain, family: "danger", title: `Memory invalidated: ${plural(n, "record")} stale`, detail: `${p("source")} changed · affects ${strList(e, "affected_agents").join(", ") || "no agents"}` };
    }
    case "memory.consolidated":
      return { icon: Brain, family: "memory", title: `Memory consolidated (${plural(num(e, "created"), "new record")})` };

    case "model.invoked":
      return { icon: Sparkles, family: "model", title: `Model ${p("model")} · ${num(e, "tokens") ?? 0} tokens`, detail: e.payload?.local === false ? `remote (${p("provider")})` : `local (${p("provider")})` };

    case "sandbox.started":
      return { icon: Box, family: "sandbox", title: `Sandbox ${p("sandbox_id")} started`, detail: p("image") };
    case "sandbox.destroyed":
      return { icon: Box, family: "sandbox", title: `Sandbox ${p("sandbox_id")} destroyed` };
    case "sandbox.screenshot":
      return { icon: Camera, family: "sandbox", title: "Screenshot captured", detail: p("artifact") };
    case "tool.started":
      return { icon: Wrench, family: "tool", title: `Tool ${p("tool")}.${p("operation")} started` };
    case "tool.completed":
      return { icon: Wrench, family: p("status") === "success" ? "tool" : "danger", title: `Tool ${p("tool")}.${p("operation")} → ${p("status")}` };

    case "system.ready":
      return { icon: Activity, family: "system", title: "System ready" };
    case "system.health":
      return { icon: Activity, family: "system", title: "Health snapshot" };
    case "cron.triggered":
      return { icon: Clock, family: "system", title: `Scheduled job ${p("job")}` };
    default:
      return { icon: Activity, family: "system", title: e.type };
  }
}
