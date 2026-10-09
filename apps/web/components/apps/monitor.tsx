"use client";

import type { Event, SandboxInfo } from "@kairos/contracts";
import { useQuery } from "@tanstack/react-query";
import { Box, Camera, CircleCheck, CircleX, Cpu, Gauge, Globe, HardDrive, Lock, MemoryStick, MonitorCog, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useClient } from "@/app/providers";
import { ArtifactImage, isImage } from "@/components/artifacts";
import { useModels, useResources } from "@/components/desktop/hooks";
import { formatTime } from "@/components/status";
import { str } from "@/lib/events";
import { cn } from "@/lib/utils";

function Gauge2({ label, icon: Icon, pct, value, detail }: { label: string; icon: typeof Cpu; pct: number | null; value: string; detail: string }) {
  const p = pct === null ? 0 : Math.max(0, Math.min(100, pct));
  return (
    <div className="rounded-xl border border-line bg-surface-1 p-4 shadow-panel">
      <p className="flex items-center gap-2 text-sm text-text-2">
        <Icon className="size-4" aria-hidden /> {label}
      </p>
      <p className="mt-1 font-mono text-3xl font-bold">{value}</p>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-3" role="meter" aria-label={label} aria-valuenow={Math.round(p)} aria-valuemin={0} aria-valuemax={100}>
        <div className={cn("h-full rounded-full transition-[width] duration-[350ms]", p > 90 ? "bg-st-failed" : p > 75 ? "bg-st-waiting" : "bg-brand")} style={{ width: `${p}%` }} />
      </div>
      <p className="mt-1.5 truncate font-mono text-xs text-text-2" title={detail}>{detail}</p>
    </div>
  );
}

function Section({ title, icon: Icon, children, className }: { title: string; icon: typeof Cpu; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-xl border border-line bg-surface-1 p-4 shadow-panel", className)}>
      <h2 className="mb-3 flex items-center gap-2 text-[17px] font-semibold">
        <Icon className="size-4.5 text-text-2" aria-hidden /> {title}
      </h2>
      {children}
    </section>
  );
}

function SandboxCard({ s }: { s: SandboxInfo }) {
  const sp = s.spec;
  const live = s.status === "running" || s.status === "provisioning";
  const readOnly = (sp.mounts ?? []).every((m) => (m as { read_only?: boolean }).read_only !== false);
  return (
    <li className="rounded-lg border border-line bg-surface-2 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn("rounded-md px-1.5 py-0.5 font-mono text-xs font-semibold", live ? "bg-st-running/12 text-st-running" : "bg-surface-3 text-text-2")}>{s.status}</span>
        <span className="font-mono text-sm">{s.sandbox_id}</span>
        <span className="text-sm text-text-2">{sp.display ? "browser" : (sp.image ?? "container")}</span>
        <Link href={`/tasks/${sp.task_id}`} className="ml-auto font-mono text-xs text-brand hover:underline">
          {sp.task_id}
        </Link>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-xs">
        <span className={cn("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5", sp.network === "none" ? "border-st-running/50 text-st-running" : "border-st-waiting/50 text-st-waiting")}>
          <Globe className="size-3" aria-hidden /> {sp.network === "none" ? "no network" : `allowlist: ${(sp.network_allow ?? []).join(", ") || "—"}`}
        </span>
        <span className="rounded-md border border-line px-1.5 py-0.5 text-text-2">{sp.cpu ?? 1} CPU · {sp.memory_mb ?? 0} MB{sp.gpu ? " · GPU" : ""}</span>
        {!!sp.mounts?.length && (
          <span className="inline-flex items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-text-2">
            <Lock className="size-3" aria-hidden /> {sp.mounts.length} mount{sp.mounts.length === 1 ? "" : "s"}{readOnly ? ", read-only" : ""}
          </span>
        )}
        {sp.timeout_s && <span className="rounded-md border border-line px-1.5 py-0.5 text-text-2">timeout {sp.timeout_s}s</span>}
        {sp.pid && <span className="rounded-md border border-line px-1.5 py-0.5 text-text-2">PID {sp.pid}</span>}
      </div>
    </li>
  );
}

/** The latest sandbox.screenshot events from the live stream (any task). */
function useScreenshots() {
  const client = useClient();
  const [shots, setShots] = useState<Event[]>([]);
  useEffect(
    () => client.events((e) => setShots((s) => [e, ...s.filter((x) => x.event_id !== e.event_id)].slice(0, 4)), { types: ["sandbox.screenshot"] }),
    [client],
  );
  return shots;
}

/** Before any live screenshot arrives: the screenshots of the most recent task that has some. */
function useLastTaskScreenshots() {
  const client = useClient();
  return useQuery({
    queryKey: ["last-task-screenshots"],
    queryFn: async () => {
      const tasks = (await client.listTasks()).sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? "")).slice(0, 5);
      for (const t of tasks) {
        const refs = (await client.taskArtifacts(t.task_id)).filter(isImage);
        if (refs.length) return { taskId: t.task_id, refs };
      }
      return null;
    },
  });
}

export function MonitorApp() {
  const client = useClient();
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => client.status(), refetchInterval: 10_000 });
  const res = useResources();
  const models = useModels();
  const sandboxes = useQuery({ queryKey: ["sandboxes"], queryFn: () => client.sandboxes(), refetchInterval: 3_000 });
  const shots = useScreenshots();
  const last = useLastTaskScreenshots();
  const r = res.data;
  const gpu = r?.gpu;
  const st = status.data;
  const up = st ? (st.uptime_s < 3600 ? `${Math.round(st.uptime_s / 60)} min` : `${(st.uptime_s / 3600).toFixed(1)} h`) : "";

  return (
    <div className="mx-auto max-w-[1600px] space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <MonitorCog className="size-6 text-brand" aria-hidden /> System
        </h1>
        {st && (
          <span className={cn("rounded-md px-2 py-0.5 font-mono text-xs font-bold", st.ready ? "bg-st-running/12 text-st-running" : "bg-st-failed/12 text-st-failed")}>
            {st.ready ? "READY" : "NOT READY"}
          </span>
        )}
        {st && (
          <span className="font-mono text-sm text-text-2">
            v{st.version} · contract {st.contract_version} · up {up}
          </span>
        )}
        {status.isError && (
          <span className="ml-auto flex items-center gap-2 text-sm text-st-failed">
            Gateway unreachable
            <button type="button" onClick={() => status.refetch()} className="rounded-md border border-line px-2 py-1 text-xs text-foreground hover:bg-surface-3">
              Retry
            </button>
          </span>
        )}
      </div>

      <div className="grid gap-4 @xl:grid-cols-2 @7xl:grid-cols-4">
        <Gauge2 label="CPU" icon={Cpu} pct={r ? r.cpu_percent : null} value={r ? `${r.cpu_percent.toFixed(0)}%` : "…"} detail="all cores" />
        <Gauge2
          label="RAM"
          icon={MemoryStick}
          pct={r ? (100 * r.ram_used_mb) / Math.max(r.ram_total_mb, 1) : null}
          value={r ? `${(r.ram_used_mb / 1024).toFixed(1)} GB` : "…"}
          detail={r ? `of ${(r.ram_total_mb / 1024).toFixed(1)} GB` : ""}
        />
        <Gauge2 label="GPU" icon={Gauge} pct={gpu ? gpu.utilization : null} value={gpu ? `${gpu.utilization.toFixed(0)}%` : "n/a"} detail={gpu?.name ?? "no GPU reported"} />
        <Gauge2
          label="VRAM"
          icon={HardDrive}
          pct={gpu ? (100 * gpu.memory_used_mb) / Math.max(gpu.memory_total_mb, 1) : null}
          value={gpu ? `${(gpu.memory_used_mb / 1024).toFixed(1)} GB` : "n/a"}
          detail={gpu ? `of ${(gpu.memory_total_mb / 1024).toFixed(1)} GB` : ""}
        />
      </div>

      <div className="grid gap-4 @7xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Section title="Kernel" icon={Cpu}>
            <dl className="grid grid-cols-2 gap-2 @xl:grid-cols-4">
              {(
                [
                  ["processes", r?.running_processes],
                  ["queued tasks", r?.queued_tasks],
                  ["sandboxes", r?.active_sandboxes],
                  ["tokens / min", r?.tokens_last_minute],
                ] as const
              ).map(([k, v]) => (
                <div key={k} className="rounded-lg border border-line bg-surface-2 px-3 py-2">
                  <dd className="font-mono text-2xl font-bold">{v ?? "–"}</dd>
                  <dt className="text-xs text-text-2">{k}</dt>
                </div>
              ))}
            </dl>
          </Section>

          <Section title={`Components (${st?.components.filter((c) => c.ok).length ?? 0}/${st?.components.length ?? 0} healthy)`} icon={CircleCheck}>
            <ul className="grid grid-cols-2 gap-1.5 @xl:grid-cols-3">
              {st?.components.map((c) => (
                <li key={c.component} className="flex items-center gap-2 rounded-md border border-line bg-surface-2 px-2.5 py-1.5 text-sm" title={c.detail || undefined}>
                  {c.ok ? <CircleCheck className="size-4 shrink-0 text-st-running" aria-label="ok" /> : <CircleX className="size-4 shrink-0 text-st-failed" aria-label="down" />}
                  <span className="truncate">{c.component}</span>
                  <span className={cn("ml-auto rounded px-1.5 font-mono text-xs font-bold", c.mode === "real" ? "bg-st-running/12 text-st-running" : "bg-st-waiting/12 text-st-waiting")}>{c.mode}</span>
                </li>
              ))}
            </ul>
          </Section>

          <Section title="Models" icon={Sparkles}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th className="pb-2 font-semibold">Model</th>
                    <th className="pb-2 font-semibold">Runs</th>
                    <th className="pb-2 font-semibold">Context</th>
                    <th className="pb-2 font-semibold">Capabilities</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {(models.data ?? []).map((m) => (
                    <tr key={m.name} className={cn(m.available === false && "opacity-50")}>
                      <td className="py-2 font-mono">{m.name}</td>
                      <td className="py-2">
                        <span className={cn("rounded-md px-1.5 font-mono text-xs font-semibold", m.local !== false ? "bg-st-running/12 text-st-running" : "bg-st-waiting/12 text-st-waiting")}>
                          {m.local !== false ? "local" : "remote"}
                        </span>{" "}
                        <span className="text-xs text-text-2">{m.provider}</span>
                      </td>
                      <td className="py-2 font-mono text-xs text-text-2">{m.embedding_dim ? `${m.embedding_dim}-d embeddings` : m.context_window ? `${m.context_window.toLocaleString()} tokens` : "—"}</td>
                      <td className="py-2 font-mono text-xs text-text-2">{(m.capabilities ?? []).join(" · ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        </div>

        <div className="space-y-4">
          <Section title={`Sandboxes (${(sandboxes.data ?? []).length})`} icon={Box}>
            <ul className="space-y-2">
              {(sandboxes.data ?? []).length === 0 && <li className="text-sm text-text-2">No sandboxes yet. They start when an agent browses or runs code.</li>}
              {[...(sandboxes.data ?? [])].reverse().slice(0, 6).map((s) => (
                <SandboxCard key={s.sandbox_id} s={s} />
              ))}
            </ul>
          </Section>

          <Section title="Latest sandbox screenshots" icon={Camera}>
            {shots.length === 0 && last.data ? (
              <div className="space-y-1.5">
                <p className="flex font-mono text-xs text-text-2">
                  from the last run
                  <Link href={`/tasks/${last.data.taskId}`} className="ml-auto text-brand hover:underline">{last.data.taskId}</Link>
                </p>
                {last.data.refs.slice(0, 2).map((ref) => <ArtifactImage key={ref} artifact={ref} className="[&_img]:max-h-[420px] [&_img]:object-contain [&_img]:object-top" />)}
              </div>
            ) : shots.length === 0 ? (
              <p className="text-sm text-text-2">Screenshots appear here live when an agent browses inside a sandbox.</p>
            ) : (
              <ul className="space-y-3">
                {shots.map((e) => (
                  <li key={e.event_id} className="space-y-1">
                    <p className="flex gap-3 font-mono text-xs text-text-2">
                      <span>{formatTime(e.ts)}</span>
                      <span>PID {e.pid}</span>
                      <Link href={`/tasks/${e.task_id}`} className="ml-auto text-brand hover:underline">{e.task_id}</Link>
                    </p>
                    {str(e, "artifact") && <ArtifactImage artifact={str(e, "artifact")!} className="[&_img]:max-h-[420px] [&_img]:object-contain [&_img]:object-top" />}
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}
