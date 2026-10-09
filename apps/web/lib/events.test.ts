import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { AgentProcess, Approval, Event, Task } from "@kairos/contracts";
import { EventType } from "@kairos/contracts";
import { describe, expect, it } from "vitest";
import { describeEvent } from "./describe";
import { buildTaskView, flaggedPathsFromLog, mergeEvents, sortByTs } from "./events";

const FIXTURES = join(__dirname, "..", "..", "..", "shared", "fixtures", "json");
const load = <T>(name: string): T => JSON.parse(readFileSync(join(FIXTURES, name), "utf-8")) as T;
const EVENTS = load<Event[]>("events.json");

describe("buildTaskView on the Apollo replay (shared/fixtures/json/events.json)", () => {
  const view = buildTaskView({}, EVENTS);

  it("tracks every process and ends with them all COMPLETED", () => {
    expect(Object.keys(view.processes).map(Number).sort()).toEqual([101, 102, 103, 104, 105]);
    for (const p of Object.values(view.processes)) expect(p.state).toBe("COMPLETED");
    expect(view.processes[102].ppid).toBe(101);
    expect(view.processes[101].agent).toBe("planner-agent");
  });

  it("follows the task status and captures the summary", () => {
    expect(view.status).toBe("completed");
    expect(view.summary).toMatch(/recovery plan/);
  });

  it("shows the approval pending in the middle of the run, resolved at the end", () => {
    const upToApproval = EVENTS.slice(0, EVENTS.findIndex((e) => e.type === "approval.resolved"));
    const mid = buildTaskView({}, upToApproval);
    expect(mid.pendingApprovalIds).toEqual(["APR-882"]);
    expect(mid.status).toBe("waiting_approval");
    expect(mid.processes[105].state).toBe("WAITING");
    expect(view.pendingApprovalIds).toEqual([]);
  });

  it("attaches the firewall flag to the retrieval that surfaced it", () => {
    expect(view.retrieved).toHaveLength(1);
    expect(view.retrieved[0].flagged).toEqual(["/org/inbox/vendor-email-2026-09-12"]);
    expect(view.flaggedPaths).toEqual(["/org/inbox/vendor-email-2026-09-12"]);
  });

  it("tracks sandboxes", () => {
    expect(view.sandboxes["SB-4c2"]).toMatchObject({ destroyed: true, image: "kairos/sandbox-base:latest" });
  });
});

describe("ordering and de-duplication", () => {
  it("orders by ts, not by arrival", () => {
    const shuffled = [...EVENTS].reverse();
    expect(sortByTs(shuffled).map((e) => e.event_id)).toEqual(EVENTS.map((e) => e.event_id));
    expect(buildTaskView({}, shuffled).status).toBe("completed");
  });

  it("de-duplicates replayed events by event_id", () => {
    const seen = new Map<string, Event>();
    expect(mergeEvents(seen, EVENTS)).toBe(true);
    expect(mergeEvents(seen, EVENTS.slice(0, 10))).toBe(false);
    expect(seen.size).toBe(EVENTS.length);
  });
});

describe("late process.spawned", () => {
  it("fills in ppid and agent for a process first seen through a state change", () => {
    const at = (s: number) => `2026-09-27T10:00:0${s}Z`;
    const v = buildTaskView({}, [
      { type: "process.state_changed", source: "k", pid: 102, ts: at(1), payload: { old: "CREATED", new: "RUNNING" } },
      { type: "process.spawned", source: "k", pid: 102, ts: at(1), payload: { agent: "finance-agent", ppid: 101 } },
    ]);
    expect(v.processes[102]).toMatchObject({ ppid: 101, agent: "finance-agent", state: "RUNNING" });
  });
});

describe("snapshot seeding", () => {
  it("doesn't let an older event overwrite a newer snapshot", () => {
    const snap: AgentProcess = {
      pid: 105, agent: "action-agent", task_id: "T-1842", owner: "alice", state: "COMPLETED",
      updated_at: "2026-09-26T10:05:00Z",
    };
    const older = EVENTS.filter((e) => e.pid === 105 && e.type === "process.state_changed");
    expect(buildTaskView({ processes: [snap] }, older).processes[105].state).toBe("COMPLETED");
  });

  it("uses seeded approvals and task", () => {
    const approval = load<Approval>("approval.json");
    const task = load<Task>("task.json");
    const v = buildTaskView({ task, approvals: [{ ...approval, status: "pending" }] }, []);
    expect(v.pendingApprovalIds).toEqual([approval.approval_id]);
    expect(v.task?.task_id).toBe(task.task_id);
  });
});

describe("firewall flag parsing", () => {
  const log = (message: string): Event => ({ type: "agent.log", source: "pid:1", pid: 1, payload: { level: "warning", message } });

  it("reads the mock's and the real kernel's message formats", () => {
    expect(flaggedPathsFromLog(log("Context firewall flagged /org/inbox/vendor-email-2026-09-12 (instruction_like) — treated as data")))
      .toEqual(["/org/inbox/vendor-email-2026-09-12"]);
    expect(flaggedPathsFromLog(log("Context firewall flagged /org/a/b, /org/c — treated as data"))).toEqual(["/org/a/b", "/org/c"]);
    expect(flaggedPathsFromLog(log("nothing to see"))).toEqual([]);
  });
});

describe("describeEvent", () => {
  it("has a readable line for every event type in the catalog", () => {
    for (const type of Object.values(EventType)) {
      const line = describeEvent({ type, source: "test", payload: {} });
      expect(line.title, type).toBeTruthy();
      expect(line.title, type).not.toBe(type);
    }
  });

  it("describes the governance moments distinctly", () => {
    const byType = (t: string) => describeEvent(EVENTS.find((e) => e.type === t)!);
    expect(byType("syscall.decided")).toMatchObject({ family: "policy", title: "Policy: REQUIRES APPROVAL" });
    expect(byType("approval.requested").family).toBe("approval");
    expect(describeEvent(EVENTS.find((e) => e.type === "agent.log" && e.payload?.level === "warning")!).family).toBe("danger");
  });
});

describe("knowledge.retrieved flagged (contract 0.4.0)", () => {
  it("takes flagged paths from the payload", () => {
    const ev = {
      event_id: "EV-f1", type: "knowledge.retrieved", ts: "2026-09-28T10:00:00Z", source: "kernel", org_id: "acme",
      task_id: "T-1", pid: 104, correlation_id: null,
      payload: { query: "vendor", hits: 2, filtered_by_policy: 0, paths: ["/org/a", "/org/inbox/vendor-email"], flagged: ["/org/inbox/vendor-email"] },
    } as unknown as Event;
    const view = buildTaskView({}, [ev]);
    expect(view.retrieved[0].flagged).toEqual(["/org/inbox/vendor-email"]);
    expect(view.flaggedPaths).toEqual(["/org/inbox/vendor-email"]);
    expect(describeEvent(ev).family).toBe("danger");
  });
});
