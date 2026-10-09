"use client";

import { Loading } from "@/components/desktop/orb";
import type { AgentManifest, ToolSpec } from "@kairos/contracts";
import { useQuery } from "@tanstack/react-query";
import { Bot, Wrench } from "lucide-react";
import { useClient } from "@/app/providers";
import { RiskBadge } from "@/components/status";
import { cn } from "@/lib/utils";

function Chips({ items, tone = "border-line text-text-2" }: { items?: string[]; tone?: string }) {
  if (!items?.length) return <span className="text-sm text-muted-foreground">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((c) => (
        <span key={c} className={cn("rounded-md border px-1.5 py-0.5 font-mono text-xs", tone)}>
          {c}
        </span>
      ))}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] items-start gap-2 text-sm">
      <span className="text-text-2">{label}</span>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function AgentCard({ a }: { a: AgentManifest }) {
  const r = a.resources;
  const policy = a.runtime.model_policy;
  return (
    <article className="space-y-3 rounded-xl border border-line bg-surface-1 p-4 shadow-panel">
      <header>
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-mono text-base font-semibold">{a.name}</h2>
          {a.version && <span className="font-mono text-xs text-text-2">v{a.version}</span>}
        </div>
        <p className="mt-1 text-sm text-text-2">{a.description}</p>
      </header>
      <Row label="Model policy">
        <span className="font-mono text-sm">{String(policy ?? "—")}</span>
        {a.runtime.model_hint && <span className="font-mono text-xs text-text-2"> · {a.runtime.model_hint}</span>}
      </Row>
      <Row label="Tools">
        <Chips items={a.capabilities?.tools} tone="border-brand/40 text-brand" />
      </Row>
      <Row label="Knowledge">
        <Chips items={a.capabilities?.knowledge} tone="border-line text-ev-knowledge" />
      </Row>
      {!!a.capabilities?.agents?.length && (
        <Row label="Can spawn">
          <Chips items={a.capabilities.agents} />
        </Row>
      )}
      <Row label="Memory mounts">
        <Chips items={a.memory?.mounts} tone="border-line text-ev-knowledge" />
      </Row>
      {!!a.approval?.required?.length && (
        <Row label="Needs approval">
          <Chips items={a.approval.required} tone="border-st-waiting/50 text-st-waiting" />
        </Row>
      )}
      <Row label="Limits">
        <span className="font-mono text-xs text-text-2">
          {[
            r?.max_tokens_per_task && `${r.max_tokens_per_task.toLocaleString()} tokens/task`,
            r?.max_tool_calls && `${r.max_tool_calls} tool calls`,
            r?.cpu && `${r.cpu} CPU`,
            r?.memory && `${r.memory} RAM`,
            r?.gpu ? `${r.gpu} GPU` : null,
          ]
            .filter(Boolean)
            .join(" · ") || "—"}
        </span>
      </Row>
      {!!a.network?.allow?.length && (
        <Row label="Network">
          <Chips items={a.network.allow} />
        </Row>
      )}
    </article>
  );
}

function ToolTable({ tools }: { tools: ToolSpec[] }) {
  const ops = tools.flatMap((t) => t.operations.map((o) => ({ tool: t, op: o })));
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface-1 shadow-panel">
      <table className="w-full text-sm">
        <thead className="border-b border-line text-left text-xs uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="px-4 py-2.5 font-semibold">Operation</th>
            <th className="px-4 py-2.5 font-semibold">Capability</th>
            <th className="px-4 py-2.5 font-semibold">Risk</th>
            <th className="px-4 py-2.5 font-semibold">Reversible</th>
            <th className="px-4 py-2.5 font-semibold">Sandbox</th>
            <th className="px-4 py-2.5 font-semibold">Description</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {ops.map(({ tool, op }) => (
            <tr key={`${tool.name}.${op.name}`}>
              <td className="px-4 py-2.5 font-mono">
                {tool.name}.{op.name}
              </td>
              <td className="px-4 py-2.5 font-mono text-brand">{op.capability}</td>
              <td className="px-4 py-2.5">
                <RiskBadge risk={op.risk} />
              </td>
              <td className="px-4 py-2.5 text-text-2">{op.reversible ? "yes" : "no"}</td>
              <td className="px-4 py-2.5 text-text-2">{op.requires_sandbox ? "yes" : "no"}</td>
              <td className="px-4 py-2.5 text-text-2">{op.description || tool.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Read-only: what the kernel can spawn and what the tools can do. Agents are defined by manifests on disk. */
export function ProgramsApp() {
  const client = useClient();
  const agents = useQuery({ queryKey: ["registry-agents"], queryFn: () => client.registry() });
  const tools = useQuery({ queryKey: ["registry-tools"], queryFn: () => client.registryTools() });
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <Bot className="size-6 text-brand" aria-hidden /> Agents
        </h1>
        <p className="mt-1 text-sm text-text-2">
          The agent registry, read from the manifests on this machine: capabilities, knowledge mounts and resource limits.
        </p>
      </div>
      {agents.isError && (
        <div className="flex items-center justify-between rounded-xl border border-st-failed/50 bg-st-failed/8 p-4 text-sm text-st-failed">
          <span>Gateway unreachable: {String(agents.error)}</span>
          <button type="button" onClick={() => agents.refetch()} className="rounded-md border border-line px-3 py-1.5 text-sm text-foreground hover:bg-surface-3">
            Retry
          </button>
        </div>
      )}
      {agents.isLoading && <Loading label="Reading the agent registry" />}
      {agents.isSuccess && agents.data.length === 0 && (
        <p className="text-sm text-text-2">No agent manifests found on this machine.</p>
      )}
      <div className="grid gap-4 @3xl:grid-cols-2 @[96rem]:grid-cols-3">
        {(agents.data ?? []).map((a) => (
          <AgentCard key={a.name} a={a} />
        ))}
      </div>
      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-[17px] font-semibold">
          <Wrench className="size-4.5 text-text-2" aria-hidden /> Tools <span className="font-mono text-sm font-normal text-text-2">({tools.data?.length ?? 0})</span>
        </h2>
        {tools.isSuccess && tools.data.length === 0 && <p className="text-sm text-text-2">No tools registered.</p>}
        {tools.data && tools.data.length > 0 && <ToolTable tools={tools.data} />}
      </section>
    </div>
  );
}
