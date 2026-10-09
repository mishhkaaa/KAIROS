"use client";

import { type OrbState, type OrbTheme, ThinkingOrb } from "thinking-orbs";
import { cn } from "@/lib/utils";

/** A thinking orb in the console's ink: it follows the theme on <html data-theme>. */
export function Orb({ state = "working", size = 20, theme = "auto", className, label }: { state?: OrbState; size?: 20 | 32 | 64; theme?: OrbTheme; className?: string; label?: string }) {
  return <ThinkingOrb state={state} size={size} theme={theme} className={cn("shrink-0", className)} aria-label={label ?? state} />;
}

/** The loading state of a window or panel: an orb and what is being fetched. */
export function Loading({ label, state = "searching", className }: { label: string; state?: OrbState; className?: string }) {
  return (
    <div role="status" className={cn("flex flex-col items-center justify-center gap-3 py-12 text-sm text-text-2", className)}>
      <Orb state={state} size={64} label={label} />
      <span>{label}</span>
    </div>
  );
}
