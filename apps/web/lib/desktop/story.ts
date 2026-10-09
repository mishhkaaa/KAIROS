/** A run as a story: the kernel's events folded into the steps a person would describe. Pure and unit-tested; the Task
 *  window's story and the desktop's run stage both read it. Understands today's events and the thought-process events
 *  the agents add (task.understood, agent.planned, agent.created, agent.thought, tool.query, task.data). */

import type { Event } from "@kairos/contracts";

export type StepKind =
  | "ask"
  | "understood"
  | "planned"
  | "created"
  | "thought"
  | "read"
  | "think"
  | "message"
  | "kernel"
  | "approval"
  | "committed"
  | "sandbox"
  | "query"
  | "data"
  | "done"
  | "failed";

export type StepStatus = "done" | "active" | "waiting" | "error";

export interface Step {
  id: string;
  kind: StepKind;
  pid?: number;
  agent?: string;
  title: string;
  detail?: string;
  /** Documents read (for `read`) and the ones the firewall flagged. */
  paths?: string[];
  flagged?: string[];
  /** SQL or another query (for `query`). */
  code?: string;
  table?: { columns: string[]; rows: unknown[][] };
  /** How many events this step folds together (repeated thinking, several spawns). */
  count: number;
  /** Model tokens spent in a `think` step. */
  tokens?: number;
  ts?: string;
  status: StepStatus;
}

const s = (e: Event, k: string) => {
  const v = e.payload?.[k];
  return typeof v === "string" ? v : undefined;
};
const n = (e: Event, k: string) => {
  const v = e.payload?.[k];
  return typeof v === "number" ? v : undefined;
};
const list = (e: Event, k: string) => {
  const v = e.payload?.[k];
  return Array.isArray(v) ? v.map(String) : [];
};

const shortModel = (m?: string) => (m ?? "the model").replace(/:.*$/, "").replace(/-instruct$/, "");

export function buildStory(events: Event[], agents: Record<number, string>, taskStatus?: string | null): Step[] {
  const steps: Step[] = [];
  const who = (e: Event) => (e.pid ? (agents[e.pid] ?? s(e, "agent") ?? `PID ${e.pid}`) : undefined);
  const push = (e: Event, step: Omit<Step, "id" | "count" | "status" | "ts"> & { status?: StepStatus }) =>
    steps.push({ id: e.event_id ?? `${e.type}-${steps.length}`, count: 1, ts: e.ts, status: "done", ...step });
  const last = () => steps.at(-1);

  for (const e of events) {
    const agent = who(e);
    switch (e.type) {
      case "task.created":
        push(e, { kind: "ask", title: "You asked KAIROS", detail: s(e, "goal") });
        break;
      case "task.understood":
        push(e, { kind: "understood", title: "Understood the request", detail: [s(e, "intent"), list(e, "capabilities_needed").length ? `needs ${list(e, "capabilities_needed").join(", ")}` : ""].filter(Boolean).join(" · ") || s(e, "plan_summary") });
        break;
      case "agent.planned":
        push(e, { kind: "planned", title: `Chose a ${s(e, "role") ?? "specialist"}`, detail: s(e, "why"), paths: list(e, "scope") });
        break;
      case "agent.created":
      case "process.spawned": {
        const name = s(e, "manifest_name") ?? s(e, "agent") ?? agent ?? "an agent";
        const parent = n(e, "ppid");
        const prev = last();
        // Consecutive spawns by the same parent read as one fork: "Created finance-agent, engineering-agent…"
        if (prev?.kind === "created" && parent && prev.detail === `forked by ${agents[parent] ?? `PID ${parent}`}`) {
          prev.title = `${prev.title}, ${name}`;
          prev.count += 1;
        } else if (!(e.type === "process.spawned" && prev?.kind === "created" && prev.title.endsWith(name))) {
          push(e, { kind: "created", pid: e.pid ?? undefined, agent: name, title: `Created ${name}`, detail: parent ? `forked by ${agents[parent] ?? `PID ${parent}`}` : e.type === "agent.created" && e.payload?.generated ? `generated from the ${s(e, "template")} template` : "the root process" });
        }
        break;
      }
      case "agent.thought":
        push(e, { kind: "thought", pid: e.pid ?? undefined, agent, title: s(e, "text") ?? "…", detail: s(e, "step") });
        break;
      case "knowledge.retrieved": {
        const paths = list(e, "paths");
        const flagged = list(e, "flagged");
        push(e, {
          kind: "read",
          pid: e.pid ?? undefined,
          agent,
          title: `${agent ?? "An agent"} read ${paths.length || (n(e, "hits") ?? 0)} ${paths.length === 1 ? "document" : "documents"}`,
          detail: s(e, "query"),
          paths,
          flagged,
          status: flagged.length ? "error" : "done",
        });
        break;
      }
      case "model.invoked": {
        const prev = last();
        const tokens = n(e, "tokens") ?? 0;
        if (prev?.kind === "think" && prev.pid === e.pid) {
          prev.count += 1;
          prev.tokens = (prev.tokens ?? 0) + tokens;
          prev.detail = `${prev.count} calls · ${prev.tokens} tokens`;
        } else {
          push(e, { kind: "think", pid: e.pid ?? undefined, agent, title: `${agent ?? "An agent"} is thinking with ${shortModel(s(e, "model"))}`, detail: `1 call · ${tokens} tokens`, tokens });
        }
        break;
      }
      case "ipc.message":
        push(e, { kind: "message", pid: e.pid ?? undefined, agent, title: `${s(e, "sender") ?? agent} sent ${s(e, "type") ?? "a message"} to ${s(e, "receiver") ?? "its parent"}` });
        break;
      case "tool.query": {
        const rows = n(e, "rows");
        push(e, { kind: "query", pid: e.pid ?? undefined, agent, title: `${agent ?? "An agent"} ran ${s(e, "tool") ?? "a query"}`, code: s(e, "query"), detail: rows !== undefined ? `${rows} rows · ${n(e, "ms") ?? "?"} ms` : undefined });
        break;
      }
      case "task.data": {
        const columns = list(e, "columns");
        const rows = Array.isArray(e.payload?.rows) ? (e.payload.rows as unknown[][]) : [];
        push(e, { kind: "data", title: `The data: ${rows.length} rows`, detail: s(e, "source"), table: { columns, rows } });
        break;
      }
      case "syscall.requested":
        push(e, { kind: "kernel", pid: e.pid ?? undefined, agent, title: `${agent ?? "An agent"} asked the kernel for ${s(e, "capability")}`, detail: `risk ${s(e, "risk") ?? "?"}` });
        break;
      case "syscall.decided": {
        const d = s(e, "decision") ?? "";
        const prev = last();
        const text = d === "ALLOW" ? "allowed by policy" : d === "DENY" ? "denied by policy" : "policy says a human decides";
        if (prev?.kind === "kernel") prev.detail = `${prev.detail} · ${text}${s(e, "policy") ? ` (${s(e, "policy")})` : ""}`;
        if (d === "DENY" && prev) prev.status = "error";
        break;
      }
      case "approval.requested":
        push(e, { kind: "approval", pid: e.pid ?? undefined, agent, title: `Waiting for your approval: ${s(e, "capability")}`, status: "waiting" });
        break;
      case "approval.resolved": {
        const a = [...steps].reverse().find((x) => x.kind === "approval");
        if (a) {
          a.title = `${s(e, "status") === "approved" ? "Approved" : "Rejected"} by ${s(e, "resolved_by") ?? "a human"}: ${a.title.replace(/^Waiting for your approval: /, "")}`;
          a.status = s(e, "status") === "approved" ? "done" : "error";
        }
        break;
      }
      case "transaction.committed":
        push(e, { kind: "committed", pid: e.pid ?? undefined, agent, title: e.payload?.verified ? "Executed, verified and committed" : "Committed" });
        break;
      case "transaction.rolled_back":
        push(e, { kind: "committed", pid: e.pid ?? undefined, agent, title: "Rolled back", detail: s(e, "reason"), status: "error" });
        break;
      case "sandbox.started":
        push(e, { kind: "sandbox", pid: e.pid ?? undefined, agent, title: `${agent ?? "An agent"} opened a sandbox`, detail: s(e, "image") });
        break;
      case "sandbox.screenshot": {
        const prev = last();
        if (prev?.kind === "sandbox") prev.detail = `${prev.detail ?? ""} · screenshot taken`.replace(/^ · /, "");
        break;
      }
      case "task.completed":
        push(e, { kind: "done", title: "Done", detail: s(e, "summary") });
        break;
      case "task.failed":
        push(e, { kind: "failed", title: "The task failed", detail: s(e, "reason"), status: "error" });
        break;
    }
  }
  // While the task runs, its latest step is the one happening now.
  const running = taskStatus && !["completed", "failed", "cancelled"].includes(taskStatus);
  const tail = steps.at(-1);
  if (running && tail && tail.status === "done") tail.status = "active";
  return steps;
}
