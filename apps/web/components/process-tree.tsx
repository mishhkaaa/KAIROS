"use client";

import type { AgentProcess, Event } from "@kairos/contracts";
import {
  Background,
  type Edge,
  Handle,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  useStore,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Hourglass, Pause, Play, Skull } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useMemo, useRef, useState } from "react";
import { Orb } from "@/components/desktop/orb";
import { ORB_LABEL, orbFor } from "@/lib/desktop/orb";
import { NODE_H, NODE_W, columnsFor, layout } from "@/lib/process-layout";
import { agentTone } from "@/lib/tones";
import { cn } from "@/lib/utils";
import { AgentStateBadge } from "./status";
import { availableActions, type ProcessAction, useProcessActions } from "./task/process-actions";


interface NodeData extends Record<string, unknown> {
  proc: AgentProcess;
  /** The last event this process produced: what its orb shows it doing. */
  last?: Event;
  selected: boolean;
  onAction: (a: ProcessAction, p: AgentProcess) => void;
  onSelect: (pid: number) => void;
}
type ProcNode = Node<NodeData, "proc">;

export const tokensOf = (p: AgentProcess) => (p.usage?.tokens_prompt ?? 0) + (p.usage?.tokens_completion ?? 0);

const ACTION_ICON = { pause: Pause, resume: Play, kill: Skull } as const;

function ProcessNode({ data }: NodeProps<ProcNode>) {
  const p = data.proc;
  const tone = agentTone(p.state);
  const orb = orbFor(p.state, data.last, p.waiting_on);
  const actions = availableActions(p).filter((a): a is keyof typeof ACTION_ICON => a in ACTION_ICON);
  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={data.selected}
      aria-label={`PID ${p.pid} ${p.agent}, ${p.state}`}
      onClick={() => data.onSelect(p.pid)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && data.onSelect(p.pid)}
      className={cn(
        "cursor-pointer rounded-xl border bg-surface-1 px-3 py-2.5 shadow-panel transition-[border-color,box-shadow] duration-200",
        data.selected ? "border-brand ring-2 ring-brand/30" : tone.border,
      )}
      style={{ width: NODE_W, minHeight: NODE_H }}
    >
      <Handle type="target" position={Position.Top} className="!border-0 !bg-transparent" />
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-base font-bold">
          <span className="text-muted-foreground">PID </span>
          {p.pid}
        </span>
        <AgentStateBadge state={p.state} />
      </div>
      <p className="mt-0.5 flex items-center gap-1.5 truncate text-sm font-medium">
        {orb && <Orb state={orb} label={ORB_LABEL[orb]} />}
        <span className="truncate">{p.agent}</span>
        {orb && <span className="ml-auto shrink-0 text-xs font-normal text-text-2">{ORB_LABEL[orb]}</span>}
      </p>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 font-mono text-xs text-text-2">
        <span>{tokensOf(p).toLocaleString()} tok</span>
        {(p.usage?.tool_calls ?? 0) > 0 && <span>· {p.usage?.tool_calls} tools</span>}
      </div>
      {p.waiting_on && (
        <p className={cn("mt-1 flex items-center gap-1 truncate font-mono text-xs", tone.text)}>
          <Hourglass className="size-3.5 shrink-0" aria-hidden /> {p.waiting_on}
        </p>
      )}
      {actions.length > 0 && (
        <div className="nodrag mt-2 flex gap-1">
          {actions.map((a) => {
            const Icon = ACTION_ICON[a];
            return (
              <button
                key={a}
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  data.onAction(a, p);
                }}
                aria-label={`${a} PID ${p.pid}`}
                className={cn(
                  "flex items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-xs capitalize text-text-2 transition-colors hover:bg-surface-3 hover:text-foreground",
                  a === "kill" && "hover:border-st-failed hover:text-st-failed",
                )}
              >
                <Icon className="size-3.5" aria-hidden /> {a}
              </button>
            );
          })}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!border-0 !bg-transparent" />
    </div>
  );
}

const nodeTypes = { proc: ProcessNode };

/** Re-fit whenever the set of processes or their parents change, and when the pane is resized. */
function FitOnGrowth({ pids }: { pids: string }) {
  const { fitView } = useReactFlow();
  const width = useStore((s) => s.width);
  const height = useStore((s) => s.height);
  useEffect(() => {
    const fit = () => void fitView({ padding: 0.08, maxZoom: 1.2, duration: 220 });
    const timers = [setTimeout(fit, 60), setTimeout(fit, 450)];
    return () => timers.forEach(clearTimeout);
  }, [pids, fitView]);
  useEffect(() => {
    if (!width || !height) return;
    const timer = setTimeout(() => void fitView({ padding: 0.08, maxZoom: 1.2, duration: 150 }), 150);
    return () => clearTimeout(timer);
  }, [width, height, fitView]);
  return null;
}

export function ProcessTree({
  processes,
  last = {},
  selected = null,
  onSelect = () => {},
}: {
  processes: Record<number, AgentProcess>;
  last?: Record<number, Event>;
  selected?: number | null;
  onSelect?: (pid: number) => void;
}) {
  const { act, dialog } = useProcessActions();
  const { resolvedTheme } = useTheme();
  const procs = useMemo(() => Object.values(processes), [processes]);
  const pane = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = pane.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const cols = width ? columnsFor(width) : Number.POSITIVE_INFINITY;
  const { nodes, edges } = useMemo(() => {
    const { positions, edges: pairs } = layout(procs, cols);
    const nodes: ProcNode[] = procs.map((p) => ({
      id: String(p.pid),
      type: "proc",
      position: positions[p.pid] ?? { x: 0, y: 0 },
      data: { proc: p, last: last[p.pid], selected: p.pid === selected, onAction: act, onSelect },
      draggable: false,
    }));
    const edges: Edge[] = pairs.map(([a, b]) => {
      const child = processes[b];
      return {
        id: `${a}-${b}`,
        source: String(a),
        target: String(b),
        animated: child?.state === "RUNNING",
        style: { stroke: agentTone(child?.state).stroke, strokeWidth: 2, opacity: 0.75 },
      };
    });
    return { nodes, edges };
    // `act` is recreated each render but only opens a dialog or fires a mutation; depending on it would rebuild the graph every render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [procs, processes, last, selected, onSelect, cols]);

  return (
    <div ref={pane} className="relative h-full min-h-0">
      {procs.length === 0 ? (
        <p className="p-4 text-sm text-muted-foreground">No processes yet.</p>
      ) : (
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.08, maxZoom: 1.2 }}
            nodesConnectable={false}
            proOptions={{ hideAttribution: true }}
            colorMode={resolvedTheme === "light" ? "light" : "dark"}
            minZoom={0.3}
            style={{ background: "transparent" }}
          >
            <Background gap={24} size={1} color="var(--line)" />
            <FitOnGrowth pids={`${cols}|${procs.map((p) => `${p.pid}<${p.ppid ?? ""}`).sort().join(",")}`} />
          </ReactFlow>
        </ReactFlowProvider>
      )}
      {dialog}
    </div>
  );
}
