/** Pure helpers for the Settings app (GET /system/config). Kept free of React so they are unit-tested. */
import type { ComponentHealth, ModelRoute, PolicySummary, StackComponent, SystemConfig } from "@kairos/contracts";

export type SectionId = "overview" | "models" | "agents" | "tools" | "policies" | "security" | "stack";

export const SECTIONS: { id: SectionId; title: string }[] = [
  { id: "overview", title: "Overview" },
  { id: "models", title: "Models" },
  { id: "agents", title: "Agents" },
  { id: "tools", title: "Tools & connectors" },
  { id: "policies", title: "Policies" },
  { id: "security", title: "Security" },
  { id: "stack", title: "Stack" },
];

/** The architecture map's layers, top to bottom. Components the map doesn't know land in "Other". */
export const LAYERS: { title: string; components: string[] }[] = [
  { title: "Kernel", components: ["kernel", "event_bus", "policy", "audit"] },
  { title: "Knowledge & memory", components: ["knowledge", "firewall", "memory", "converters"] },
  { title: "Agents & models", components: ["agent_router", "agent_registry", "agent_runtime", "models"] },
  { title: "Execution", components: ["tools", "sandbox", "browser", "artifacts"] },
  { title: "Platform", components: ["probe"] },
];

export interface MapNode extends StackComponent {
  /** Live health from /system/status when available (it refreshes more often than the config). */
  live?: boolean;
}

export function architecture(stack: StackComponent[], status?: ComponentHealth[]): { title: string; nodes: MapNode[] }[] {
  const live = new Map((status ?? []).map((c) => [c.component, c.ok]));
  const byName = new Map(stack.map((c) => [c.component, { ...c, live: live.get(c.component) }]));
  const known = new Set(LAYERS.flatMap((l) => l.components));
  const layers = LAYERS.map((l) => ({ title: l.title, nodes: l.components.flatMap((c) => (byName.has(c) ? [byName.get(c)!] : [])) }));
  const other = stack.filter((c) => !known.has(c.component)).map((c) => byName.get(c.component)!);
  return [...layers, ...(other.length ? [{ title: "Other", nodes: other }] : [])].filter((l) => l.nodes.length);
}

export function isHealthy(n: MapNode): boolean {
  return n.live ?? n.ok;
}

/** Model routing as a flow: each model with the task classes that route to it (embedding and default first). */
export function routingFlow(routes: ModelRoute[]): { model: string; local: boolean; available: boolean; classes: string[] }[] {
  const order = (t: string) => (t === "default" ? 0 : t === "embedding" ? 1 : t === "latency_critical" ? 2 : 3);
  const groups = new Map<string, { model: string; local: boolean; available: boolean; classes: string[] }>();
  for (const r of [...routes].sort((a, b) => order(a.task_class) - order(b.task_class) || a.task_class.localeCompare(b.task_class))) {
    const g = groups.get(r.model) ?? { model: r.model, local: r.local !== false, available: r.available, classes: [] };
    g.classes.push(r.task_class);
    groups.set(r.model, g);
  }
  return [...groups.values()].sort((a, b) => b.classes.length - a.classes.length || a.model.localeCompare(b.model));
}

/** "What needs a human": each capability that requires approval, with the policies that say so. */
export function needsHuman(policies: PolicySummary[]): { capability: string; policies: string[] }[] {
  const out = new Map<string, string[]>();
  for (const p of policies) for (const c of p.requires_approval ?? []) out.set(c, [...(out.get(c) ?? []), p.policy]);
  return [...out.entries()].map(([capability, ps]) => ({ capability, policies: ps.sort() })).sort((a, b) => a.capability.localeCompare(b.capability));
}

export interface SearchHit {
  section: SectionId;
  label: string;
  detail: string;
}

/** Search across the whole config: every hit names the section it lives in. Case-insensitive, all terms must match. */
export function searchConfig(cfg: SystemConfig, query: string): SearchHit[] {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  const rows: SearchHit[] = [
    ...(cfg.models.routes ?? []).map((r) => ({ section: "models" as const, label: r.task_class, detail: `routes to ${r.model}` })),
    ...(cfg.models.models ?? []).map((m) => ({ section: "models" as const, label: m.name, detail: `${m.provider} · ${(m.capabilities ?? []).join(", ")}` })),
    ...(cfg.agents ?? []).map((a) => ({
      section: "agents" as const,
      label: a.name,
      detail: [a.description, ...(a.capabilities?.tools ?? []), ...(a.handles ?? [])].join(" · "),
    })),
    ...(cfg.tools ?? []).map((t) => ({ section: "tools" as const, label: t.name, detail: [t.description, ...t.operations.map((o) => o.capability)].join(" · ") })),
    ...(cfg.policies ?? []).map((p) => ({
      section: "policies" as const,
      label: p.policy,
      detail: `needs a human: ${(p.requires_approval ?? []).join(", ") || "nothing"} · agents: ${(p.agents ?? []).join(", ")}`,
    })),
    ...(cfg.stack ?? []).map((c) => ({ section: "stack" as const, label: c.component, detail: `${c.mode} · ${c.implementation}` })),
    ...(cfg.endpoints ?? []).map((e) => ({ section: "stack" as const, label: e.name, detail: e.url })),
    ...Object.entries(cfg.feature_flags ?? {}).map(([k, v]) => ({ section: "security" as const, label: k, detail: v ? "on" : "off" })),
  ];
  return rows.filter((r) => terms.every((t) => `${r.label} ${r.detail}`.toLowerCase().includes(t))).slice(0, 50);
}

/** Counts for the Overview tiles. */
export function overview(cfg: SystemConfig) {
  const stack = cfg.stack ?? [];
  return {
    real: stack.filter((c) => c.mode === "real").length,
    components: stack.length,
    healthy: stack.filter((c) => c.ok).length,
    models: (cfg.models.models ?? []).length,
    localOnly: !cfg.models.remote_enabled && (cfg.models.routes ?? []).every((r) => r.local !== false),
    agents: (cfg.agents ?? []).length,
    tools: (cfg.tools ?? []).length,
    gated: needsHuman(cfg.policies ?? []).length,
  };
}
