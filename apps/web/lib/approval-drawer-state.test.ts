import { describe, expect, it } from "vitest";
import { drawerOpen, seenAfterClose } from "./approval-drawer-state";

const base = { pending: [] as string[], seen: [] as string[], manualOpen: false, lingering: false };

describe("approval drawer", () => {
  it("opens by itself for a new pending approval", () => {
    expect(drawerOpen({ ...base, pending: ["A"] })).toBe(true);
  });

  it("stays closed once the user has seen and closed it", () => {
    const seen = seenAfterClose([], ["A"], ["A"]);
    expect(drawerOpen({ ...base, pending: ["A"], seen })).toBe(false);
    expect(drawerOpen({ ...base, pending: ["A"], seen, manualOpen: true })).toBe(true); // the banner reopens it
  });

  it("an approval that arrives while the drawer is closing is not lost", () => {
    // B turned up pending but its card never rendered before the user closed the drawer
    const seen = seenAfterClose([], ["A", "B"], ["A"]);
    expect(seen).toEqual(["A"]);
    expect(drawerOpen({ ...base, pending: ["A", "B"], seen })).toBe(true);
  });

  it("lingers after a decision, then shows the next approval without closing", () => {
    expect(drawerOpen({ ...base, pending: [], lingering: true })).toBe(true);
    expect(drawerOpen({ ...base, pending: ["B"], seen: ["A"], lingering: true })).toBe(true);
    expect(drawerOpen({ ...base, pending: [], lingering: false })).toBe(false);
  });

  it("never opens with nothing to show unless it is lingering", () => {
    expect(drawerOpen({ ...base, manualOpen: true })).toBe(false);
  });
});
