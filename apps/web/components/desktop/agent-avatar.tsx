"use client";

import { BotAvatar, type BotAvatarType } from "bot-avatars";

/** Known roles keep a stable face; generated agents get one from a hash of their role, so the same role always looks
 *  the same across runs. */
const KNOWN: Record<string, [BotAvatarType, string]> = {
  planner: ["droid", "#2f7cf6"],
  finance: ["clover", "#16b67a"],
  engineering: ["mech", "#ff8a3d"],
  research: ["alien", "#7b61ff"],
  action: ["star", "#f5a623"],
  data: ["hexagon", "#00b3c7"],
  writer: ["flower", "#f0628f"],
  operator: ["pill", "#5c6bc0"],
};
const SHAPES: BotAvatarType[] = ["blob", "ghost", "drop", "cloud", "pebble", "cat", "square", "triangle", "circle", "puddle"];
const COLOURS = ["#14a89a", "#c56cf0", "#7cc242", "#ff5a5f", "#00b3c7", "#f5a623", "#2f7cf6"];

function hash(s: string): number {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0;
  return Math.abs(h);
}

export function avatarFor(agent: string): [BotAvatarType, string] {
  const role = agent.replace(/-agent.*$/, "").replace(/-[0-9a-f]{2,}$/, "").split("-")[0];
  if (KNOWN[role]) return KNOWN[role];
  const h = hash(role);
  return [SHAPES[h % SHAPES.length], COLOURS[h % COLOURS.length]];
}

export function agentBotState(state?: string): "working" | "sleeping" | "default" {
  const s = (state ?? "").toUpperCase();
  if (s === "RUNNING" || s === "READY" || s === "CREATED") return "working";
  if (s === "WAITING" || s === "PAUSED") return "default";
  return "sleeping";
}

/** An agent's face: a bot avatar that hops while the process works, looks around while it waits, and dozes when done. */
export function AgentAvatar({ agent, state, size = 56, interactive = false }: { agent: string; state?: string; size?: number; interactive?: boolean }) {
  const [type, color] = avatarFor(agent);
  return <BotAvatar type={type} color={color} state={agentBotState(state)} size={size} interactive={interactive} aria-label={`${agent} (${state ?? "unknown"})`} role="img" />;
}
