import type { AgentProcess } from "@kairos/contracts";
import { describe, expect, it } from "vitest";
import { GAP_X, GAP_Y, NODE_H, NODE_W, columnsFor, layout } from "./process-layout";

const proc = (pid: number, ppid: number | null): AgentProcess => ({ pid, ppid, agent: `a${pid}`, task_id: "T", owner: "alice" });
const apollo = [proc(101, null), proc(102, 101), proc(103, 101), proc(104, 101), proc(105, 101)];
const COL = NODE_W + GAP_X;
const ROW = NODE_H + GAP_Y;

describe("process tree layout", () => {
  it("puts siblings in one row, parent centred above, when they fit", () => {
    const { positions, edges } = layout(apollo);
    expect([102, 103, 104, 105].map((p) => positions[p])).toEqual([0, 1, 2, 3].map((i) => ({ x: i * COL, y: ROW })));
    expect(positions[101]).toEqual({ x: 1.5 * COL, y: 0 });
    expect(edges).toHaveLength(4);
  });

  it("wraps leaf siblings into rows when the pane is narrow (projector at 1366 px)", () => {
    const { positions } = layout(apollo, 2);
    expect(positions[102]).toEqual({ x: 0, y: ROW });
    expect(positions[103]).toEqual({ x: COL, y: ROW });
    expect(positions[104]).toEqual({ x: 0, y: 2 * ROW });
    expect(positions[105]).toEqual({ x: COL, y: 2 * ROW });
    expect(positions[101]).toEqual({ x: 0.5 * COL, y: 0 });
  });

  it("keeps deeper trees top-down even when narrow", () => {
    const { positions } = layout([proc(1, null), proc(2, 1), proc(3, 2), proc(4, 1)], 1);
    expect(positions[3].y).toBe(2 * ROW);
    expect(positions[2].y).toBe(ROW);
  });

  it("fits at least two columns", () => {
    expect(columnsFor(300)).toBe(2);
    expect(columnsFor(4 * COL + 16)).toBe(4);
  });
});
