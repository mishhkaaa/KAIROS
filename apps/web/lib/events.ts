// Event stream → UI state. Events are ordered by `ts` (never arrival order) and de-duplicated by `event_id`,
// because the gateway replays a task's history on (re)connect. Payload shapes are the ones in
// shared/catalogs/events.yaml; they aren't generated into TypeScript, so fields are read through the accessors
// below rather than re-declared as local interfaces.
import type { AgentProcess, AgentState, Approval, Event, Task, TaskStatus } from "@kairos/contracts";

// --------------------------------------------------------------------------------------------- payload access

export const str = (e: Event, key: string): string | undefined => {
  const v = e.payload?.[key];
  return typeof v === "string" ? v : typeof v === "number" ? String(v) : undefined;
};
export const num = (e: Event, key: string): number | undefined => {
  const v = e.payload?.[key];
  return typeof v === "number" ? v : undefined;
};
export const strList = (e: Event, key: string): string[] => {
  const v = e.payload?.[key];
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
};

const tsOf = (e: Event) => (e.ts ? Date.parse(e.ts) : 0);

/** Sort by ts; ties keep their relative order (Array.prototype.sort is stable). */
export function sortByTs(events: Event[]): Event[] {
  return [...events].sort((a, b) => tsOf(a) - tsOf(b));
}

/** Merge new events into a map keyed by event_id (events without an id are keyed by content). */
export function mergeEvents(into: Map<string, Event>, incoming: Event[]): boolean {
  let changed = false;
  for (const e of incoming) {
    const key = e.event_id ?? `${e.type}|${e.ts}|${e.pid}|${JSON.stringify(e.payload)}`;
    if (!into.has(key)) {
      into.set(key, e);
      changed = true;
    }
  }
  return changed;
}

// --------------------------------------------------------------------------------------------- firewall flags

// knowledge.retrieved carries `flagged` (contract 0.4.0). Older gateways only logged
// `Context firewall flagged <path>[, <path>…] — treated as data` as an agent.log warning; still parsed as a fallback.
const FLAG_RE = /Context firewall flagged\s+(.+)/i;
const PATH_RE = /\/org(?:\/[A-Za-z0-9._-]+)+/g;

export function flaggedPathsFromLog(e: Event): string[] {
  if (e.type !== "agent.log") return [];
  const m = FLAG_RE.exec(str(e, "message") ?? "");
  return m ? (m[1].match(PATH_RE) ?? []) : [];
}

// --------------------------------------------------------------------------------------------- task view

export interface Retrieval {
  event: Event;
  flagged: string[];
}

export interface SandboxView {
  sandboxId: string;
  pid: number | null;
  image?: string;
  destroyed: boolean;
  screenshots: string[];
}

export interface TaskView {
  task: Task | null;
  status: TaskStatus | null;
  processes: Record<number, AgentProcess>;
  timeline: Event[];
  approvals: Record<string, Approval>;
  pendingApprovalIds: string[];
  retrieved: Retrieval[];
  flaggedPaths: string[];
  sandboxes: Record<string, SandboxView>;
  summary: string | null;
  failure: string | null;
  invalidations: Event[];
}

export interface TaskSeed {
  task?: Task | null;
  processes?: AgentProcess[];
  approvals?: Approval[];
}

export function buildTaskView(seed: TaskSeed, events: Event[]): TaskView {
  const task = seed.task ?? null;
  const view: TaskView = {
    task,
    status: task?.status ?? null,
    processes: {},
    timeline: sortByTs(events),
    approvals: {},
    pendingApprovalIds: [],
    retrieved: [],
    flaggedPaths: [],
    sandboxes: {},
    summary: task?.result?.summary ?? null,
    failure: task?.error?.message ?? null,
    invalidations: [],
  };
  const seededAt: Record<number, number> = {};
  for (const p of seed.processes ?? []) {
    view.processes[p.pid] = p;
    seededAt[p.pid] = p.updated_at ? Date.parse(p.updated_at) : 0;
  }
  const pending = new Set<string>();
  for (const a of seed.approvals ?? []) {
    view.approvals[a.approval_id] = a;
    if ((a.status ?? "pending") === "pending") pending.add(a.approval_id);
  }
  const flagged = new Set<string>();
  const lastRetrievalByPid = new Map<number, Retrieval>();

  for (const e of view.timeline) {
    const pid = e.pid ?? null;
    const stale = pid !== null && seededAt[pid] !== undefined && tsOf(e) < seededAt[pid];
    switch (e.type) {
      case "process.spawned": {
        if (pid === null) break;
        const ppid = num(e, "ppid") ?? null;
        const agent = str(e, "agent") ?? `pid ${pid}`;
        const known = view.processes[pid];
        if (!known) {
          view.processes[pid] = { pid, ppid, agent, task_id: e.task_id ?? task?.task_id ?? "", owner: task?.user_id ?? "", state: "CREATED" };
        } else {
          // Seen first through another event (same ts, different order): keep its state, fill in the identity.
          view.processes[pid] = { ...known, ppid: known.ppid ?? ppid, agent: known.agent.startsWith("pid ") ? agent : known.agent };
        }
        break;
      }
      case "process.state_changed": {
        if (pid === null || stale) break;
        const p = view.processes[pid] ?? { pid, agent: `pid ${pid}`, task_id: e.task_id ?? "", owner: "" };
        const next = str(e, "new") as AgentState | undefined;
        const reason = str(e, "reason");
        view.processes[pid] = {
          ...p,
          state: next ?? p.state,
          waiting_on: next === "WAITING" ? (reason && /^(pid|approval):/.test(reason) ? reason : p.waiting_on) : null,
        };
        break;
      }
      case "process.usage": {
        if (pid === null || stale || !view.processes[pid]) break;
        view.processes[pid] = { ...view.processes[pid], usage: { ...view.processes[pid].usage, ...(e.payload ?? {}) } };
        break;
      }
      case "task.status_changed":
        view.status = (str(e, "new") as TaskStatus) ?? view.status;
        break;
      case "task.completed":
        view.status = "completed";
        view.summary = str(e, "summary") ?? view.summary;
        break;
      case "task.failed":
        view.status = "failed";
        view.failure = str(e, "reason") ?? view.failure;
        break;
      case "approval.requested": {
        const id = str(e, "approval_id") ?? e.correlation_id ?? undefined;
        if (id && (view.approvals[id]?.status ?? "pending") === "pending") pending.add(id);
        break;
      }
      case "approval.resolved": {
        const id = str(e, "approval_id") ?? e.correlation_id ?? undefined;
        if (!id) break;
        pending.delete(id);
        const a = view.approvals[id];
        if (a) view.approvals[id] = { ...a, status: (str(e, "status") as Approval["status"]) ?? a.status, resolved_by: str(e, "resolved_by") ?? a.resolved_by };
        break;
      }
      case "knowledge.retrieved": {
        const r: Retrieval = { event: e, flagged: strList(e, "flagged") };
        r.flagged.forEach((p) => flagged.add(p));
        view.retrieved.push(r);
        if (pid !== null) lastRetrievalByPid.set(pid, r);
        break;
      }
      case "agent.log": {
        const paths = flaggedPathsFromLog(e);
        if (!paths.length) break;
        paths.forEach((p) => flagged.add(p));
        const r = pid !== null ? lastRetrievalByPid.get(pid) : undefined;
        if (r) r.flagged = [...new Set([...r.flagged, ...paths])];
        break;
      }
      case "sandbox.started":
      case "sandbox.destroyed":
      case "sandbox.screenshot": {
        const id = str(e, "sandbox_id");
        if (!id) break;
        const sb = (view.sandboxes[id] ??= { sandboxId: id, pid, destroyed: false, screenshots: [] });
        if (e.type === "sandbox.started") sb.image = str(e, "image");
        if (e.type === "sandbox.destroyed") sb.destroyed = true;
        if (e.type === "sandbox.screenshot") {
          const ref = str(e, "artifact");
          if (ref) sb.screenshots.push(ref);
        }
        break;
      }
      case "memory.invalidated":
        view.invalidations.push(e);
        break;
    }
  }
  view.pendingApprovalIds = [...pending];
  view.flaggedPaths = [...flagged];
  return view;
}

export const isActive = (s: TaskStatus | null | undefined) => !!s && !["completed", "failed", "cancelled"].includes(s);
