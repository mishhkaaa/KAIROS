"use client";

import type { GraphResult } from "@kairos/contracts";
import { useQuery } from "@tanstack/react-query";
import { Background, type Edge, MarkerType, type Node, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ArrowDownLeft, ArrowUpRight, EyeOff, ShieldAlert } from "lucide-react";
import { useTheme } from "next-themes";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useClient } from "@/app/providers";
import { KairosError } from "@/lib/kairos-client";
import { Chip, PrivacyChip, TrustChip } from "./chips";

function Markdown({ body, onLink }: { body: string; onLink: (href: string) => void }) {
  return (
    <div className="space-y-3 text-[15px] leading-relaxed [&_code]:rounded [&_code]:bg-surface-3 [&_code]:px-1 [&_code]:font-mono [&_code]:text-sm [&_h1]:text-xl [&_h1]:font-semibold [&_h2]:mt-5 [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:font-semibold [&_li]:ml-5 [&_ol]:list-decimal [&_table]:w-full [&_table]:text-sm [&_td]:border [&_td]:border-line [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-line [&_th]:bg-surface-2 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_ul]:list-disc">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a
              href={href}
              className="text-ev-knowledge underline underline-offset-2"
              onClick={(e) => {
                if (href && !/^[a-z]+:/i.test(href)) {
                  e.preventDefault();
                  onLink(href);
                }
              }}
            >
              {children}
            </a>
          ),
        }}
      >
        {body}
      </ReactMarkdown>
    </div>
  );
}

/** Relative OKF link (../systems/payments-api.md) → /org path, mirroring util.okf_file_to_org_path. */
export function resolveOkfLink(fromPath: string, okfFile: string, href: string): string {
  const baseDir = okfFile.split("/").slice(0, -1);
  const parts = [...baseDir, ...href.split("#")[0].split("/")];
  const out: string[] = [];
  for (const p of parts) {
    if (p === "..") out.pop();
    else if (p && p !== ".") out.push(p);
  }
  const rel = out.join("/").replace(/\.md$/, "").replace(/(^|\/)index$/, "");
  return rel ? `/org/${rel}` : fromPath.split("/").slice(0, 2).join("/");
}

export function GraphView({ graph, onSelect, height = 440 }: { graph: GraphResult; onSelect: (p: string) => void; height?: number }) {
  const { resolvedTheme } = useTheme();
  const others = graph.nodes.filter((n) => n.path !== graph.root);
  const r = 160;
  const nodes: Node[] = [
    {
      id: graph.root,
      position: { x: 0, y: 0 },
      data: { label: graph.nodes.find((n) => n.path === graph.root)?.title ?? graph.root },
      style: { background: "var(--brand-subtle)", color: "var(--text)", border: "2px solid var(--brand)", borderRadius: 10, fontSize: 13, width: 190 },
    },
    ...others.map((n, i) => {
      const a = (2 * Math.PI * i) / Math.max(others.length, 1) - Math.PI / 2;
      return {
        id: n.path,
        position: { x: Math.cos(a) * r * 1.4, y: Math.sin(a) * r },
        data: { label: n.title || n.path.split("/").pop() },
        style: { background: "var(--surface-1)", color: "var(--text)", border: "1px solid var(--line-strong)", borderRadius: 10, fontSize: 13, width: 180 },
      };
    }),
  ];
  const edges: Edge[] = graph.edges.map((e) => ({
    id: `${e.src}-${e.relation}-${e.dst}`,
    source: e.src,
    target: e.dst,
    label: e.relation,
    labelStyle: { fill: "var(--text-2)", fontSize: 11 },
    labelBgStyle: { fill: "var(--bg)" },
    style: { stroke: e.relation === "links_to" ? "var(--line-strong)" : "var(--ev-knowledge)" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--line-strong)" },
  }));
  return (
    <div className="rounded-xl border border-line bg-surface-2" style={{ height }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        nodesConnectable={false}
        colorMode={resolvedTheme === "light" ? "light" : "dark"}
        style={{ background: "transparent" }}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, n) => onSelect(n.id)}
      >
        <Background gap={24} size={1} color="var(--line)" />
      </ReactFlow>
    </div>
  );
}

function LinkList({ title, icon: Icon, paths, onSelect }: { title: string; icon: typeof ArrowUpRight; paths: string[]; onSelect: (p: string) => void }) {
  return (
    <section className="rounded-xl border border-line bg-surface-1 p-3">
      <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        <Icon className="size-3.5" aria-hidden /> {title} ({paths.length})
      </h3>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {paths.map((l) => (
          <button key={l} type="button" onClick={() => onSelect(l)} className="rounded-md border border-line bg-surface-2 px-2 py-0.5 font-mono text-xs text-ev-knowledge hover:bg-surface-3">
            {l}
          </button>
        ))}
        {!paths.length && <span className="text-sm text-muted-foreground">none</span>}
      </div>
    </section>
  );
}

export function ObjectView({ path, onSelect }: { path: string; onSelect: (p: string) => void }) {
  const client = useClient();
  const obj = useQuery({ queryKey: ["knowledge-object", path], queryFn: () => client.object(path), retry: false });
  const graph = useQuery({ queryKey: ["knowledge-graph", path], queryFn: () => client.graph(path, 1), retry: false, enabled: obj.isSuccess });

  if (obj.isLoading) return <p className="text-sm text-muted-foreground">Loading {path}…</p>;
  if (obj.isError) {
    const e = obj.error;
    if (e instanceof KairosError && e.code === "KNOWLEDGE_FORBIDDEN")
      return (
        <div className="rounded-xl border border-st-failed/50 bg-st-failed/10 p-5">
          <p className="flex items-center gap-2 font-semibold text-st-failed"><EyeOff className="size-5" /> Hidden by policy</p>
          <p className="mt-1 text-sm text-muted-foreground">{path} is outside your scope or above your privacy clearance.</p>
        </div>
      );
    if (e instanceof KairosError && e.code === "KNOWLEDGE_NOT_FOUND")
      return <p className="text-sm text-muted-foreground">{path} is a folder without an index document. Pick a file on the left.</p>;
    return <p className="text-sm text-st-failed">{String(e)}</p>;
  }
  const o = obj.data!;
  const fm = o.frontmatter;
  const edges = graph.data?.edges ?? [];
  const outgoing = edges.filter((e) => e.src === o.path).map((e) => e.dst);
  const incoming = [...new Set(edges.filter((e) => e.dst === o.path).map((e) => e.src))];
  const pv = o.provenance;
  return (
    <article className="space-y-5">
      <header className="space-y-2">
        <p className="font-mono text-sm text-muted-foreground">{o.path} <span className="opacity-60">({o.okf_file} · {o.content_hash})</span></p>
        <h1 className="text-2xl font-semibold">{fm.title}</h1>
        {fm.description && <p className="text-muted-foreground">{fm.description}</p>}
        <div className="flex flex-wrap gap-1.5">
          <Chip label="type" value={fm.type} className="border-border" />
          <PrivacyChip value={fm.privacy ?? "internal"} />
          <TrustChip value={pv.trust ?? fm.trust} />
          <Chip label="source" value={`${pv.source}${pv.source_version ? ` @ ${pv.source_version}` : ""}`} className="border-border" />
          {pv.verification_status && <Chip label="verification" value={pv.verification_status} className="border-border" />}
          {fm.owner && <Chip label="owner" value={fm.owner} className="border-border" />}
          {pv.updated_at && <Chip label="updated" value={pv.updated_at.slice(0, 10)} className="border-border" />}
          {(fm.tags ?? []).map((t) => <Chip key={t} value={`#${t}`} className="border-border text-muted-foreground" />)}
        </div>
        {(pv.trust ?? fm.trust) === "untrusted" && (
          <p className="flex items-center gap-2 rounded-lg border border-untrusted/50 bg-untrusted-bg px-3 py-2 text-sm text-untrusted">
            <ShieldAlert className="size-4" /> Untrusted external content: agents receive it as quoted data and the context firewall screens it.
          </p>
        )}
      </header>
      <div className="rounded-xl border border-line bg-surface-1 p-5 shadow-panel">
        <Markdown body={o.body} onLink={(href) => onSelect(resolveOkfLink(o.path, o.okf_file, href))} />
      </div>
      <div className="grid gap-4 @3xl:grid-cols-2">
        <LinkList title="Links to" icon={ArrowUpRight} paths={[...new Set([...(o.links ?? []), ...outgoing])]} onSelect={onSelect} />
        <LinkList title="Linked from" icon={ArrowDownLeft} paths={incoming} onSelect={onSelect} />
      </div>
      {graph.data && graph.data.nodes.length > 1 && (
        <section>
          <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Relationship graph (depth 1)</h3>
          <GraphView graph={graph.data} onSelect={onSelect} height={360} />
        </section>
      )}
    </article>
  );
}
