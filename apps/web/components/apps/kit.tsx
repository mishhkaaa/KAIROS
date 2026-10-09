"use client";

import { Lock } from "lucide-react";
import { AppTile } from "@/components/desktop/app-icons";
import type { AppId } from "@/lib/desktop/routes";
import { KairosError } from "@/lib/kairos-client";
import { cn } from "@/lib/utils";

/** The message of a gateway error, without its code prefix. */
export const errText = (e: unknown) => (e instanceof KairosError ? e.message.replace(/^[A-Z_]+: /, "") : e instanceof Error ? e.message : String(e));

/** An app's header: its tile, a title and one line under it, and actions on the right. */
export function AppHeader({ app, title, sub, children }: { app: AppId; title: React.ReactNode; sub?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <header className="flex flex-wrap items-center gap-3">
      <AppTile app={app} size={40} />
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-xl font-semibold tracking-tight">{title}</h1>
        {sub && <p className="truncate text-sm text-text-2">{sub}</p>}
      </div>
      {children}
    </header>
  );
}

export function Card({ title, icon, aside, className, children }: { title?: React.ReactNode; icon?: React.ReactNode; aside?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return (
    <section className={cn("rounded-2xl border border-hairline bg-surface-1 p-4 shadow-panel", className)}>
      {(title || aside) && (
        <div className="mb-3 flex items-center gap-2">
          {icon}
          {title && <h2 className="text-[15px] font-semibold">{title}</h2>}
          {aside && <div className="ml-auto flex items-center gap-2">{aside}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Pill({ tone = "neutral", mono, children, title }: { tone?: "neutral" | "ok" | "warn" | "bad" | "brand"; mono?: boolean; children: React.ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11.5px] font-medium",
        mono && "font-mono",
        tone === "neutral" && "bg-surface-3 text-text-2",
        tone === "ok" && "bg-st-completed/12 text-st-completed",
        tone === "warn" && "bg-st-waiting/14 text-st-waiting",
        tone === "bad" && "bg-st-failed/12 text-st-failed",
        tone === "brand" && "bg-brand-subtle text-brand",
      )}
    >
      {children}
    </span>
  );
}

/** Shown in place of controls the caller's role does not allow. */
export function NotAllowed({ role, permission, what }: { role?: string | null; permission: string; what: string }) {
  return (
    <p className="flex items-center gap-2 rounded-xl border border-dashed border-hairline bg-surface-2 px-3 py-2 text-sm text-text-2">
      <Lock className="size-3.5 shrink-0" />
      <span>
        Your role ({role ?? "none"}) cannot {what}. It needs <span className="font-mono">{permission}</span>.
      </span>
    </p>
  );
}

export const button = {
  primary: "inline-flex h-9 items-center justify-center gap-1.5 rounded-xl bg-brand px-3.5 text-sm font-medium text-white hover:bg-brand-hover disabled:opacity-50",
  quiet: "inline-flex h-9 items-center justify-center gap-1.5 rounded-xl border border-hairline bg-surface-1 px-3 text-sm hover:bg-surface-3 disabled:opacity-50",
  danger: "inline-flex h-9 items-center justify-center gap-1.5 rounded-xl border border-st-failed/30 px-3 text-sm text-st-failed hover:bg-st-failed/10 disabled:opacity-50",
};

export const field = "h-9 min-w-0 rounded-xl border border-hairline bg-surface-2 px-3 text-sm outline-none focus:border-brand";
