import type { Event } from "@kairos/contracts";
import { describe, expect, it } from "vitest";
import { orbFor } from "./orb";

const ev = (type: string) => ({ type }) as Event;

describe("process orbs", () => {
  it("shows what a running agent is doing from its last event", () => {
    expect(orbFor("RUNNING", ev("knowledge.retrieved"))).toBe("searching");
    expect(orbFor("RUNNING", ev("model.invoked"))).toBe("composing");
    expect(orbFor("RUNNING", ev("ipc.message"))).toBe("weaving");
    expect(orbFor("RUNNING", ev("sandbox.started"))).toBe("connecting");
    expect(orbFor("RUNNING", undefined)).toBe("working");
  });

  it("breathes while a process waits on a human, and stops when it is done", () => {
    expect(orbFor("WAITING", undefined, "approval:A-1")).toBe("breathing");
    expect(orbFor("WAITING", undefined, "ipc")).toBe("listening");
    expect(orbFor("TERMINATED", ev("model.invoked"))).toBeNull();
    expect(orbFor("FAILED", undefined)).toBeNull();
  });
});
