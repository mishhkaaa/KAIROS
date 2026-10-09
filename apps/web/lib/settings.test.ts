import type { SystemConfig } from "@kairos/contracts";
import { describe, expect, it } from "vitest";
import example from "../../../shared/fixtures/json/system_config.json";
import { architecture, needsHuman, overview, routingFlow, searchConfig } from "./settings";

const cfg = example as unknown as SystemConfig;

describe("settings helpers", () => {
  it("groups the stack into layers and prefers live health", () => {
    const map = architecture(
      [
        { component: "kernel", mode: "real", implementation: "K", ok: true },
        { component: "models", mode: "fake", implementation: "M", ok: true },
        { component: "mystery", mode: "real", implementation: "X", ok: true },
      ],
      [{ component: "models", ok: false, mode: "fake" }],
    );
    expect(map.map((l) => l.title)).toEqual(["Kernel", "Agents & models", "Other"]);
    expect(map[1].nodes[0].live).toBe(false);
  });

  it("draws routing as model <- task classes, default first", () => {
    const flow = routingFlow([
      { task_class: "planning", model: "a", available: true },
      { task_class: "default", model: "a", available: true },
      { task_class: "embedding", model: "e", available: false },
    ]);
    expect(flow[0]).toEqual({ model: "a", local: true, available: true, classes: ["default", "planning"] });
    expect(flow[1].available).toBe(false);
  });

  it("summarises what needs a human across policies", () => {
    expect(
      needsHuman([
        { policy: "b", priority: 1, requires_approval: ["jira.write"] },
        { policy: "a", priority: 2, requires_approval: ["jira.write", "db.write"] },
      ]),
    ).toEqual([
      { capability: "db.write", policies: ["a"] },
      { capability: "jira.write", policies: ["a", "b"] },
    ]);
  });

  it("searches across sections with all terms", () => {
    expect(searchConfig(cfg, "")).toEqual([]);
    const hits = searchConfig(cfg, "jira write");
    expect(hits.some((h) => h.section === "policies")).toBe(true);
    expect(searchConfig(cfg, "nomic").some((h) => h.section === "models")).toBe(true);
  });

  it("computes overview counts from the example config", () => {
    const o = overview(cfg);
    expect(o.components).toBeGreaterThan(0);
    expect(o.localOnly).toBe(true);
    expect(o.gated).toBeGreaterThan(0);
  });
});
