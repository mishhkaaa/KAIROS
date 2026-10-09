"use client";

import type { AgentManifest, SystemConfig, ToolSpec } from "@kairos/contracts";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Boxes, Check, CircleCheck, CircleX, Cpu, FileCode2, Gauge, KeyRound, Layers, Search, ShieldAlert, ShieldCheck, Sparkles, Users, Wrench } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useClient } from "@/app/providers";
import { AgentAvatar } from "@/components/desktop/agent-avatar";
import { Loading } from "@/components/desktop/orb";
import { useWindowNav, useWindowParams } from "@/components/desktop/window-context";
import { useSession } from "@/components/session";
import { architecture, isHealthy, searchConfig } from "@/lib/settings";
import { cn } from "@/lib/utils";
import { AppHeader, Card, errText, NotAllowed, Pill } from "./kit";

const SECTIONS = [
  { id: "overview", label: "Overview", icon: Gauge },
  { id: "models", label: "Models", icon: Sparkles },
  { id: "agents", label: "Agents", icon: Cpu },
  { id: "tools", label: "Tools & connectors", icon: Wrench },
  { id: "policies", label: "What needs a human", icon: ShieldCheck },
  { id: "security", label: "Security & access", icon: KeyRound },
  { id: "stack", label: "Stack", icon: Layers },
] as const;
type SectionId = (typeof SECTIONS)[number]["id"];

/** Every word of the query appears somewhere in these fields (as lib/settings.ts searchConfig matches). */
const has = (q: string, ...xs: (string | null | undefined)[]) => {
  const hay = xs.filter(Boolean).join(" ").toLowerCase();
  return q.split(/\s+/).filter(Boolean).every((t) => hay.includes(t));
};

function Source({ path }: { path?: string }) {
  if (!path) return null;
  return (
    <span className="inline-flex items-center gap-1 font-mono text-[11px] text-text-2" title="Change it in this file; kairosd reads it at start">
      <FileCode2 className="size-3" /> {path}
    </span>
  );
}

function Fact({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "ok" | "warn" }) {
  return (
    <div className="rounded-xl border border-hairline bg-surface-2 px-3 py-2">
      <dt className="text-xs text-text-2">{label}</dt>
      <dd className={cn("mt-0.5 font-mono text-[15px] font-semibold", tone === "ok" && "text-st-completed", tone === "warn" && "text-st-waiting")}>{value}</dd>
    </div>
  );
}

function Overview({ c }: { c: SystemConfig }) {
  const unavailable = c.models.routes?.filter((r) => !r.available).length ?? 0;
  const approvals = new Set((c.policies ?? []).flatMap((p) => p.requires_approval ?? []));
  const flags = c.feature_flags ?? {};
  return (
    <div className="space-y-4">
      <Card>
        <p className="text-[15px]">
          KAIROS <span className="font-mono">{c.versions.kairos}</span> runs <span className="font-semibold">{c.agents?.length ?? 0} agents</span> with{" "}
          <span className="font-semibold">{c.tools?.length ?? 0} tools</span> on <span className="font-semibold">{c.models.remote_enabled ? "local and remote" : "local"} models</span>. {approvals.size} kinds of action wait for a person; everything is audited.
        </p>
        <dl className="mt-3 grid grid-cols-2 gap-2 @2xl:grid-cols-4">
          <Fact label="contract" value={c.versions.contract} />
          <Fact label="environment" value={c.env} />
          <Fact label="default model" value={c.models.default.replace(/:.*$/, "")} />
          <Fact label="agent router" value={flags.jev_router ? "Jev, local" : "rules"} tone={flags.jev_router ? "ok" : "warn"} />
          <Fact label="data leaves the machine" value={c.models.remote_enabled ? "allowed" : "never"} tone={c.models.remote_enabled ? "warn" : "ok"} />
          <Fact label="sign-in" value={flags.google_sign_in ? "Google" : "dev"} tone={flags.google_sign_in ? "ok" : "warn"} />
          <Fact label="vault" value={flags.vault_encrypted ? "encrypted" : "dev obfuscation"} tone={flags.vault_encrypted ? "ok" : "warn"} />
          <Fact label="prompt firewall" value={c.firewall?.llm_classifier ? "regex + LLM" : "regex"} tone="ok" />
          <Fact label="models missing" value={unavailable} tone={unavailable ? "warn" : "ok"} />
        </dl>
      </Card>
      <Card title="Switches">
        <ul className="grid gap-1.5 @2xl:grid-cols-2">
          {Object.entries(flags).map(([k, v]) => (
            <li key={k} className="flex items-center gap-2 rounded-lg bg-surface-2 px-2.5 py-1.5 text-sm">
              <span className={cn("flex size-4 items-center justify-center rounded-full", v ? "bg-st-completed text-white" : "bg-surface-3")}>{v && <Check className="size-3" />}</span>
              <span className="font-mono text-[13px]">{k}</span>
              <span className="ml-auto text-xs text-text-2">{v ? "on" : "off"}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function Models({ c, q }: { c: SystemConfig; q: string }) {
  const routes = (c.models.routes ?? []).filter((r) => has(q, r.task_class, r.model));
  const models = (c.models.models ?? []).filter((m) => has(q, m.name, m.provider));
  return (
    <div className="space-y-4">
      <Card title="Routing: which model does which kind of thinking" aside={<Source path={c.models.config_file} />}>
        <ul className="space-y-1.5">
          {routes.map((r) => (
            <li key={r.task_class} className="flex items-center gap-2 text-sm">
              <span className="w-32 shrink-0 rounded-lg bg-surface-2 px-2 py-1 font-mono text-xs">{r.task_class}</span>
              <span className="h-px flex-1 bg-gradient-to-r from-hairline to-brand/40" aria-hidden />
              <ArrowRight className="size-3.5 text-brand" />
              <span className={cn("flex min-w-0 items-center gap-2 rounded-lg border px-2 py-1 font-mono text-xs", r.available ? "border-hairline bg-surface-1" : "border-st-failed/40 bg-st-failed/5")}>
                <span className="truncate">{r.model}</span>
                <Pill tone={r.local ? "ok" : "warn"}>{r.local ? "local" : "remote"}</Pill>
                {!r.available && <Pill tone="bad">not pulled</Pill>}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-text-2">
          Embeddings: <span className="font-mono">{c.models.embedding}</span>. Remote models are {c.models.remote_enabled ? "enabled" : "disabled"}; confidential and restricted data never reaches one either way.
        </p>
      </Card>
      <Card title={`Installed (${models.length})`}>
        <ul className="grid gap-2 @3xl:grid-cols-2">
          {models.map((m) => (
            <li key={m.name} className={cn("rounded-xl border border-hairline bg-surface-2 p-2.5", m.available === false && "opacity-50")}>
              <p className="flex items-center gap-2 font-mono text-sm font-semibold">
                {m.name}
                <span className="ml-auto text-xs font-normal text-text-2">{m.provider}</span>
              </p>
              <p className="mt-1 flex flex-wrap gap-1">
                {(m.capabilities ?? []).map((cap) => (
                  <Pill key={cap} mono>{cap}</Pill>
                ))}
                {m.context_window && <Pill mono>{m.context_window.toLocaleString()} ctx</Pill>}
                {m.embedding_dim && <Pill mono>{m.embedding_dim}-d</Pill>}
              </p>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function AgentCard({ a }: { a: AgentManifest }) {
  const tools = a.capabilities?.tools ?? [];
  const approval = a.approval?.required ?? [];
  return (
    <li className="rounded-2xl border border-hairline bg-surface-1 p-3 shadow-panel">
      <div className="flex items-start gap-3">
        <AgentAvatar agent={a.name} state="READY" size={44} />
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 font-mono text-sm font-semibold">
            {a.name} <span className="font-normal text-text-2">v{a.version}</span>
          </p>
          <p className="mt-0.5 text-sm text-text-2">{a.description}</p>
        </div>
      </div>
      <div className="mt-2.5 flex flex-wrap gap-1">
        {tools.map((t) => (
          <Pill key={t} mono tone={approval.includes(t) ? "warn" : "neutral"} title={approval.includes(t) ? "needs approval" : undefined}>
            {t}
          </Pill>
        ))}
        {!tools.length && <span className="text-xs text-text-2">no tools: reads knowledge only</span>}
      </div>
      <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-text-2">
        <span>{a.runtime?.model_policy ?? "local-preferred"}</span>
        <span>{a.resources?.max_tokens_per_task?.toLocaleString() ?? "?"} tokens/task</span>
        <span>{a.resources?.max_tool_calls ?? "?"} tool calls</span>
        {!!a.memory?.mounts?.length && <span>mounts {a.memory.mounts.join(", ")}</span>}
        {!!a.network?.allow?.length && <span>net {a.network.allow.join(", ")}</span>}
      </p>
    </li>
  );
}

function Agents({ c, q }: { c: SystemConfig; q: string }) {
  const agents = (c.agents ?? []).filter((a) => has(q, a.name, a.description, ...(a.capabilities?.tools ?? [])));
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-2">Each agent is a manifest: what it may call, how much it may spend, what it may see. The planner also makes new agents on demand.</p>
        <Source path={c.paths?.manifests_dir} />
      </div>
      <ul className="grid gap-3 @3xl:grid-cols-2">
        {agents.map((a) => (
          <AgentCard key={a.name} a={a} />
        ))}
      </ul>
    </div>
  );
}

function ToolRow({ t, q }: { t: ToolSpec; q: string }) {
  const ops = (t.operations ?? []).filter((o) => has(q, t.name, o.name, o.capability, o.description));
  if (!ops.length) return null;
  return (
    <Card title={<span className="font-mono">{t.name}</span>} aside={<Pill mono>{t.transport}</Pill>}>
      <ul className="divide-y divide-hairline">
        {ops.map((o) => (
          <li key={o.name} className="flex flex-wrap items-center gap-2 py-1.5 text-sm">
            <span className="w-40 shrink-0 font-mono text-xs">{o.name}</span>
            <span className="min-w-0 flex-1 truncate text-text-2" title={o.description}>{o.description}</span>
            <Pill mono tone={o.risk === "high" || o.risk === "critical" ? "bad" : o.risk === "medium" ? "warn" : "neutral"}>{o.capability}</Pill>
            {o.requires_sandbox && <Pill>sandbox</Pill>}
            {o.reversible === false && <Pill tone="warn">irreversible</Pill>}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Tools({ c, q }: { c: SystemConfig; q: string }) {
  const client = useClient();
  const connectors = useQuery({ queryKey: ["connectors"], queryFn: () => client.connectors(), staleTime: 30_000 });
  return (
    <div className="space-y-3">
      <Card title="Connectors" aside={<Link href="/connections" className="text-xs text-brand hover:underline">Manage in Connections</Link>}>
        <ul className="flex flex-wrap gap-2">
          {(connectors.data ?? []).map((x) => (
            <li key={x.connector_id} className="flex items-center gap-2 rounded-xl bg-surface-2 px-3 py-1.5 text-sm">
              <span className={cn("size-2 rounded-full", x.status === "connected" ? "bg-st-completed" : "bg-surface-3")} />
              {x.name}
              <span className="font-mono text-xs text-text-2">{x.status === "connected" ? (x.mode === "live" ? "live" : "demo data") : "off"}</span>
            </li>
          ))}
          {connectors.isError && <li className="text-sm text-text-2">Connectors unavailable.</li>}
        </ul>
      </Card>
      {(c.tools ?? []).map((t) => (
        <ToolRow key={t.name} t={t} q={q} />
      ))}
    </div>
  );
}

function Policies({ c, q }: { c: SystemConfig; q: string }) {
  const policies = (c.policies ?? []).filter((p) => has(q, p.policy, ...(p.agents ?? []), ...(p.requires_approval ?? []), ...(p.denied ?? [])));
  const caps = [...new Set(policies.flatMap((p) => [...(p.requires_approval ?? []), ...(p.auto_approved ?? []), ...(p.denied ?? [])]))].sort();
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-text-2">Before an agent acts, the kernel checks these. A highlighted cell means the action pauses until an approver says yes.</p>
        <Source path={c.paths?.policies_dir} />
      </div>
      <Card className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="text-left text-xs text-text-2">
              <th className="pb-2 font-medium">Action</th>
              {policies.map((p) => (
                <th key={p.policy} className="pb-2 text-center font-mono font-medium" title={`priority ${p.priority}; agents ${(p.agents ?? []).join(", ")}`}>
                  {p.policy.replace(/-v\d+$/, "")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {caps.map((cap) => (
              <tr key={cap}>
                <td className="py-1.5 font-mono text-xs">{cap}</td>
                {policies.map((p) => {
                  const need = p.requires_approval?.includes(cap);
                  const auto = p.auto_approved?.includes(cap);
                  const deny = p.denied?.includes(cap);
                  return (
                    <td key={p.policy} className="py-1 text-center">
                      {deny ? (
                        <span className="inline-flex items-center gap-1 rounded-md bg-st-failed/12 px-1.5 py-0.5 text-[11px] font-medium text-st-failed"><ShieldAlert className="size-3" /> never</span>
                      ) : need ? (
                        <span className="inline-flex items-center gap-1 rounded-md bg-st-waiting/15 px-1.5 py-0.5 text-[11px] font-medium text-st-waiting"><Users className="size-3" /> a person</span>
                      ) : auto ? (
                        <span className="inline-flex items-center gap-1 rounded-md bg-st-completed/12 px-1.5 py-0.5 text-[11px] font-medium text-st-completed"><Check className="size-3" /> auto</span>
                      ) : (
                        <span className="text-text-2/40">·</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function Security({ c }: { c: SystemConfig }) {
  const flags = c.feature_flags ?? {};
  const { me } = useSession();
  const rows: { title: string; ok: boolean; now: string; how: string }[] = [
    {
      title: "Sign-in",
      ok: !!flags.google_sign_in,
      now: flags.google_sign_in ? "Google accounts; a session per person, expiring after a working day" : "Dev mode: email sign-in, and header callers act as the org owner",
      how: "KAIROS_AUTH=google and KAIROS_GOOGLE_CLIENT_ID=<your OAuth web client id>",
    },
    {
      title: "Connector vault",
      ok: !!flags.vault_encrypted,
      now: flags.vault_encrypted ? "Tokens are encrypted (Fernet) at rest" : "Tokens are only obfuscated: fine for a demo, not for real accounts",
      how: "KAIROS_VAULT_KEY=<32 random bytes, base64>; scripts/win/start-kairosd.ps1 makes one in .data on first start",
    },
    {
      title: "Prompt firewall",
      ok: true,
      now: c.firewall?.llm_classifier ? "Pattern screening plus a local classifier model on every retrieved document" : "Pattern screening on every retrieved document",
      how: "KAIROS_FIREWALL_LLM=true adds the classifier",
    },
    {
      title: "Models",
      ok: !c.models.remote_enabled,
      now: c.models.remote_enabled ? "Remote models may be used for public and internal data" : "Every model runs on this machine",
      how: `${c.models.config_file}: remote_enabled`,
    },
  ];
  return (
    <div className="space-y-3">
      <ul className="space-y-2">
        {rows.map((r) => (
          <li key={r.title} className="flex gap-3 rounded-2xl border border-hairline bg-surface-1 p-3 shadow-panel">
            {r.ok ? <CircleCheck className="mt-0.5 size-5 shrink-0 text-st-completed" /> : <ShieldAlert className="mt-0.5 size-5 shrink-0 text-st-waiting" />}
            <div className="min-w-0">
              <p className="font-semibold">{r.title}</p>
              <p className="text-sm">{r.now}</p>
              <p className="mt-1 font-mono text-[11px] text-text-2">{r.how}</p>
            </div>
          </li>
        ))}
      </ul>
      <Card title="People and roles" aside={<Link href="/organization" className="text-xs text-brand hover:underline">Open Organization</Link>}>
        <p className="text-sm">
          You are <span className="font-semibold">{me?.user.email ?? "the local developer"}</span>, <span className="font-mono">{me?.role ?? "owner"}</span> of {me?.org?.name ?? "the org"}. Roles decide who may start tasks, approve actions, add knowledge, connect services and see these settings (<span className="font-mono">policies/rbac/roles.yaml</span>).
        </p>
      </Card>
    </div>
  );
}

function Stack({ c, q }: { c: SystemConfig; q: string }) {
  const client = useClient();
  // Health refreshes more often than the config: the map shows the live state over the configured stack.
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => client.status(), refetchInterval: 15_000 });
  const layers = architecture(c.stack ?? [], status.data?.components)
    .map((l) => ({ ...l, nodes: l.nodes.filter((s) => has(q, s.component, s.implementation, s.mode)) }))
    .filter((l) => l.nodes.length);
  return (
    <div className="space-y-3">
      <Card title="The running system, layer by layer" aside={<span className="text-[11px] text-text-2">health live from /system/status</span>}>
        {!layers.length && <p className="text-sm text-text-2">No component matches the search.</p>}
        <div className="space-y-2.5">
          {layers.map((l) => (
            <div key={l.title} className="flex flex-col gap-1.5 @2xl:flex-row @2xl:items-stretch">
              <p className="w-40 shrink-0 pt-2 text-xs font-semibold uppercase tracking-wider text-text-2">{l.title}</p>
              <ul className="grid flex-1 gap-2 @2xl:grid-cols-2 @5xl:grid-cols-3">
                {l.nodes.map((s) => (
                  <li key={s.component} className="rounded-xl border border-hairline bg-surface-2 p-2.5" title={s.detail || undefined}>
                    <p className="flex items-center gap-2 text-sm font-semibold">
                      {isHealthy(s) ? <CircleCheck className="size-4 text-st-completed" /> : <CircleX className="size-4 text-st-failed" />}
                      {s.component}
                      <Pill tone={s.mode === "real" ? "ok" : "warn"} mono>{s.mode}</Pill>
                    </p>
                    <p className="mt-1 truncate font-mono text-[11px] text-text-2" title={s.implementation}>{s.implementation}</p>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Card>
      <div className="grid gap-3 @3xl:grid-cols-2">
        <Card title="Endpoints" aside={<span className="text-[11px] text-text-2">credentials redacted</span>}>
          <ul className="space-y-1">
            {(c.endpoints ?? []).map((e) => (
              <li key={e.name} className="flex gap-2 text-sm">
                <span className="w-20 shrink-0 text-text-2">{e.name}</span>
                <span className="truncate font-mono text-xs">{e.url}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Paths">
          <ul className="space-y-1">
            {Object.entries(c.paths ?? {}).map(([k, v]) => (
              <li key={k} className="flex gap-2 text-sm">
                <span className="w-28 shrink-0 text-text-2">{k}</span>
                <span className="truncate font-mono text-xs">{v}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 font-mono text-[11px] text-text-2">
            python {c.versions.python}
            {c.versions.node ? ` · node ${c.versions.node}` : ""}
          </p>
        </Card>
      </div>
    </div>
  );
}

/** The settings centre: one read-only picture of the running system, from GET /system/config. Each section names the
 *  file that changes it. The architecture map, search and summaries come from lib/settings.ts. */
export function SettingsApp() {
  const client = useClient();
  const { me, can } = useSession();
  const params = useWindowParams();
  const nav = useWindowNav();
  const [q, setQ] = useState("");
  const section = (SECTIONS.find((s) => s.id === params.get("section"))?.id ?? "overview") as SectionId;
  const config = useQuery({ queryKey: ["system-config"], queryFn: () => client.systemConfig(), enabled: can("config.read"), staleTime: 30_000 });
  const query = q.trim().toLowerCase();
  const hits = useMemo(() => (config.data && query ? searchConfig(config.data, query) : []), [config.data, query]);
  const counts = useMemo(() => {
    if (!query) return {} as Partial<Record<SectionId, number>>;
    const out: Partial<Record<SectionId, number>> = { models: 0, agents: 0, tools: 0, policies: 0, stack: 0 };
    for (const h of hits) out[h.section as SectionId] = (out[h.section as SectionId] ?? 0) + 1;
    return out;
  }, [hits, query]);
  const go = (id: SectionId) => nav.navigate(id === "overview" ? "/settings" : `/settings?section=${id}`);

  if (!can("config.read")) return <NotAllowed role={me?.role} permission="config.read" what="see the system settings" />;

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 @3xl:flex-row">
      <aside className="flex shrink-0 flex-col gap-2 @3xl:w-56">
        <label className="flex items-center gap-2 rounded-xl border border-hairline bg-surface-2 px-2.5 focus-within:border-brand">
          <Search className="size-3.5 text-text-2" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search settings" aria-label="Search settings" className="h-9 min-w-0 flex-1 bg-transparent text-sm outline-none" />
        </label>
        <nav aria-label="Settings sections" className="flex gap-1 overflow-x-auto @3xl:flex-col">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => go(s.id)}
              aria-current={section === s.id ? "page" : undefined}
              className={cn("flex shrink-0 items-center gap-2 rounded-xl px-2.5 py-2 text-left text-sm transition-colors", section === s.id ? "bg-brand text-white" : "hover:bg-surface-3")}
            >
              <s.icon className="size-4" />
              <span className="flex-1">{s.label}</span>
              {query && counts[s.id] !== undefined && <span className={cn("rounded-full px-1.5 font-mono text-[11px]", section === s.id ? "bg-white/25" : "bg-surface-3")}>{counts[s.id]}</span>}
            </button>
          ))}
        </nav>
        <p className="mt-auto hidden text-[11px] text-text-2 @3xl:block">
          <Boxes className="mr-1 inline size-3" />
          Read-only here. Each section names the file that changes it; kairosd reads them at start.
        </p>
      </aside>
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto pr-1">
        <AppHeader app="settings" title={SECTIONS.find((s) => s.id === section)!.label} sub={config.data ? `KAIROS ${config.data.versions.kairos} · contract ${config.data.versions.contract}` : undefined} />
        {config.data && query && (
          <Card className="mt-4" title={`Everywhere: ${hits.length} ${hits.length === 1 ? "match" : "matches"}`}>
            <ul className="max-h-48 space-y-1 overflow-y-auto">
              {hits.map((h, i) => (
                <li key={`${h.section}-${h.label}-${i}`}>
                  <button type="button" onClick={() => go(h.section as SectionId)} className="flex w-full items-baseline gap-2 rounded-lg px-2 py-1 text-left text-sm hover:bg-surface-3">
                    <span className="w-24 shrink-0 font-mono text-[11px] text-text-2">{SECTIONS.find((s) => s.id === h.section)?.label}</span>
                    <span className="font-medium">{h.label}</span>
                    <span className="truncate text-xs text-text-2">{h.detail}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        )}
        <div className="mt-4">
          {config.isPending ? (
            <Loading label="Reading the system" state="searching" />
          ) : config.isError ? (
            <p className="text-sm text-st-failed">Could not read the configuration: {errText(config.error)}</p>
          ) : section === "overview" ? (
            <Overview c={config.data} />
          ) : section === "models" ? (
            <Models c={config.data} q={query} />
          ) : section === "agents" ? (
            <Agents c={config.data} q={query} />
          ) : section === "tools" ? (
            <Tools c={config.data} q={query} />
          ) : section === "policies" ? (
            <Policies c={config.data} q={query} />
          ) : section === "security" ? (
            <Security c={config.data} />
          ) : (
            <Stack c={config.data} q={query} />
          )}
        </div>
      </div>
    </div>
  );
}
