"use client";

import { BellRing, Brain, Building2, Cable, Cpu, FolderTree, Gauge, ListChecks, type LucideIcon, ScrollText, Settings2, SquareTerminal, Upload, Workflow } from "lucide-react";
import type { AppId } from "@/lib/desktop/routes";
import { cn } from "@/lib/utils";

export const APP_ICON: Record<AppId, LucideIcon> = {
  tasks: ListChecks,
  task: Workflow,
  approvals: BellRing,
  files: FolderTree,
  memory: Brain,
  journals: ScrollText,
  journal: ScrollText,
  programs: Cpu,
  monitor: Gauge,
  terminal: SquareTerminal,
  organization: Building2,
  connections: Cable,
  ingest: Upload,
  settings: Settings2,
};

/** Each app's colour: one vivid hue, used for its tile, its window's accent line and its rail indicator. */
export const APP_TINT: Record<AppId, string> = {
  tasks: "#0d9488",
  task: "#0d9488",
  approvals: "#f59e0b",
  files: "#3b82f6",
  memory: "#8b5cf6",
  journals: "#64748b",
  journal: "#64748b",
  programs: "#22a35a",
  monitor: "#ef4444",
  terminal: "#111827",
  organization: "#0ea5e9",
  connections: "#ec4899",
  ingest: "#f97316",
  settings: "#6366f1",
};

/** An app's icon: its glyph on a flat tile in the app's colour, with a one-pixel top light. Cheap to paint. */
export function AppTile({ app, size = 40, className }: { app: AppId; size?: number; className?: string }) {
  const Icon = APP_ICON[app];
  return (
    <span
      className={cn("relative inline-flex shrink-0 items-center justify-center text-white", className)}
      style={{ width: size, height: size, borderRadius: size * 0.28, background: APP_TINT[app], boxShadow: "inset 0 1px 0 rgb(255 255 255 / 0.3)" }}
      aria-hidden
    >
      {app === "terminal" ? (
        <span className="font-mono font-bold text-[#34d399]" style={{ fontSize: size * 0.34 }}>
          &gt;_
        </span>
      ) : (
        <Icon style={{ width: size * 0.5, height: size * 0.5 }} strokeWidth={2.1} />
      )}
    </span>
  );
}
