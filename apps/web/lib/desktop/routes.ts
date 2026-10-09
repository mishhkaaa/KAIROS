/** Which desktop app a console URL opens, and the key of the window that shows it. Pure, so it is unit-tested. */

export type AppId =
  | "tasks"
  | "task"
  | "approvals"
  | "files"
  | "memory"
  | "journals"
  | "journal"
  | "programs"
  | "monitor"
  | "terminal"
  | "organization"
  | "connections"
  | "ingest"
  | "settings";

export interface AppRoute {
  app: AppId;
  /** The window that shows this URL: one per app, except one per task for a task or its journal. */
  key: string;
  /** Task id for `task` and `journal`. */
  id?: string;
  /** The URL the window shows (path and query). */
  url: string;
}

const STATIC: Record<string, AppId> = {
  "/tasks": "tasks",
  "/approvals": "approvals",
  "/knowledge": "files",
  "/memory": "memory",
  "/audit": "journals",
  "/agents": "programs",
  "/system": "monitor",
  "/terminal": "terminal",
  "/organization": "organization",
  "/connections": "connections",
  "/ingest": "ingest",
  "/settings": "settings",
};

/** Parse a console URL. `/`, `/boot` and unknown paths open no window (null). */
export function parseRoute(url: string): AppRoute | null {
  const [rawPath, query = ""] = url.split("?", 2);
  const path = rawPath.length > 1 ? rawPath.replace(/\/+$/, "") : rawPath;
  const full = query ? `${path}?${query}` : path;
  const app = STATIC[path];
  if (app) return { app, key: app, url: full };
  const m = /^\/(tasks|audit)\/([^/]+)$/.exec(path);
  if (m) {
    const id = decodeURIComponent(m[2]);
    const which: AppId = m[1] === "tasks" ? "task" : "journal";
    return { app: which, key: `${which}:${id}`, id, url: full };
  }
  return null;
}

export interface AppMeta {
  title: string;
  /** Default window size as a fraction of the desktop area. */
  size: [number, number];
  /** Opens maximised. */
  maximized?: boolean;
  /** Opens docked to the left edge, full height: the live run's story, with the run stage beside it. */
  dockLeft?: boolean;
  /** The URL the dock opens. */
  home: string;
}

export const APPS: Record<AppId, AppMeta> = {
  tasks: { title: "Tasks", size: [0.6, 0.72], home: "/tasks" },
  task: { title: "Task", size: [0.9, 0.9], dockLeft: true, home: "/tasks" },
  approvals: { title: "Approvals", size: [0.5, 0.78], home: "/approvals" },
  files: { title: "Knowledge", size: [0.82, 0.84], home: "/knowledge" },
  memory: { title: "Memory", size: [0.74, 0.84], home: "/memory" },
  journals: { title: "Audit", size: [0.6, 0.72], home: "/audit" },
  journal: { title: "Audit", size: [0.82, 0.88], home: "/audit" },
  programs: { title: "Agents", size: [0.72, 0.8], home: "/agents" },
  monitor: { title: "System", size: [0.74, 0.84], home: "/system" },
  terminal: { title: "Terminal", size: [0.5, 0.56], home: "/terminal" },
  organization: { title: "Organization", size: [0.68, 0.8], home: "/organization" },
  connections: { title: "Connections", size: [0.62, 0.78], home: "/connections" },
  ingest: { title: "Add knowledge", size: [0.62, 0.8], home: "/ingest" },
  settings: { title: "Settings", size: [0.8, 0.86], home: "/settings" },
};
