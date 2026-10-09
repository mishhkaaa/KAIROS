"use client";

import type { KnowledgeMount, PrivacyLevel } from "@kairos/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CloudUpload, FileText, FolderSync, HardDrive, RefreshCw, Trash2, XCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useClient } from "@/app/providers";
import { Orb } from "@/components/desktop/orb";
import { useSession } from "@/components/session";
import { formatTime } from "@/components/status";
import type { IngestProgress } from "@/lib/kairos-client";
import { cn } from "@/lib/utils";
import { AppHeader, button, Card, errText, field, NotAllowed, Pill } from "./kit";

type Stage = "ready" | "sending" | IngestProgress["stage"];

interface Entry {
  file: File;
  stage: Stage;
  path?: string | null;
  error?: string | null;
}

const PRIVACY: { level: PrivacyLevel; note: string }[] = [
  { level: "public", note: "anyone, any model" },
  { level: "internal", note: "org members; local models" },
  { level: "confidential", note: "need-to-know agents; local models only" },
  { level: "restricted", note: "named people; never leaves this machine" },
];

const ACCEPT = ".md,.txt,.csv,.json,.pdf,.docx,.pptx,.xlsx,.log,.rst,.py,.ts,.tsx,.js,.sql,.sh,.yaml,.yml,.toml,.html,.css";

function StageMark({ e }: { e: Entry }) {
  if (e.stage === "ready") return <span className="font-mono text-xs text-text-2">ready</span>;
  if (e.stage === "sending" || e.stage === "received") return <span className="flex items-center gap-1.5 font-mono text-xs text-brand"><Orb state="working" label="converting" /> {e.stage === "sending" ? "sending" : "converting"}</span>;
  if (e.stage === "indexed")
    return (
      <Link href={`/knowledge?path=${encodeURIComponent(e.path ?? "/org/uploads")}`} className="flex items-center gap-1 font-mono text-xs text-st-completed hover:underline">
        <CheckCircle2 className="size-3.5" /> {e.path}
      </Link>
    );
  return (
    <span className={cn("flex items-center gap-1 font-mono text-xs", e.stage === "error" ? "text-st-failed" : "text-st-waiting")} title={e.error ?? undefined}>
      <XCircle className="size-3.5" /> {e.stage}{e.error ? `: ${e.error}` : ""}
    </span>
  );
}

function Upload() {
  const client = useClient();
  const qc = useQueryClient();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [folder, setFolder] = useState("/org/uploads");
  const [privacy, setPrivacy] = useState<PrivacyLevel>("internal");
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  // Each file's way through the gateway, live: received, then indexed (or skipped, or an error).
  useEffect(
    () =>
      client.events(
        (ev) => {
          const p = ev.payload as unknown as IngestProgress;
          setEntries((list) => list.map((e) => (e.file.name === p.file && e.stage !== "ready" ? { ...e, stage: p.stage, path: p.path ?? e.path, error: p.error } : e)));
        },
        { types: ["ingest.progress"] },
      ),
    [client],
  );

  const add = useCallback((files: File[]) => {
    setEntries((list) => [...list.filter((e) => e.stage !== "indexed"), ...files.filter((f) => !list.some((e) => e.file.name === f.name && e.stage === "ready")).map((file): Entry => ({ file, stage: "ready" }))]);
  }, []);

  const send = useMutation({
    mutationFn: async () => {
      const batch = entries.filter((e) => e.stage === "ready");
      setEntries((list) => list.map((e) => (e.stage === "ready" ? { ...e, stage: "sending" } : e)));
      return client.upload(batch.map((e) => e.file), folder, privacy);
    },
    onSuccess: (r) => {
      const made = [...(r.created ?? []), ...(r.updated ?? [])];
      // The events usually got here first; the response settles anything they missed.
      setEntries((list) =>
        list.map((e) => {
          if (e.stage !== "sending" && e.stage !== "received") return e;
          const skipped = r.skipped?.find((s) => s.startsWith(e.file.name));
          const err = r.errors?.find((s) => s.startsWith(e.file.name));
          return skipped ? { ...e, stage: "skipped", error: skipped.slice(e.file.name.length).replace(/^[\s(:]+|\)$/g, "") } : err ? { ...e, stage: "error", error: err } : { ...e, stage: "indexed" };
        }),
      );
      for (const key of ["knowledge-tree", "knowledge-all-docs", "knowledge-search"]) qc.invalidateQueries({ queryKey: [key] });
      toast.success(`${made.length} ${made.length === 1 ? "document" : "documents"} added to ${folder}`, { description: "Converted, indexed and searchable by agents now." });
    },
    onError: (e) => {
      setEntries((list) => list.map((x) => (x.stage === "sending" ? { ...x, stage: "error", error: errText(e) } : x)));
      toast.error("Upload failed", { description: errText(e) });
    },
  });
  const ready = entries.filter((e) => e.stage === "ready").length;

  return (
    <Card title="Upload files" icon={<CloudUpload className="size-4 text-text-2" />}>
      <div
        role="button"
        tabIndex={0}
        aria-label="Drop files here or choose files"
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          add(Array.from(e.dataTransfer.files));
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-4 py-8 text-center transition-colors",
          dragging ? "border-brand bg-brand-subtle/60" : "border-hairline bg-surface-2 hover:border-brand/50",
        )}
      >
        <span className="grid grid-cols-2 gap-1" aria-hidden>
          {["#2f7cf6", "#16b67a", "#ff8a3d", "#7b61ff"].map((c) => (
            <span key={c} className={cn("size-4 rounded-[4px] transition-transform", dragging && "scale-110")} style={{ background: c }} />
          ))}
        </span>
        <p className="text-sm font-medium">Drop documents here, or click to choose</p>
        <p className="text-xs text-text-2">Markdown, text, CSV, JSON, PDF, Word, PowerPoint, Excel, code. Up to 25 MB each.</p>
        <input ref={input} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => add(Array.from(e.target.files ?? []))} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-xs">
          <span className="text-text-2">Into</span>
          <input value={folder} onChange={(e) => setFolder(e.target.value)} className={cn(field, "h-8 w-44 font-mono text-xs")} aria-label="Target folder" />
        </label>
        <label className="flex items-center gap-2 text-xs">
          <span className="text-text-2">Privacy</span>
          <select value={privacy} onChange={(e) => setPrivacy(e.target.value as PrivacyLevel)} className={cn(field, "h-8 text-xs")} aria-label="Privacy">
            {PRIVACY.map((p) => (
              <option key={p.level} value={p.level}>{p.level}: {p.note}</option>
            ))}
          </select>
        </label>
        <button type="button" onClick={() => send.mutate()} disabled={!ready || send.isPending} className={cn(button.primary, "ml-auto h-8")}>
          {send.isPending ? <Orb state="working" label="uploading" /> : <CloudUpload className="size-4" />} Add {ready || ""} to /org
        </button>
      </div>

      {entries.length > 0 && (
        <ul className="mt-3 divide-y divide-hairline rounded-xl border border-hairline">
          {entries.map((e) => (
            <li key={e.file.name} className="flex items-center gap-3 px-3 py-2">
              <FileText className="size-4 shrink-0 text-text-2" />
              <span className="min-w-0 flex-1 truncate text-sm">{e.file.name}</span>
              <span className="shrink-0 font-mono text-xs text-text-2">{Math.max(1, Math.round(e.file.size / 1024))} KB</span>
              <span className="max-w-[45%] shrink-0 truncate"><StageMark e={e} /></span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function MountRow({ m }: { m: KnowledgeMount }) {
  const client = useClient();
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["mounts"] });
  const sync = useMutation({ mutationFn: () => client.syncMount(m.name), onSuccess: refresh, onError: (e) => toast.error("Sync failed", { description: errText(e) }) });
  const remove = useMutation({
    mutationFn: () => client.removeMount(m.name),
    onSuccess: () => {
      refresh();
      for (const key of ["knowledge-tree", "knowledge-all-docs"]) qc.invalidateQueries({ queryKey: [key] });
      toast.success(`${m.org_path} unmounted`, { description: "The folder on this computer is untouched." });
    },
    onError: (e) => toast.error("Not removed", { description: errText(e) }),
  });
  return (
    <li className="flex flex-wrap items-center gap-3 px-3 py-2.5">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-[#f97316]/12 text-[#ea580c]">
        <HardDrive className="size-4.5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
          <Link href={`/knowledge?path=${encodeURIComponent(m.org_path)}`} className="font-mono text-brand hover:underline">{m.org_path}</Link>
          {m.watching ? (
            <Pill tone="ok">
              <span className="size-1.5 rounded-full bg-current" /> watching
            </Pill>
          ) : (
            <Pill>not watching</Pill>
          )}
        </p>
        <p className="truncate font-mono text-xs text-text-2" title={m.host_path}>{m.host_path}</p>
        <p className="text-xs text-text-2">
          {m.files ?? 0} files mirrored{m.skipped ? `, ${m.skipped} could not be read` : ""}
          {m.synced_at ? ` · synced ${formatTime(m.synced_at)}` : ""}
        </p>
        {!!m.errors?.length && <p className="truncate text-xs text-st-failed" title={m.errors.join("\n")}>{m.errors[0]}</p>}
      </div>
      <button type="button" onClick={() => sync.mutate()} disabled={sync.isPending} className={cn(button.quiet, "h-8")} aria-label={`Sync ${m.name}`}>
        <RefreshCw className={cn("size-3.5", sync.isPending && "animate-spin")} /> Sync
      </button>
      <button type="button" onClick={() => remove.mutate()} disabled={remove.isPending} aria-label={`Unmount ${m.name}`} className="rounded-lg p-2 text-text-2 hover:bg-st-failed/10 hover:text-st-failed">
        <Trash2 className="size-4" />
      </button>
    </li>
  );
}

function Mounts() {
  const client = useClient();
  const qc = useQueryClient();
  const mounts = useQuery({ queryKey: ["mounts"], queryFn: () => client.mounts(), refetchInterval: 15_000 });
  const [name, setName] = useState("");
  const [host, setHost] = useState("");
  // A mount re-syncs by itself when a watched file changes; keep the list current.
  useEffect(() => client.events(() => qc.invalidateQueries({ queryKey: ["mounts"] }), { types: ["mount.synced"] }), [client, qc]);
  const add = useMutation({
    mutationFn: () => client.addMount({ name: name.trim(), host_path: host.trim() }),
    onSuccess: (m) => {
      setName("");
      setHost("");
      qc.invalidateQueries({ queryKey: ["mounts"] });
      for (const key of ["knowledge-tree", "knowledge-all-docs"]) qc.invalidateQueries({ queryKey: [key] });
      toast.success(`Mounted at ${m.org_path}`, { description: `${m.files ?? 0} files mirrored; changes on disk flow in by themselves.` });
    },
    onError: (e) => toast.error("Not mounted", { description: errText(e) }),
  });
  const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "");

  return (
    <Card title="Folders on this computer" icon={<FolderSync className="size-4 text-text-2" />} aside={<span className="font-mono text-[11px] text-text-2">/org/mnt</span>}>
      <p className="mb-3 text-sm text-text-2">
        Mount a folder and KAIROS keeps it in /org: every document is converted and indexed, edits are picked up as you save, and deleted files leave. The mirror is read-only: agents never write to your disk.
      </p>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (name && host) add.mutate();
        }}
      >
        <input
          value={host}
          onChange={(e) => {
            setHost(e.target.value);
            if (!name) setName(slug(e.target.value.split(/[\\/]/).filter(Boolean).pop() ?? ""));
          }}
          placeholder="C:\Users\you\Documents\team-notes"
          aria-label="Folder path on this computer"
          className={cn(field, "min-w-64 flex-[2] font-mono text-xs")}
        />
        <input value={name} onChange={(e) => setName(slug(e.target.value))} placeholder="name" aria-label="Mount name" className={cn(field, "w-36 flex-1 font-mono text-xs")} />
        <button type="submit" disabled={!name || !host || add.isPending} className={button.primary}>
          {add.isPending ? <Orb state="working" label="mounting" /> : <FolderSync className="size-4" />} Mount
        </button>
      </form>
      {mounts.data && mounts.data.length > 0 ? (
        <ul className="mt-3 divide-y divide-hairline rounded-xl border border-hairline">
          {mounts.data.map((m) => (
            <MountRow key={m.name} m={m} />
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-xs text-text-2">{mounts.isPending ? "Loading mounts…" : "No folders mounted yet."}</p>
      )}
    </Card>
  );
}

/** Bring knowledge in from outside /org: files from the browser, folders from this computer, and (in Connections)
 *  GitHub and Calendar. Everything lands as OKF documents, indexed for search. */
export function IngestApp() {
  const { me, can } = useSession();
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <AppHeader app="ingest" title="Add knowledge" sub="Files, folders of this computer and connected services, into /org">
        <Link href="/connections" className={button.quiet}>From GitHub or Calendar</Link>
      </AppHeader>
      {can("knowledge.ingest") ? (
        <>
          <Upload />
          <Mounts />
        </>
      ) : (
        <NotAllowed role={me?.role} permission="knowledge.ingest" what="add knowledge" />
      )}
    </div>
  );
}
