/** The desktop's window manager as a pure reducer (unit-tested): open, focus, move, resize, minimise, maximise, close. */

import { APPS, type AppId, parseRoute } from "./routes";

export interface Win {
  key: string;
  app: AppId;
  url: string;
  x: number;
  y: number;
  w: number;
  h: number;
  z: number;
  minimized: boolean;
  maximized: boolean;
  /** Docked to the left edge (a live task); moving, resizing or zooming undocks it. */
  docked: boolean;
}

export interface Area {
  w: number;
  h: number;
}

export interface WinState {
  wins: Win[];
  /** The next stacking order. */
  top: number;
}

export const EMPTY: WinState = { wins: [], top: 1 };

/** Below this width every window is a full-screen sheet (phones). */
export const COMPACT_WIDTH = 900;
const MIN_W = 360;
const MIN_H = 240;
const CASCADE = 28;

export type WinAction =
  | { type: "open"; url: string; area: Area }
  | { type: "focus"; key: string }
  | { type: "close"; key: string }
  | { type: "minimize"; key: string }
  | { type: "toggleMax"; key: string }
  | { type: "move"; key: string; x: number; y: number; area: Area }
  | { type: "resize"; key: string; w: number; h: number; area: Area }
  | { type: "minimizeAll" };

/** The window on top: the highest stacking order among those not minimised. */
export function focused(s: WinState): Win | undefined {
  return s.wins.filter((w) => !w.minimized).reduce<Win | undefined>((a, b) => (!a || b.z > a.z ? b : a), undefined);
}

function clampPos(x: number, y: number, w: number, area: Area) {
  // Keep at least a grab-able strip of the title bar on screen.
  return { x: Math.round(Math.min(Math.max(x, 80 - w), area.w - 80)), y: Math.round(Math.min(Math.max(y, 0), area.h - 34)) };
}

/** Width of a window docked left: room for the run's story, the rest of the desktop for its stage. */
export function dockWidth(area: Area): number {
  return Math.round(Math.min(700, Math.max(440, area.w * 0.36)));
}

function place(app: AppId, area: Area, open: number) {
  if (APPS[app].dockLeft) return { x: 0, y: 0, w: dockWidth(area), h: area.h };
  const [fw, fh] = APPS[app].size;
  const w = Math.max(MIN_W, Math.min(area.w, Math.round(area.w * fw)));
  const h = Math.max(MIN_H, Math.min(area.h, Math.round(area.h * fh)));
  const step = (open % 6) * CASCADE;
  return { x: Math.max(0, Math.round((area.w - w) / 2) + step - CASCADE), y: Math.max(0, Math.round((area.h - h) / 3) + step), w, h };
}

export function reduce(s: WinState, a: WinAction): WinState {
  const map = (key: string, f: (w: Win) => Win) => s.wins.map((w) => (w.key === key ? f(w) : w));
  switch (a.type) {
    case "open": {
      const r = parseRoute(a.url);
      if (!r) return s;
      const existing = s.wins.find((w) => w.key === r.key);
      if (existing) {
        if (existing.url === r.url && !existing.minimized && existing === focused(s)) return s;
        return { top: s.top + 1, wins: map(r.key, (w) => ({ ...w, url: r.url, minimized: false, z: s.top })) };
      }
      const g = place(r.app, a.area, s.wins.filter((w) => !w.minimized).length);
      const compact = a.area.w < COMPACT_WIDTH;
      const maximized = !!APPS[r.app].maximized || compact;
      const docked = !!APPS[r.app].dockLeft && !compact;
      const win: Win = { key: r.key, app: r.app, url: r.url, ...g, z: s.top, minimized: false, maximized, docked };
      return { top: s.top + 1, wins: [...s.wins, win] };
    }
    case "focus": {
      const w = s.wins.find((x) => x.key === a.key);
      if (!w || (w === focused(s) && !w.minimized)) return s;
      return { top: s.top + 1, wins: map(a.key, (x) => ({ ...x, minimized: false, z: s.top })) };
    }
    case "close":
      return { ...s, wins: s.wins.filter((w) => w.key !== a.key) };
    case "minimize":
      return { ...s, wins: map(a.key, (w) => ({ ...w, minimized: true })) };
    case "minimizeAll":
      return { ...s, wins: s.wins.map((w) => ({ ...w, minimized: true })) };
    case "toggleMax":
      return { top: s.top + 1, wins: map(a.key, (w) => ({ ...w, maximized: !w.maximized, docked: false, minimized: false, z: s.top })) };
    case "move":
      return { ...s, wins: map(a.key, (w) => ({ ...w, ...clampPos(a.x, a.y, w.w, a.area), maximized: false, docked: false })) };
    case "resize":
      return {
        ...s,
        wins: map(a.key, (w) => ({
          ...w,
          w: Math.round(Math.max(MIN_W, Math.min(a.w, a.area.w - Math.max(0, w.x)))),
          h: Math.round(Math.max(MIN_H, Math.min(a.h, a.area.h - Math.max(0, w.y)))),
          maximized: false,
          docked: false,
        })),
      };
  }
}
