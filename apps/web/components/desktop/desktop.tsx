"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { memo, Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from "react";
import { useClient } from "@/app/providers";
import { ApprovalsApp } from "@/components/apps/approvals";
import { ConnectionsApp } from "@/components/apps/connections";
import { FilesApp } from "@/components/apps/files";
import { IngestApp } from "@/components/apps/ingest";
import { JournalApp } from "@/components/apps/journal";
import { JournalsApp } from "@/components/apps/journals";
import { MemoryApp } from "@/components/apps/memory";
import { MonitorApp } from "@/components/apps/monitor";
import { OrganizationApp } from "@/components/apps/organization";
import { ProgramsApp } from "@/components/apps/programs";
import { SettingsApp } from "@/components/apps/settings";
import { TaskApp } from "@/components/apps/task";
import { TasksApp } from "@/components/apps/tasks";
import { TerminalApp } from "@/components/apps/terminal";
import type { Box } from "@/lib/desktop/kairos";
import { APPS, type AppId, parseRoute } from "@/lib/desktop/routes";
import { type Area, COMPACT_WIDTH, EMPTY, focused as topWindow, reduce, type Win } from "@/lib/desktop/windows";
import { Boot } from "./boot";
import { Dock } from "./dock";
import { Notifications } from "./notifications";
import { RunStage } from "./run-stage";
import { DOCK_APPS, ShortcutSheet, Switcher } from "./shortcuts";
import { Spotlight } from "./spotlight";
import { type MenuActions, TopBar } from "./top-bar";
import { Hero, Widgets } from "./widgets";
import { Wallpaper } from "./wallpaper";
import { WindowContext } from "./window-context";
import { WindowFrame } from "./window-frame";

function AppBody({ win }: { win: Win }) {
  const r = parseRoute(win.url);
  switch (win.app) {
    case "tasks":
      return <TasksApp />;
    case "task":
      return <TaskApp id={r?.id ?? ""} />;
    case "approvals":
      return <ApprovalsApp />;
    case "files":
      return <FilesApp />;
    case "memory":
      return <MemoryApp />;
    case "journals":
      return <JournalsApp />;
    case "journal":
      return <JournalApp taskId={r?.id ?? ""} />;
    case "programs":
      return <ProgramsApp />;
    case "monitor":
      return <MonitorApp />;
    case "terminal":
      return <TerminalApp />;
    case "organization":
      return <OrganizationApp />;
    case "connections":
      return <ConnectionsApp />;
    case "ingest":
      return <IngestApp />;
    case "settings":
      return <SettingsApp />;
  }
}

/** A window's title-bar text: the app, plus what it is showing. */
function useWindowTitle(win: Win): { title: string; subtitle?: string } {
  const client = useClient();
  const r = parseRoute(win.url);
  const task = useQuery({ queryKey: ["task", r?.id], queryFn: () => client.getTask(r!.id!), enabled: !!r?.id && (win.app === "task" || win.app === "journal") });
  if (win.app === "task") return { title: task.data?.goal ? truncate(task.data.goal, 70) : "Task", subtitle: r?.id };
  if (win.app === "journal") return { title: "Audit", subtitle: r?.id };
  if (win.app === "files") return { title: "Knowledge", subtitle: new URLSearchParams(win.url.split("?")[1] ?? "").get("path") ?? "/org" };
  return { title: APPS[win.app].title };
}

const truncate = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

const WindowView = memo(function WindowView(props: {
  win: Win;
  focused: boolean;
  compact: boolean;
  area: Area;
  dispatch: React.Dispatch<Parameters<typeof reduce>[1]>;
  onNavigate: (url: string) => void;
  onClose: (key: string) => void;
}) {
  const { win, focused, compact, area, dispatch, onNavigate, onClose } = props;
  const { title, subtitle } = useWindowTitle(win);
  const close = useCallback(() => onClose(win.key), [onClose, win.key]);
  const nav = useMemo(() => ({ key: win.key, url: win.url, navigate: onNavigate, close }), [win.key, win.url, onNavigate, close]);
  // The app's element only changes with its URL, so dragging or resizing the window never re-renders the app inside.
  const body = useMemo(
    () => (
      <WindowContext.Provider value={nav}>
        <AppBody win={win} />
      </WindowContext.Provider>
    ),
    // win is read for its app and url only
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [nav, win.app, win.url],
  );
  return (
    <WindowFrame
      win={win}
      title={title}
      subtitle={subtitle}
      focused={focused}
      compact={compact}
      area={area}
      onFocus={() => dispatch({ type: "focus", key: win.key })}
      onClose={close}
      onMinimize={() => dispatch({ type: "minimize", key: win.key })}
      onToggleMax={() => dispatch({ type: "toggleMax", key: win.key })}
      onMove={(x, y) => dispatch({ type: "move", key: win.key, x, y, area })}
      onResize={(w, h) => dispatch({ type: "resize", key: win.key, w, h, area })}
    >
      {body}
    </WindowFrame>
  );
});

/** The part of the wallpaper the centred greeting and Ask bar cover (fractions of the screen), kept free of documents. */
const HERO_BOX: Box = [0.26, 0.17, 0.74, 0.5];

function DesktopInner() {
  const pathname = usePathname();
  const search = useSearchParams();
  const router = useRouter();
  const url = `${pathname}${search.size ? `?${search}` : ""}`;
  const [state, dispatch] = useReducer(reduce, EMPTY);
  const areaRef = useRef<HTMLDivElement>(null);
  const [area, setArea] = useState<Area>({ w: 1440, h: 800 });
  const [spotlight, setSpotlight] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [switcher, setSwitcher] = useState<number | null>(null);
  const compact = area.w < COMPACT_WIDTH;
  const top = topWindow(state);
  // Keep the kairos's documents out from under the Ask bar and the widget column.
  const avoid = useMemo<Box[]>(() => (area.w >= 1100 ? [HERO_BOX, [1 - 340 / area.w, 0, 1, 1]] : [HERO_BOX]), [area.w]);
  // Windows for the Alt+` switcher, front first.
  const stack = useMemo(() => [...state.wins].sort((a, b) => Number(a.minimized) - Number(b.minimized) || b.z - a.z), [state.wins]);

  useLayoutEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    const measure = () => setArea({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // The address bar drives the windows: a link, a deep link or Back opens or focuses the window for that URL...
  useEffect(() => {
    if (pathname === "/") dispatch({ type: "minimizeAll" });
    else dispatch({ type: "open", url, area });
    // area only sizes new windows; a resize must not reopen them
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  // ...and the window in front drives the address bar, so a reload or a shared link comes back to it. Only after the
  // front window actually changes: on load the address bar is the truth, and writing "/" before its window has opened
  // would read as "show the desktop" and minimise it.
  const lastTop = useRef<string | null>(null);
  useEffect(() => {
    const sig = top ? `${top.key}|${top.url}` : "";
    if (lastTop.current === null || sig === lastTop.current) {
      lastTop.current = sig;
      return;
    }
    lastTop.current = sig;
    const want = top?.url ?? "/";
    if (want !== url) window.history.replaceState(null, "", want);
    // only when the front window (or its URL) changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [top?.key, top?.url]);

  const openApp = useCallback(
    (app: AppId) => {
      const family: AppId[] = app === "tasks" ? ["tasks", "task"] : app === "journals" ? ["journals", "journal"] : [app];
      const mine = state.wins.filter((w) => family.includes(w.app)).sort((a, b) => b.z - a.z);
      if (!mine.length) return router.push(APPS[app].home);
      dispatch({ type: "focus", key: mine[0].key });
    },
    [state.wins, router],
  );

  // Keyboard: Alt is the modifier (the browser and the OS keep most Ctrl/Cmd combinations). Alt+` switches windows
  // while Alt is held, like Cmd+Tab.
  const switchRef = useRef<number | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && k === "k") {
        e.preventDefault();
        setSpotlight(true);
        return;
      }
      if (!e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.code === "Space") {
        e.preventDefault();
        setSpotlight((o) => !o);
      } else if (e.code === "Backquote") {
        e.preventDefault();
        if (!stack.length) return;
        const cur = switchRef.current;
        const next = cur === null ? (stack.length > 1 ? 1 : 0) : (cur + (e.shiftKey ? stack.length - 1 : 1)) % stack.length;
        switchRef.current = next;
        setSwitcher(next);
      } else if (/^Digit[1-9]$/.test(e.code)) {
        e.preventDefault();
        const app = DOCK_APPS[Number(e.code.slice(5)) - 1];
        if (app) openApp(app);
      } else if (k === "w" && top) {
        e.preventDefault();
        dispatch({ type: "close", key: top.key });
      } else if (k === "m" && top) {
        e.preventDefault();
        dispatch({ type: "minimize", key: top.key });
      } else if (e.key === "Enter" && top) {
        e.preventDefault();
        dispatch({ type: "toggleMax", key: top.key });
      } else if (k === "d") {
        e.preventDefault();
        router.push("/");
      } else if (k === "t") {
        e.preventDefault();
        router.push("/terminal");
      } else if (e.code === "Comma") {
        e.preventDefault();
        openApp("settings");
      } else if (e.code === "Slash") {
        e.preventDefault();
        setSheet((o) => !o);
      }
    };
    const onUp = (e: KeyboardEvent) => {
      if (e.key === "Alt" && switchRef.current !== null) {
        const chosen = stack[switchRef.current];
        switchRef.current = null;
        setSwitcher(null);
        if (chosen) dispatch({ type: "focus", key: chosen.key });
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("keyup", onUp);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("keyup", onUp);
    };
  }, [router, stack, top, openApp]);

  const navigate = useCallback((to: string) => router.push(to), [router]);
  const close = useCallback((key: string) => dispatch({ type: "close", key }), []);

  const onDock = (app: AppId) => {
    const family: AppId[] = app === "tasks" ? ["tasks", "task"] : app === "journals" ? ["journals", "journal"] : [app];
    if (top && family.includes(top.app)) return dispatch({ type: "minimize", key: top.key });
    openApp(app);
  };

  const actions: MenuActions = {
    spotlight: () => setSpotlight(true),
    close: () => top && dispatch({ type: "close", key: top.key }),
    minimize: () => top && dispatch({ type: "minimize", key: top.key }),
    zoom: () => top && dispatch({ type: "toggleMax", key: top.key }),
    desktop: () => router.push("/"),
    shortcuts: () => setSheet(true),
    openApp,
    focusWindow: (key) => dispatch({ type: "focus", key }),
    boot: () => router.push("/boot"),
  };

  if (pathname === "/boot") return <Boot />;

  const focusedTask = top?.app === "task" ? parseRoute(top.url)?.id : undefined;
  // A live task docked left gets the rest of the desktop as its stage.
  const docked = !compact ? state.wins.find((w) => w.app === "task" && w.docked && !w.minimized && !w.maximized) : undefined;
  const dockedTask = docked ? parseRoute(docked.url)?.id : undefined;
  const nothingOpen = !state.wins.some((w) => !w.minimized);

  return (
    <div className="desktop fixed inset-0 flex flex-col overflow-hidden bg-grout text-foreground">
      <Wallpaper avoid={avoid} />
      <TopBar front={top} wins={state.wins} actions={actions} compact={compact} />
      <main ref={areaRef} className={`relative min-h-0 flex-1 ${compact ? "" : "mb-[90px]"}`} aria-label="Desktop">
        <div className={`absolute inset-0 flex overflow-y-auto ${compact ? "flex-col items-center gap-6 px-4 pt-8 pb-6" : "items-start justify-center px-6 pt-[20vh]"} ${docked ? "invisible" : ""}`}>
          <Hero onAsk={() => setSpotlight(true)} compact={compact} />
          {!compact && (
            <div className="absolute top-4 right-5 hidden min-[1100px]:block">
              <Widgets />
            </div>
          )}
          {compact && nothingOpen && <Widgets />}
        </div>
        {docked && dockedTask && (
          <div className="@container absolute top-3 right-4 bottom-3 overflow-y-auto pr-1" style={{ left: docked.w + 16, zIndex: Math.max(1, docked.z - 1) }} aria-label="Live run">
            <RunStage taskId={dockedTask} onZoom={() => dispatch({ type: "toggleMax", key: docked.key })} />
          </div>
        )}
        {state.wins.map((w) => (
          <WindowView key={w.key} win={w} focused={w.key === top?.key} compact={compact} area={area} dispatch={dispatch} onNavigate={navigate} onClose={close} />
        ))}
        <Notifications focusedTask={focusedTask} />
      </main>
      <div className={compact ? "relative" : "pointer-events-none absolute inset-x-0 bottom-2 z-[5000] flex justify-center"}>
        <div className={compact ? "" : "pointer-events-auto"}>
          <Dock wins={state.wins} focusedKey={top?.key} compact={compact} onApp={(app) => onDock(app)} onDesktop={() => router.push("/")} onAsk={() => setSpotlight(true)} />
        </div>
      </div>
      <Spotlight open={spotlight} onClose={() => setSpotlight(false)} />
      {switcher !== null && <Switcher wins={stack} index={switcher} />}
      {sheet && <ShortcutSheet onClose={() => setSheet(false)} />}
    </div>
  );
}

/** The console as an operating system: wallpaper, menu bar, windows, dock. Routes only say which window to show. */
export function Desktop() {
  return (
    <Suspense>
      <DesktopInner />
    </Suspense>
  );
}
