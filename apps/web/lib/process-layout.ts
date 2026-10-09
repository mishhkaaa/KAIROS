// Process-tree layout, kept pure so it's tested. Top-down: a parent sits centred over its children. When a parent's
// children are all leaves and more than fit across the pane, they wrap into rows (a projector at 1366 px otherwise
// shrinks five nodes in one row to unreadable).
import type { AgentProcess } from "@kairos/contracts";

export const NODE_W = 212;
export const NODE_H = 112;
export const GAP_X = 20;
export const GAP_Y = 64;

export interface Layout {
  positions: Record<number, { x: number; y: number }>;
  edges: [number, number][];
}

export function layout(procs: AgentProcess[], maxCols = Number.POSITIVE_INFINITY): Layout {
  const byPid = new Map(procs.map((p) => [p.pid, p]));
  const children = new Map<number, number[]>();
  const roots: number[] = [];
  for (const p of [...procs].sort((a, b) => a.pid - b.pid)) {
    if (p.ppid && byPid.has(p.ppid)) children.set(p.ppid, [...(children.get(p.ppid) ?? []), p.pid]);
    else roots.push(p.pid);
  }
  const positions: Layout["positions"] = {};
  const edges: Layout["edges"] = [];
  const cols = Math.max(1, maxCols);
  let slot = 0;
  let deepest = 0;

  const place = (pid: number, depth: number): number => {
    const kids = children.get(pid) ?? [];
    let x: number;
    if (!kids.length) {
      x = slot * (NODE_W + GAP_X);
      slot += 1;
    } else if (kids.length > cols && kids.every((k) => !(children.get(k) ?? []).length)) {
      const first = slot;
      kids.forEach((k, i) => {
        edges.push([pid, k]);
        const row = Math.floor(i / cols);
        positions[k] = { x: (first + (i % cols)) * (NODE_W + GAP_X), y: (depth + 1 + row) * (NODE_H + GAP_Y) };
        deepest = Math.max(deepest, depth + 1 + row);
      });
      slot += cols;
      x = first * (NODE_W + GAP_X) + ((cols - 1) * (NODE_W + GAP_X)) / 2;
    } else {
      const xs = kids.map((k) => {
        edges.push([pid, k]);
        return place(k, depth + 1);
      });
      x = (Math.min(...xs) + Math.max(...xs)) / 2;
    }
    positions[pid] = { x, y: depth * (NODE_H + GAP_Y) };
    deepest = Math.max(deepest, depth);
    return x;
  };
  roots.forEach((r) => place(r, 0));
  return { positions, edges };
}

/** How many nodes fit across a pane of `width` px at zoom 1 (at least 2, so a wrapped row still reads as siblings). */
export const columnsFor = (width: number) => Math.max(2, Math.floor((width - 16) / (NODE_W + GAP_X)));
