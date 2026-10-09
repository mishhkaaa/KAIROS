import type { Event } from "@kairos/contracts";
import { describe, expect, it } from "vitest";
import { buildStory } from "./story";

let seq = 0;
const ev = (type: string, payload: Record<string, unknown> = {}, pid?: number): Event =>
  ({ event_id: `E${++seq}`, type, payload, pid, ts: `2026-09-30T10:00:${String(seq).padStart(2, "0")}Z` }) as unknown as Event;
const agents = { 101: "planner-agent", 102: "finance-agent", 103: "engineering-agent", 105: "action-agent" };

describe("run story", () => {
  const events = [
    ev("task.created", { goal: "Why is Apollo late?" }),
    ev("process.spawned", { agent: "planner-agent" }, 101),
    ev("process.spawned", { agent: "finance-agent", ppid: 101 }, 102),
    ev("process.spawned", { agent: "engineering-agent", ppid: 101 }, 103),
    ev("knowledge.retrieved", { paths: ["/org/finance/apollo-budget", "/org/inbox/vendor-email-2026-09-12"], flagged: ["/org/inbox/vendor-email-2026-09-12"], query: "budget" }, 102),
    ev("model.invoked", { model: "qwen2.5:7b-instruct", tokens: 1200 }, 102),
    ev("model.invoked", { model: "qwen2.5:7b-instruct", tokens: 300 }, 102),
    ev("syscall.requested", { capability: "jira.write", risk: "medium" }, 105),
    ev("syscall.decided", { decision: "REQUIRE_APPROVAL", policy: "default-v1" }, 105),
    ev("approval.requested", { capability: "jira.write" }, 105),
  ];

  it("tells the run as steps a person would describe", () => {
    const story = buildStory(events, agents, "waiting");
    expect(story.map((x) => x.kind)).toEqual(["ask", "created", "created", "read", "think", "kernel", "approval"]);
    expect(story[2].title).toBe("Created finance-agent, engineering-agent");
    expect(story[3]).toMatchObject({ title: "finance-agent read 2 documents", flagged: ["/org/inbox/vendor-email-2026-09-12"], status: "error" });
    expect(story[4]).toMatchObject({ title: "finance-agent is thinking with qwen2.5", detail: "2 calls · 1500 tokens" });
    expect(story[5].detail).toBe("risk medium · policy says a human decides (default-v1)");
    expect(story.at(-1)?.status).toBe("waiting");
  });

  it("resolves the approval, and marks the latest step active while the task runs", () => {
    const story = buildStory([...events, ev("approval.resolved", { status: "approved", resolved_by: "alice" }, 105), ev("transaction.committed", { verified: true }, 105)], agents, "running");
    expect(story.find((x) => x.kind === "approval")).toMatchObject({ title: "Approved by alice: jira.write", status: "done" });
    expect(story.at(-1)).toMatchObject({ kind: "committed", title: "Executed, verified and committed", status: "active" });
  });

  it("reads the thought-process events: understanding, planned and generated agents, SQL and data", () => {
    const story = buildStory(
      [
        ev("task.understood", { intent: "find vendor overpayments", capabilities_needed: ["db.query"] }),
        ev("agent.planned", { role: "data engineer", why: "the numbers live in the invoices table", scope: ["/org/finance"] }),
        ev("agent.created", { manifest_name: "data-engineer-7f", template: "data-engineer", generated: true }, 110),
        ev("agent.thought", { text: "Joining invoices to contracts by vendor", step: "plan" }, 110),
        ev("tool.query", { tool: "db.query", query: "SELECT vendor, SUM(amount) FROM invoices GROUP BY vendor LIMIT 50", rows: 12, ms: 38 }, 110),
        ev("task.data", { columns: ["vendor", "over"], rows: [["PayCo", 4.1]], source: "kairos_demo_data" }),
        ev("task.completed", { summary: "PayCo was overpaid by 4.1 lakh" }),
      ],
      { 110: "data-engineer-7f" },
      "completed",
    );
    expect(story.map((x) => x.kind)).toEqual(["understood", "planned", "created", "thought", "query", "data", "done"]);
    expect(story[0].detail).toBe("find vendor overpayments · needs db.query");
    expect(story[2].detail).toBe("generated from the data-engineer template");
    expect(story[4]).toMatchObject({ code: "SELECT vendor, SUM(amount) FROM invoices GROUP BY vendor LIMIT 50", detail: "12 rows · 38 ms" });
    expect(story[5].table?.rows).toEqual([["PayCo", 4.1]]);
    expect(story.every((x) => x.status !== "active")).toBe(true);
  });
});

describe("the routing decision", () => {
  it("shows Jev's scores once, highest first, with the agents over the line marked", () => {
    const understood = ev("task.understood", { intent: "why is Apollo late", plan_summary: "x", goal_type: "investigation", router: "jev",
      route_scores: { "research-agent": 0.2, "finance-agent": 0.91, "engineering-agent": 0.6 }, route_ms: 38.4 }, 101);
    const story = buildStory([understood, { ...understood, event_id: "again" } as Event,
      ev("agent.planned", { role: "finance-agent", why: "budget", score: 0.91 }, 101)], agents, "running");
    expect(story.map((x) => x.kind)).toEqual(["understood", "routed", "understood", "planned"]);
    expect(story[1].title).toBe("Jev routed this locally in 38 ms: an investigation");
    expect(story[1].scores).toEqual([{ role: "finance-agent", p: 0.91, on: true }, { role: "engineering-agent", p: 0.6, on: true },
      { role: "research-agent", p: 0.2, on: false }]);
    expect(new Set(story.map((x) => x.id)).size).toBe(story.length);
    expect(story[3].title).toBe("Chose a finance-agent (Jev 0.91)");
  });

  it("says when the rules chose the agents", () => {
    const story = buildStory([ev("task.understood", { intent: "q", plan_summary: "x", goal_type: "question", router: "rules" })], {}, "running");
    expect(story[1]).toMatchObject({ kind: "routed", title: "Routed by the planner's rules: a question" });
  });
});
