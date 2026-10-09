"use client";

import { LayoutGrid } from "lucide-react";
import { APPS, type AppId } from "@/lib/desktop/routes";
import type { Win } from "@/lib/desktop/windows";
import { isActive } from "@/lib/events";
import { cn } from "@/lib/utils";
import { APP_TINT, AppTile } from "./app-icons";
import { usePendingApprovals, useTasks } from "./hooks";
import { Orb } from "./orb";
import { DOCK_APPS } from "./shortcuts";

/** Windows that belong to a rail app (a task window counts as Tasks, a journal as Audit). */
const FAMILY: Partial<Record<AppId, AppId[]>> = { tasks: ["tasks", "task"], journals: ["journals", "journal"] };

/** The command rail, centred under the desktop: ask KAIROS, the desktop, then the apps (Settings last). Every item is the
 *  same size, so the rail is symmetric. Hover lifts an icon with a compositor-only transform; nothing is measured or
 *  re-rendered as the pointer moves. */
export function Dock({ wins, focusedKey, compact, onApp, onDesktop, onAsk }: { wins: Win[]; focusedKey?: string; compact: boolean; onApp: (app: AppId, home: string) => void; onDesktop: () => void; onAsk: () => void }) {
  const pending = usePendingApprovals().data?.length ?? 0;
  const running = (useTasks().data ?? []).some((t) => isActive(t.status));
  const items = compact ? (["tasks", "approvals", "files", "terminal"] as AppId[]) : DOCK_APPS;

  if (compact) {
    return (
      <nav aria-label="Apps" className="chrome flex w-full justify-around border-x-0 border-b-0 px-2 pt-1.5 pb-[max(6px,env(safe-area-inset-bottom))]">
        <button type="button" onClick={onAsk} aria-label="Ask KAIROS" className="flex flex-col items-center gap-0.5 text-[11px] text-text-2">
          <span className="flex size-9 items-center justify-center rounded-[10px] bg-brand text-white">
            <Orb state="breathing" theme="dark" label="Ask" />
          </span>
          Ask
        </button>
        {items.map((app) => {
          const family = FAMILY[app] ?? [app];
          const active = wins.some((w) => w.key === focusedKey && family.includes(w.app));
          return (
            <button key={app} type="button" onClick={() => onApp(app, APPS[app].home)} aria-label={APPS[app].title} aria-current={active ? "true" : undefined} className={cn("relative flex flex-col items-center gap-0.5 text-[11px]", active ? "text-foreground" : "text-text-2")}>
              <AppTile app={app} size={36} />
              {app === "approvals" && pending > 0 && <span className="absolute -top-1 right-0 min-w-4 rounded-full bg-[#ef4444] px-1 text-center text-[10px] font-bold leading-4 text-white">{pending}</span>}
              {APPS[app].title}
            </button>
          );
        })}
      </nav>
    );
  }

  return (
    <nav aria-label="Command rail" className="chrome flex items-center gap-2 rounded-[20px] p-2 shadow-window">
      <button type="button" onClick={onAsk} aria-label="Ask KAIROS (Alt Space)" className="rail-item group relative flex flex-col items-center">
        <span className="rail-icon flex size-11 items-center justify-center rounded-[12px] bg-gradient-to-br from-[#0d9488] to-[#2563eb] shadow-[inset_0_1px_0_rgb(255_255_255/0.3)]">
          <Orb state="breathing" size={32} theme="dark" label="Ask KAIROS" />
        </span>
        <Tip label="Ask KAIROS · Alt Space" />
      </button>
      <button type="button" onClick={onDesktop} aria-label="Desktop" aria-current={!focusedKey ? "true" : undefined} className="rail-item group relative flex flex-col items-center">
        <span className="rail-icon flex size-11 items-center justify-center rounded-[12px] bg-surface-2 text-foreground">
          <LayoutGrid className="size-5" />
        </span>
        <Tip label="Desktop" />
      </button>
      {items.map((app) => {
        const family = FAMILY[app] ?? [app];
        const open = wins.some((w) => family.includes(w.app));
        const divider = app === "ingest" ? <span key="sep" className="mx-0.5 h-8 w-px bg-hairline" aria-hidden /> : null;
        const active = wins.some((w) => w.key === focusedKey && family.includes(w.app));
        return [
          divider,
          <button key={app} type="button" onClick={() => onApp(app, APPS[app].home)} aria-label={APPS[app].title} aria-current={active ? "true" : undefined} className="rail-item group relative flex flex-col items-center">
            <span className={cn("rail-icon relative", app === "approvals" && pending > 0 && "dock-bounce")}>
              <AppTile app={app} size={44} />
              {app === "approvals" && pending > 0 && (
                <span className="absolute -top-1.5 -right-1.5 min-w-5 rounded-full bg-[#ef4444] px-1.5 text-center text-xs font-bold leading-5 text-white ring-2 ring-surface-1">{pending}</span>
              )}
              {app === "tasks" && running && (
                <span className="absolute -top-2 -right-2 rounded-full bg-surface-1 p-0.5 ring-1 ring-hairline">
                  <Orb state="working" label="a task is running" />
                </span>
              )}
            </span>
            <span className="absolute -bottom-1.5 h-[3px] rounded-full transition-all duration-200" style={{ width: active ? 18 : open ? 5 : 0, background: active ? APP_TINT[app] : "var(--text-2)" }} aria-hidden />
            <Tip label={APPS[app].title} />
          </button>,
        ];
      })}
    </nav>
  );
}

function Tip({ label }: { label: string }) {
  return (
    <span className="panel pointer-events-none absolute -top-10 hidden whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium group-hover:block group-focus-visible:block">{label}</span>
  );
}
