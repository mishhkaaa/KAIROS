"use client";

import { useQuery } from "@tanstack/react-query";
import { EyeOff, ShieldAlert, ShieldCheck } from "lucide-react";
import { useClient } from "@/app/providers";
import { UntrustedBadge } from "@/components/status";
import { cn } from "@/lib/utils";
import { TrustChip } from "./chips";

const MODES: [string, string][] = [
  ["lexical", "bg-ev-tool"],
  ["semantic", "bg-brand"],
  ["graph", "bg-ev-knowledge"],
];

/** Returns "classifier" if the LLM classifier fired, "regex" if only the regex layer fired, null if no instruction-like
 *  text was found (an untrusted source alone is not a detection). */
function firewallDetection(flags: string[] | null | undefined): "classifier" | "regex" | null {
  if (!flags?.includes("instruction_like")) return null;
  return flags.includes("instruction_like_llm") ? "classifier" : "regex";
}

export function SearchResults({ text, onSelect }: { text: string; onSelect: (p: string) => void }) {
  const client = useClient();
  const q = useQuery({ queryKey: ["knowledge-search", text], queryFn: () => client.search(text, 10) });
  if (q.isLoading) return <p className="text-sm text-text-2">Searching…</p>;
  if (q.isError) return <p className="text-sm text-st-failed">{String(q.error)}</p>;
  const ev = q.data!;
  return (
    <div className="space-y-3">
      <p className="flex flex-wrap items-center gap-x-3 text-sm text-text-2">
        <span>{ev.hits.length} hits</span>
        <span>· {ev.total_candidates ?? 0} candidates</span>
        {!!ev.filtered_by_policy && (
          <span className="flex items-center gap-1 text-st-waiting">
            · <EyeOff className="size-3.5" /> {ev.filtered_by_policy} hidden by policy
          </span>
        )}
        {ev.took_ms !== undefined && <span>· {Math.round(ev.took_ms)} ms</span>}
      </p>
      {ev.hits.map((h, i) => {
        const detection = firewallDetection(h.firewall_flags);
        const flagged = detection !== null;
        const untrusted = flagged || !!h.firewall_flags?.includes("untrusted_source");
        return (
          <button
            key={h.path}
            type="button"
            onClick={() => onSelect(h.path)}
            className={cn(
              "block w-full rounded-xl border border-line bg-surface-1 p-4 text-left shadow-panel transition-colors hover:border-brand/60",
              flagged && "border-untrusted/60 bg-untrusted-bg/30",
            )}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-text-2">#{i + 1}</span>
              <span className="font-semibold">{h.title}</span>
              {untrusted && <UntrustedBadge />}
              {flagged && (
                <span className="inline-flex items-center gap-1 rounded border border-untrusted/40 px-1.5 py-0.5 font-mono text-xs text-untrusted">
                  {detection === "classifier" ? (
                    <><ShieldAlert className="size-3" aria-hidden /> caught by LLM classifier</>
                  ) : (
                    <><ShieldAlert className="size-3" aria-hidden /> caught by regex</>
                  )}
                </span>
              )}
              <span className="ml-auto font-mono text-xs text-text-2">score {h.score.toFixed(4)}</span>
            </div>
            <p className="font-mono text-xs text-ev-knowledge">{h.path} <span className="text-text-2">· {h.type}</span></p>
            <p className="mt-1.5 line-clamp-2 text-sm text-text-2">{h.snippet}</p>
            {flagged && (
              <div className="mt-2 flex items-center gap-1.5 rounded-md border border-st-running/40 bg-st-running/8 px-2 py-1">
                <ShieldCheck className="size-3.5 shrink-0 text-st-running" aria-hidden />
                <span className="text-xs font-medium text-st-running">treated as data, not instructions</span>
              </div>
            )}
            <div className="mt-2 grid grid-cols-[1fr_auto] items-end gap-3">
              <div className="space-y-1">
                {MODES.map(([mode, color]) => {
                  const v = h.scores?.[mode];
                  return (
                    <div key={mode} className="flex items-center gap-2 text-xs">
                      <span className="w-16 font-mono text-text-2">{mode}</span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-3">
                        <div className={cn("h-full rounded-full transition-[width] duration-300", color)} style={{ width: `${Math.round((v ?? 0) * 100)}%` }} />
                      </div>
                      <span className="w-10 text-right font-mono text-text-2">{v === undefined ? "–" : v.toFixed(2)}</span>
                    </div>
                  );
                })}
              </div>
              <div className="flex flex-col items-end gap-1 text-xs text-text-2">
                <TrustChip value={h.provenance.trust} />
                <span className="font-mono">
                  {h.provenance.source}
                  {h.provenance.source_version ? ` @ ${h.provenance.source_version}` : ""}
                </span>
                {h.provenance.updated_at && <span className="font-mono">{h.provenance.updated_at.slice(0, 10)}</span>}
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
