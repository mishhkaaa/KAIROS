import type { MemoryRecord } from "@kairos/contracts";
import { describe, expect, it } from "vitest";
import { groupMemories } from "./memory-groups";

const mem = (id: string, extra: Partial<MemoryRecord> = {}): MemoryRecord =>
  ({ memory_id: id, kind: "episodic", scope: "agent", org_id: "acme", owner: "finance-agent", content: id, ...extra }) as MemoryRecord;

describe("memory groups", () => {
  // Newest first, as the Memory screen sorts them: two re-derived records, then engineering, then the stale originals.
  const list = [
    mem("NEW1", { tags: ["reconsolidated", "replaces:OLD1"] }),
    mem("NEW2", { tags: ["reconsolidated", "replaces:OLD2"] }),
    mem("ENG", { owner: "engineering-agent" }),
    mem("OLD1", { stale: true }),
    mem("OLD2", { stale: true }),
  ];

  it("lists every memory exactly once, pairing each re-derived memory with the one it replaced", () => {
    const groups = groupMemories(list);
    expect(groups.map((g) => [g.memory.memory_id, g.replaced.map((r) => r.memory_id)])).toEqual([
      ["NEW1", ["OLD1"]],
      ["NEW2", ["OLD2"]],
      ["ENG", []],
    ]);
    const shown = groups.flatMap((g) => [g.memory.memory_id, ...g.replaced.map((r) => r.memory_id)]);
    expect(new Set(shown).size).toBe(shown.length);
    expect(shown.sort()).toEqual(list.map((m) => m.memory_id).sort());
  });

  it("shows a re-derived memory on its own when the record it replaced is filtered out", () => {
    const groups = groupMemories(list.filter((m) => !m.stale));
    expect(groups.map((g) => [g.memory.memory_id, g.replaced.map((r) => r.memory_id)])).toEqual([
      ["NEW1", []],
      ["NEW2", []],
      ["ENG", []],
    ]);
  });

  it("shows a stale memory on its own until its replacement arrives", () => {
    expect(groupMemories([mem("OLD1", { stale: true })]).map((g) => g.memory.memory_id)).toEqual(["OLD1"]);
  });

  it("keeps a whole chain together when the source changed twice", () => {
    const chain = [
      mem("V3", { tags: ["replaces:V2"] }),
      mem("V2", { stale: true, tags: ["replaces:V1"] }),
      mem("V1", { stale: true }),
    ];
    expect(groupMemories(chain).map((g) => [g.memory.memory_id, g.replaced.map((r) => r.memory_id)])).toEqual([["V3", ["V2", "V1"]]]);
  });
});
