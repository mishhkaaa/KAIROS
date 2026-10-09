"use client";

import type { ComponentHealth } from "@kairos/contracts";
import { useQuery } from "@tanstack/react-query";
import { Check, CircleAlert } from "lucide-react";
import { Orb } from "./orb";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { useClient } from "@/app/providers";
import { cn } from "@/lib/utils";
import { BigOrb } from "./big-orb";
import { Mark, Wordmark } from "./logo";

const GIVE_UP_MS = 60_000;

// What an operator recognises, in boot order, and the /system/status components each line waits for.
const STEPS: { label: string; components: string[] }[] = [
  { label: "Kernel", components: ["kernel", "event_bus"] },
  { label: "Policy engine", components: ["policy"] },
  { label: "Audit log", components: ["audit"] },
  { label: "Knowledge filesystem", components: ["knowledge", "firewall", "converters"] },
  { label: "Memory", components: ["memory"] },
  { label: "Models", components: ["models", "probe"] },
  { label: "Agents", components: ["agent_registry", "agent_runtime", "agents", "tools"] },
  { label: "Sandbox", components: ["sandbox", "browser", "artifacts"] },
];

type StepState = "ok" | "wait" | "down";

// A line whose components aren't reported at all (a smaller build, the mock) is done once the gateway says it's ready.
function stepStates(components: ComponentHealth[] | undefined, gatewayUp: boolean, ready: boolean): StepState[] {
  let blocked = !gatewayUp; // lines tick in order: one isn't shown done until those above it are
  return STEPS.map((s) => {
    const mine = (components ?? []).filter((c) => s.components.includes(c.component));
    const ok = gatewayUp && !!components && mine.every((c) => c.ok) && (mine.length > 0 || ready);
    const state: StepState = blocked ? "wait" : ok ? "ok" : mine.some((c) => !c.ok) ? "down" : "wait";
    if (state !== "ok") blocked = true;
    return state;
  });
}

export function Boot() {
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme !== "light";
  const client = useClient();
  const router = useRouter();
  const [started] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);
  const health = useQuery({ queryKey: ["boot", "health"], queryFn: () => client.health(), refetchInterval: 500, retry: false });
  const status = useQuery({ queryKey: ["boot", "status"], queryFn: () => client.status(), refetchInterval: 500, retry: false, enabled: health.isSuccess });
  const models = useQuery({ queryKey: ["models"], queryFn: () => client.models(), enabled: status.isSuccess });
  const res = useQuery({ queryKey: ["system-resources"], queryFn: () => client.resources(), enabled: status.isSuccess });

  const gatewayUp = health.isSuccess;
  const states = stepStates(status.data?.components, gatewayUp, !!status.data?.ready);
  const allUp = gatewayUp && !!status.data?.ready && states.every((s) => s === "ok");
  const gaveUp = !allUp && now - started > GIVE_UP_MS;
  useEffect(() => {
    if (!allUp) return;
    const t = setTimeout(() => router.replace("/"), 1300);
    return () => clearTimeout(t);
  }, [allUp, router]);

  const chat = models.data?.find((m) => m.local !== false && m.capabilities?.includes("chat"))?.name;
  const down = (status.data?.components ?? []).filter((c) => !c.ok);
  const done = states.filter((st) => st === "ok").length + (gatewayUp ? 1 : 0);

  return (
    <main className={cn("boot fixed inset-0 z-50 grid place-items-center overflow-auto bg-grout p-6 transition-opacity duration-700", allUp && "opacity-0 delay-500")}>
      <div className="flex w-full max-w-4xl flex-col items-center gap-10 md:flex-row md:justify-center md:gap-20">
        <div className="relative grid place-items-center">
          <BigOrb state={allUp ? "shaping" : gatewayUp ? "connecting" : "breathing"} size={240} dark={dark} />
          <p className="absolute -bottom-7 font-mono text-xs text-text-2 tabular-nums">
            {done}/{STEPS.length + 1}
          </p>
        </div>
        <div className="w-full max-w-sm space-y-6">
          <div className="space-y-1.5">
            <p className="flex items-center gap-3">
              <Mark className="size-9" />
              <Wordmark className="text-4xl" />
            </p>
            <p className="font-mono text-sm text-text-2" aria-live="polite">
              {allUp ? "ready" : gaveUp ? "startup incomplete" : gatewayUp ? "starting services" : `waiting for the kernel at ${client.baseUrl}`}
            </p>
          </div>

          <ol className="space-y-0.5 font-mono text-sm">
            <li className="flex items-center gap-3 py-1">
              <StepIcon state={gatewayUp ? "ok" : gaveUp ? "down" : "wait"} />
              <span className={cn(!gatewayUp && "text-text-2")}>Gateway</span>
            </li>
            {STEPS.map((s, i) => (
              <li key={s.label} className="flex items-center gap-3 py-1">
                <StepIcon state={gaveUp && states[i] === "wait" ? "down" : states[i]} />
                <span className={cn(states[i] !== "ok" && "text-text-2")}>{s.label}</span>
                {s.label === "Models" && states[i] === "ok" && (
                  <span className="ml-auto truncate text-xs text-text-2">
                    {chat ?? ""}
                    {res.data?.gpu ? ` · ${res.data.gpu.name.replace(/^NVIDIA GeForce /, "")}` : ""}
                  </span>
                )}
              </li>
            ))}
          </ol>

          {gaveUp && (
            <div role="alert" className="space-y-2 rounded-lg border border-st-failed/60 bg-st-failed/10 p-4 text-sm">
              <p className="flex items-center gap-2 font-semibold text-st-failed">
                <CircleAlert className="size-4" aria-hidden /> Not everything came up within 60 s
              </p>
              {!gatewayUp && <p>kairosd isn&apos;t answering at {client.baseUrl}. Start it, then reload.</p>}
              {down.map((c) => (
                <p key={c.component} className="font-mono text-xs">
                  {c.component} ({c.mode}): {c.detail || "not ok"}
                </p>
              ))}
              <div className="flex gap-2 pt-1">
                <button type="button" onClick={() => location.reload()} className="rounded-md border border-line px-3 py-1.5 hover:bg-surface-3">
                  Retry
                </button>
                <button type="button" onClick={() => router.replace("/")} className="rounded-md border border-line px-3 py-1.5 hover:bg-surface-3">
                  Open the desktop anyway
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

function StepIcon({ state }: { state: StepState }) {
  if (state === "ok") return <Check className="size-4 text-st-running transition-colors duration-150" aria-label="ready" />;
  if (state === "down") return <CircleAlert className="size-4 text-st-failed" aria-label="down" />;
  return <Orb state="working" label="starting" />;
}
