"use client";

import { Maximize2, Minimize2, Minus, X } from "lucide-react";
import { useRef } from "react";
import type { Area, Win } from "@/lib/desktop/windows";
import { cn } from "@/lib/utils";
import { APP_TINT, AppTile } from "./app-icons";

interface Props {
  win: Win;
  title: string;
  subtitle?: string;
  focused: boolean;
  compact: boolean;
  area: Area;
  onFocus: () => void;
  onClose: () => void;
  onMinimize: () => void;
  onToggleMax: () => void;
  onMove: (x: number, y: number) => void;
  onResize: (w: number, h: number) => void;
  children: React.ReactNode;
}

/** A window: a thin accent line in the app's colour when it is in front, its name and path, and plain controls on the
 *  right. Drag the title bar (double-click to zoom); the body is its own size container. */
export function WindowFrame({ win, title, subtitle, focused, compact, onFocus, onClose, onMinimize, onToggleMax, onMove, onResize, children }: Props) {
  const drag = useRef<{ dx: number; dy: number } | null>(null);
  const size = useRef<{ x: number; y: number; w: number; h: number } | null>(null);
  const full = compact || win.maximized;
  const btn = "flex h-6 w-7 items-center justify-center rounded-md text-text-2 transition-colors hover:bg-surface-3 hover:text-foreground";

  return (
    <section
      aria-label={title}
      data-window={win.key}
      onPointerDownCapture={onFocus}
      className={cn(
        "window-in absolute flex flex-col overflow-hidden border bg-surface-1",
        full ? "inset-0 rounded-none border-0" : "rounded-[14px]",
        focused ? "border-line shadow-window" : "border-hairline shadow-window-idle",
        win.docked && !full && "dock-left-in",
        win.minimized && "hidden",
      )}
      style={full ? { zIndex: win.z } : { left: win.x, top: win.y, width: win.w, height: win.h, zIndex: win.z }}
    >
      <span aria-hidden className="absolute inset-x-0 top-0 h-[3px] transition-opacity duration-150" style={{ background: APP_TINT[win.app], opacity: focused ? 1 : 0 }} />
      <header
        className="flex h-10 shrink-0 select-none items-center gap-2.5 border-b border-hairline px-3 pt-[3px]"
        onDoubleClick={() => !compact && onToggleMax()}
        onPointerDown={(e) => {
          if (full || e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
          drag.current = { dx: e.clientX - win.x, dy: e.clientY - win.y };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => drag.current && onMove(e.clientX - drag.current.dx, e.clientY - drag.current.dy)}
        onPointerUp={() => (drag.current = null)}
      >
        <AppTile app={win.app} size={20} />
        <h2 className={cn("min-w-0 truncate text-[13px] font-semibold", focused ? "text-foreground" : "text-text-2")}>{title}</h2>
        {subtitle && <span className="hidden min-w-0 truncate font-mono text-[11px] text-text-2 sm:inline">{subtitle}</span>}
        <div className="ml-auto flex items-center gap-0.5" onPointerDown={(e) => e.stopPropagation()}>
          {!compact && (
            <>
              <button type="button" onClick={onMinimize} aria-label={`Minimise ${title}`} className={btn}>
                <Minus className="size-3.5" />
              </button>
              <button type="button" onClick={onToggleMax} aria-label={win.maximized ? `Restore ${title}` : `Maximise ${title}`} className={btn}>
                {win.maximized ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
              </button>
            </>
          )}
          <button type="button" onClick={onClose} aria-label={`Close ${title}`} className={cn(btn, "hover:bg-[#ef4444] hover:text-white")}>
            <X className="size-3.5" />
          </button>
        </div>
      </header>
      <div className="@container min-h-0 flex-1 overflow-auto p-4">{children}</div>
      {!full && (
        <div
          aria-hidden
          className="absolute right-0 bottom-0 size-4 cursor-nwse-resize"
          onPointerDown={(e) => {
            size.current = { x: e.clientX, y: e.clientY, w: win.w, h: win.h };
            e.currentTarget.setPointerCapture(e.pointerId);
          }}
          onPointerMove={(e) => size.current && onResize(size.current.w + e.clientX - size.current.x, size.current.h + e.clientY - size.current.y)}
          onPointerUp={() => (size.current = null)}
        />
      )}
    </section>
  );
}
