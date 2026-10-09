"use client";

import type { TaskCreate } from "@kairos/contracts";
import { useMutation } from "@tanstack/react-query";
import { CornerDownLeft, FileText } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { useClient } from "@/app/providers";
import { TaskStatusBadge } from "@/components/status";
import { APPS } from "@/lib/desktop/routes";
import { folderHue } from "@/lib/desktop/palette";
import { isActive } from "@/lib/events";
import { KairosError } from "@/lib/kairos-client";
import { useSession } from "@/components/session";
import { cn } from "@/lib/utils";
import { AppTile } from "./app-icons";
import { useAllDocs, useTasks } from "./hooks";
import { Orb } from "./orb";
import { TypingDots } from "./typing-dots";
import { DOCK_APPS } from "./shortcuts";

// The prompt from docs/DEMO_SCRIPT.md ("paste exactly").
export const DEMO_PROMPT =
  "Investigate why Project Apollo is over budget and six weeks behind schedule. Identify root causes, update the tracker, and prepare a recovery plan.";
// The second scenario from docs/DEMO_SCRIPT.md ("Project Zeus budget risk").
export const ZEUS_PROMPT =
  "Prepare a steering-committee briefing on Project Zeus budget risk for Q4: identify the risk drivers with evidence, update the tracker, and propose mitigations.";
const SUGGESTIONS: [string, string][] = [
  ["Apollo demo prompt", DEMO_PROMPT],
  ["Zeus demo prompt", ZEUS_PROMPT],
  ["Who is blocked on Apollo this week?", "Who is blocked on Project Apollo this week, and on what?"],
];
const CHIP_TEXT: Record<string, string> = { "Apollo demo prompt": "Investigate Project Apollo's overrun", "Zeus demo prompt": "Brief the steering committee on Zeus risk" };

type Priority = NonNullable<TaskCreate["priority"]>;
const PRIORITIES: Priority[] = ["high", "normal", "background"];
type Row = { id: string; label: string; detail?: string; icon: React.ReactNode; run: () => void };

/** Alt+Space: one floating field to ask KAIROS something (it becomes a task) or open an app, a task or a document. */
export function Spotlight({ open, onClose }: { open: boolean; onClose: () => void }) {
  const client = useClient();
  const router = useRouter();
  const docs = useAllDocs().data ?? [];
  const tasks = useTasks().data ?? [];
  const [q, setQ] = useState("");
  const [priority, setPriority] = useState<Priority>("high");
  const [sel, setSel] = useState(0);
  const [closing, setClosing] = useState(false);
  const field = useRef<HTMLTextAreaElement>(null);

  const close = () => {
    setClosing(true);
    setTimeout(() => {
      setClosing(false);
      onClose();
    }, 140);
  };
  const go = (url: string) => {
    router.push(url);
    close();
  };
  const { me, can } = useSession();
  const mayStart = can("task.create");
  const role = me?.role;
  const start = useMutation({
    mutationFn: (goal: string) => client.createTask({ goal, priority }),
    onSuccess: (t) => {
      setQ("");
      go(`/tasks/${t.task_id}`);
    },
    onError: (e) => toast.error("Couldn't start the task", { description: e instanceof KairosError ? e.message : String(e) }),
  });

  useEffect(() => {
    if (open) setTimeout(() => field.current?.focus(), 30);
  }, [open]);

  const rows = useMemo<Row[]>(() => {
    const needle = q.trim().toLowerCase();
    const out: Row[] = [];
    if (needle && mayStart) out.push({ id: "run", label: `Ask KAIROS: “${q.trim()}”`, detail: "runs as a new task", icon: <CornerDownLeft className="size-4 text-brand" />, run: () => start.mutate(q.trim()) });
    const has = (...s: (string | undefined)[]) => !!needle && s.some((x) => x?.toLowerCase().includes(needle));
    for (const a of DOCK_APPS) if (has(APPS[a].title, a)) out.push({ id: `app:${a}`, label: APPS[a].title, detail: "app", icon: <AppTile app={a} size={22} />, run: () => go(APPS[a].home) });
    for (const t of tasks.filter((t) => has(t.goal, t.task_id)).slice(0, 3))
      out.push({ id: `task:${t.task_id}`, label: t.goal, detail: t.task_id, icon: isActive(t.status) ? <Orb state="working" /> : <TaskStatusBadge status={t.status} />, run: () => go(`/tasks/${t.task_id}`) });
    for (const d of docs.filter((d) => has(d.title, d.path)).slice(0, 5))
      out.push({ id: `doc:${d.path}`, label: d.title ?? d.path, detail: d.path, icon: <FileText className="size-4" style={{ color: folderHue(d.path) }} />, run: () => go(`/knowledge?path=${encodeURIComponent(d.path)}`) });
    return out;
    // go and start are recreated each render; the rows only depend on what is typed and the data
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, docs, tasks, mayStart]);
  const active = Math.min(sel, Math.max(0, rows.length - 1));

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[7500]" onPointerDown={close}>
      <div className="absolute inset-0 bg-[rgb(15_23_42/0.08)]" aria-hidden />
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Ask KAIROS"
        onPointerDown={(e) => e.stopPropagation()}
        className={cn("panel absolute top-[16vh] left-1/2 w-[min(720px,calc(100vw-24px))] -translate-x-1/2 overflow-hidden rounded-[20px] shadow-window", closing ? "spotlight-out" : "spotlight-in")}
      >
        <div className="flex items-start gap-3 px-4 pt-4 pb-3">
          <span className="mt-0.5 flex flex-col items-center gap-1">
            <Orb state={start.isPending ? "shaping" : q ? "listening" : "breathing"} size={32} label="KAIROS" />
            {start.isPending && <TypingDots className="text-brand" label="Starting the task" />}
          </span>
          <textarea
            ref={field}
            rows={q.length > 70 ? 3 : 1}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setSel(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                close();
              } else if (e.key === "ArrowDown") {
                e.preventDefault();
                setSel((s) => Math.min(s + 1, rows.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setSel((s) => Math.max(s - 1, 0));
              } else if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                rows[active]?.run();
              }
            }}
            placeholder={mayStart ? "Ask KAIROS to investigate, find or fix something…" : "Search apps, tasks and documents…"}
            aria-label="Ask KAIROS"
            className="min-h-8 flex-1 resize-none bg-transparent pt-0.5 text-[21px] leading-snug outline-none placeholder:text-text-2/70"
          />
        </div>

        {!q && (
          <div className="flex flex-wrap gap-2 px-4 pb-3">
            {SUGGESTIONS.map(([label, text]) => (
              <button
                key={label}
                type="button"
                aria-label={label}
                onClick={() => {
                  setQ(text);
                  field.current?.focus();
                }}
                className="rounded-full border border-hairline bg-surface-1/70 px-3 py-1 text-sm transition-colors hover:bg-surface-1"
              >
                {CHIP_TEXT[label] ?? label}
              </button>
            ))}
          </div>
        )}

        {rows.length > 0 && (
          <ul role="listbox" aria-label="Results" className="max-h-[44vh] overflow-y-auto border-t border-hairline p-1.5">
            {rows.map((r, i) => (
              <li key={r.id} role="option" aria-selected={i === active}>
                <button
                  type="button"
                  onMouseEnter={() => setSel(i)}
                  onClick={r.run}
                  className={cn("flex w-full items-center gap-3 rounded-[10px] px-3 py-2 text-left", i === active && "bg-brand text-white")}
                >
                  <span className="flex w-6 justify-center">{r.icon}</span>
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{r.label}</span>
                  {r.detail && <span className={cn("max-w-[40%] truncate font-mono text-xs", i === active ? "text-white/80" : "text-text-2")}>{r.detail}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}

        <footer className="flex flex-wrap items-center gap-3 border-t border-hairline bg-surface-1/40 px-4 py-2.5 text-xs text-text-2">
          <div role="radiogroup" aria-label="Priority" className="flex overflow-hidden rounded-md border border-hairline">
            {PRIORITIES.map((p) => (
              <button
                key={p}
                type="button"
                role="radio"
                aria-checked={priority === p}
                onClick={() => setPriority(p)}
                className={cn("px-2.5 py-1 capitalize", priority === p ? "bg-surface-1 font-semibold text-foreground" : "hover:bg-surface-1/60")}
              >
                {p}
              </button>
            ))}
          </div>
          <span className="hidden font-mono sm:inline">{mayStart ? "↵ run" : "↵ open"} · ↑↓ choose · esc close</span>
          {!mayStart && <span className="ml-auto">Your role ({role ?? "none"}) can search but not start tasks.</span>}
          <button
            type="button"
            hidden={!mayStart}
            disabled={!q.trim() || start.isPending}
            onClick={() => start.mutate(q.trim())}
            className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-lg bg-brand px-4 text-sm font-semibold text-white shadow-sm transition-transform hover:bg-brand-hover active:scale-[0.97] disabled:opacity-40"
          >
            <CornerDownLeft className="size-4" /> Run
          </button>
        </footer>
      </section>
    </div>
  );
}
