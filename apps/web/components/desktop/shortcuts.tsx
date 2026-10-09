"use client";

import type { AppId } from "@/lib/desktop/routes";
import { APPS } from "@/lib/desktop/routes";
import type { Win } from "@/lib/desktop/windows";
import { cn } from "@/lib/utils";
import { AppTile } from "./app-icons";

/** The rail's apps, in order; Alt+1..9 opens the first nine. The work first, then the machine, then the org's setup. */
export const DOCK_APPS: AppId[] = ["tasks", "approvals", "files", "memory", "journals", "programs", "monitor", "terminal", "ingest", "connections", "organization", "settings"];

/** One place for every shortcut, so the menus, the cheat sheet and the handler agree. Alt, not Ctrl or Cmd: the browser
 *  and the OS keep most Ctrl/Cmd combinations for themselves. */
export const KEYS = {
  spotlight: "Alt Space",
  switch: "Alt `",
  close: "Alt W",
  minimize: "Alt M",
  zoom: "Alt Enter",
  desktop: "Alt D",
  terminal: "Alt T",
  settings: "Alt ,",
  shortcuts: "Alt /",
} as const;

export const SHEET: [string, string][] = [
  [KEYS.spotlight, "Ask KAIROS, open an app, a task or a document (also Ctrl K)"],
  [KEYS.switch, "Switch windows (hold Alt, tap ` to move, release to open)"],
  ["Alt 1 … 9", "Open a rail app"],
  [KEYS.terminal, "Terminal"],
  [KEYS.settings, "Settings"],
  [KEYS.close, "Close the front window"],
  [KEYS.minimize, "Minimise it"],
  [KEYS.zoom, "Zoom it (maximise or restore)"],
  [KEYS.desktop, "Show the desktop"],
  [KEYS.shortcuts, "This sheet"],
];

/** The Alt+` window switcher: every open window as an icon, the chosen one highlighted. */
export function Switcher({ wins, index }: { wins: Win[]; index: number }) {
  if (!wins.length) return null;
  return (
    <div className="pointer-events-none fixed inset-0 z-[8000] grid place-items-center">
      <div className="panel spotlight-in flex max-w-[90vw] gap-2 overflow-hidden rounded-[22px] p-3 shadow-window">
        {wins.map((w, i) => (
          <div key={w.key} className={cn("flex w-24 flex-col items-center gap-1.5 rounded-[14px] p-2", i === index && "bg-black/10 dark:bg-white/15")}>
            <AppTile app={w.app} size={64} />
            <span className="max-w-full truncate text-xs font-medium">{w.app === "task" ? w.key.slice(5) : APPS[w.app].title}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ShortcutSheet({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[8000] grid place-items-center bg-black/10" onClick={onClose}>
      <section aria-label="Keyboard shortcuts" className="panel spotlight-in w-[min(560px,92vw)] rounded-[18px] p-5 shadow-window" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold">Keyboard shortcuts</h2>
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-5 gap-y-2 text-sm">
          {SHEET.map(([k, v]) => (
            <div key={k} className="contents">
              <dt>
                <kbd className="rounded-md border border-hairline bg-surface-1 px-1.5 py-0.5 font-mono text-xs shadow-sm">{k}</kbd>
              </dt>
              <dd className="text-text-2">{v}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
