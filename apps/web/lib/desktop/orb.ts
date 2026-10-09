import type { Event } from "@kairos/contracts";
import type { OrbState } from "thinking-orbs";

/** What an agent process is doing, as a thinking-orb animation, from the last event it produced. Null means it isn't
 *  working (finished, failed, killed): the orb gives way to the state chip. */
export function orbFor(state: string | undefined, last: Event | undefined, waitingOn?: string | null): OrbState | null {
  const s = (state ?? "").toUpperCase();
  if (s === "WAITING") return waitingOn?.startsWith("approval:") ? "breathing" : "listening";
  if (s === "PAUSED") return "breathing";
  if (s !== "RUNNING" && s !== "READY" && s !== "CREATED") return null;
  switch (last?.type) {
    case "knowledge.retrieved":
      return "searching";
    case "model.invoked":
      return "composing";
    case "ipc.message":
      return "weaving";
    case "process.spawned":
      return "shaping";
    case "sandbox.started":
    case "sandbox.screenshot":
    case "tool.started":
      return "connecting";
    case "syscall.requested":
    case "syscall.decided":
      return "solving";
    default:
      return "working";
  }
}

export const ORB_LABEL: Record<OrbState, string> = {
  working: "working",
  searching: "reading /org",
  solving: "asking the kernel",
  listening: "waiting",
  connecting: "in a sandbox",
  weaving: "messaging",
  composing: "thinking",
  breathing: "waiting for you",
  shaping: "forking",
};
