"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpenText, RefreshCw, Search, X } from "lucide-react";
import { Orb } from "@/components/desktop/orb";
import { useState } from "react";
import { useWindowNav, useWindowParams } from "@/components/desktop/window-context";
import { toast } from "sonner";
import { useClient } from "@/app/providers";
import { ObjectView } from "@/components/knowledge/object-view";
import { SearchResults } from "@/components/knowledge/search-results";
import { KnowledgeTree } from "@/components/knowledge/tree";
import { KairosError } from "@/lib/kairos-client";

export function FilesApp() {
  const client = useClient();
  const qc = useQueryClient();
  const params = useWindowParams();
  const win = useWindowNav();
  const path = params.get("path");
  const query = params.get("q");
  const [draft, setDraft] = useState(query ?? "");
  const validate = useQuery({ queryKey: ["knowledge-validate"], queryFn: () => client.validate(), staleTime: 5 * 60_000 });
  const reindex = useMutation({
    mutationFn: () => client.reindex(),
    onSuccess: (r) => {
      toast.success("Reindexed", { description: `${Object.values(r).reduce((a, b) => a + b, 0)} objects` });
      qc.invalidateQueries({ queryKey: ["knowledge-validate"] });
    },
    onError: (e) => toast.error("Reindex failed", { description: e instanceof KairosError ? e.message : String(e) }),
  });

  const go = (next: { path?: string | null; q?: string | null }) => {
    const s = new URLSearchParams();
    const p = next.path === undefined ? path : next.path;
    const q = next.q === undefined ? query : next.q;
    if (p) s.set("path", p);
    if (q) s.set("q", q);
    win.navigate(`/knowledge${s.size ? `?${s}` : ""}`);
  };

  return (
    <div className="flex flex-col gap-4 @5xl:h-full">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <BookOpenText className="size-6 text-brand" aria-hidden /> Knowledge
          </h1>
          <p className="mt-1 text-sm text-text-2">
            The organization&apos;s knowledge as a filesystem. Everything shown is filtered by your scope and clearance.
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm text-text-2">
          {validate.data && (
            <span className="font-mono">
              {validate.data.files_checked} documents · {validate.data.ok ? <span className="text-st-running">valid</span> : <span className="text-st-waiting">{validate.data.issues?.length} issues</span>}
            </span>
          )}
          <button
            type="button"
            onClick={() => reindex.mutate()}
            disabled={reindex.isPending}
            className="flex h-9 items-center gap-1.5 rounded-md border border-line px-3 text-sm transition-colors hover:bg-surface-3 disabled:opacity-60"
          >
            {reindex.isPending ? <Orb state="searching" label="Reindexing" /> : <RefreshCw className="size-4" aria-hidden />} Reindex
          </button>
        </div>
      </div>

      <div className="grid gap-4 @5xl:min-h-0 @5xl:flex-1 @5xl:grid-cols-[280px_minmax(0,1fr)] @[96rem]:grid-cols-[280px_minmax(0,1fr)_440px]">
        <aside className="min-h-0 overflow-y-auto rounded-xl border border-line bg-surface-1 p-2 shadow-panel">
          <KnowledgeTree selected={path} onSelect={(p) => go({ path: p })} />
        </aside>

        <section className="min-h-0 overflow-y-auto pr-1">
          {path ? (
            <ObjectView key={path} path={path} onSelect={(p) => go({ path: p })} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center px-6 py-16 text-center text-text-2">
              <BookOpenText className="mb-3 size-10 opacity-25" aria-hidden />
              <p className="text-lg font-medium text-foreground">Pick a document or search.</p>
              <p className="mt-1 text-sm">Select a file from the tree on the left, or enter a search query.</p>
              <p className="mt-1 text-sm">Search blends lexical, semantic and graph scores and shows all three.</p>
            </div>
          )}
        </section>

        <aside className="flex min-h-0 flex-col gap-3 @[96rem]:col-start-3 @max-[96rem]:@5xl:col-span-2 @max-5xl:order-first">
          <form
            role="search"
            className="relative"
            onSubmit={(e) => {
              e.preventDefault();
              go({ q: draft.trim() || null });
            }}
          >
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Hybrid search over /org"
              aria-label="Search knowledge"
              className="h-10 w-full rounded-md border border-line bg-surface-2 pl-8 pr-9 text-sm"
            />
            {query && (
              <button
                type="button"
                onClick={() => {
                  setDraft("");
                  go({ q: null });
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-text-2 hover:text-foreground"
                aria-label="Clear search"
              >
                <X className="size-4" />
              </button>
            )}
          </form>
          {query ? (
            <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              <SearchResults key={query} text={query} onSelect={(p) => go({ path: p })} />
            </div>
          ) : (
            <p className="px-1 text-sm text-text-2">Results show provenance, trust, the three scores, and what policy hid.</p>
          )}
        </aside>
      </div>
    </div>
  );
}

