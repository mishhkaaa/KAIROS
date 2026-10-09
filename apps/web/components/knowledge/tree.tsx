"use client";

import type { KnowledgeEntry } from "@kairos/contracts";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, FileText, Folder, FolderOpen, Lock } from "lucide-react";
import { useState } from "react";
import { useClient } from "@/app/providers";
import { cn } from "@/lib/utils";

function Node({ entry, depth, selected, onSelect }: { entry: KnowledgeEntry; depth: number; selected: string | null; onSelect: (p: string) => void }) {
  const [open, setOpen] = useState(() => !!selected?.startsWith(entry.path + "/"));
  const name = entry.path.split("/").pop();
  const isSel = selected === entry.path;
  const sensitive = entry.privacy === "confidential" || entry.privacy === "restricted";
  return (
    <li>
      <div
        className={cn(
          "flex cursor-pointer items-center gap-1.5 rounded-md px-1.5 py-1.5 text-sm hover:bg-surface-3",
          isSel && "bg-surface-3 font-medium text-brand",
        )}
        style={{ paddingLeft: 6 + depth * 14 }}
        onClick={() => {
          if (entry.is_dir) setOpen((o) => !o);
          onSelect(entry.path);
        }}
      >
        {entry.is_dir ? (
          <>
            <ChevronRight className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} />
            {open ? <FolderOpen className="size-4 shrink-0 text-ev-tool" /> : <Folder className="size-4 shrink-0 text-ev-tool" />}
          </>
        ) : (
          <FileText className="ml-5 size-4 shrink-0 text-muted-foreground" />
        )}
        <span className="truncate" title={entry.path}>{entry.title || name}</span>
        {sensitive && <Lock className="ml-auto size-3.5 shrink-0 text-risk-high" aria-label={entry.privacy} />}
      </div>
      {entry.is_dir && open && <Listing path={entry.path} depth={depth + 1} selected={selected} onSelect={onSelect} />}
    </li>
  );
}

function Listing({ path, depth, selected, onSelect }: { path: string; depth: number; selected: string | null; onSelect: (p: string) => void }) {
  const client = useClient();
  const q = useQuery({ queryKey: ["knowledge-tree", path], queryFn: () => client.tree(path) });
  if (q.isLoading) return <p className="px-2 py-1 text-xs text-muted-foreground" style={{ paddingLeft: 6 + depth * 14 }}>…</p>;
  if (q.isError) return <p className="px-2 py-1 text-xs text-st-failed">{String(q.error)}</p>;
  const entries = [...(q.data?.entries ?? [])].sort((a, b) => Number(!!b.is_dir) - Number(!!a.is_dir) || a.path.localeCompare(b.path));
  return (
    <ul>
      {entries.map((e) => (
        <Node key={e.path} entry={e} depth={depth} selected={selected} onSelect={onSelect} />
      ))}
    </ul>
  );
}

export function KnowledgeTree({ selected, onSelect }: { selected: string | null; onSelect: (p: string) => void }) {
  return (
    <div>
      <div
        className={cn("cursor-pointer rounded-md px-1.5 py-1.5 font-mono text-sm hover:bg-surface-3", selected === "/org" && "bg-surface-3 text-brand")}
        onClick={() => onSelect("/org")}
      >
        /org
      </div>
      <Listing path="/org" depth={0} selected={selected} onSelect={onSelect} />
    </div>
  );
}
