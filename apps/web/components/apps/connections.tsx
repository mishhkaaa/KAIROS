"use client";

import type { Connector, ConnectorSyncResult } from "@kairos/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, GitBranch, KeyRound, RefreshCw, ShieldCheck, Unplug } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { useClient } from "@/app/providers";
import { AgentAvatar } from "@/components/desktop/agent-avatar";
import { Loading } from "@/components/desktop/orb";
import { useSession } from "@/components/session";
import { formatTime } from "@/components/status";
import { cn } from "@/lib/utils";
import { AppHeader, button, Card, errText, field, NotAllowed, Pill } from "./kit";

const LOOK: Record<string, { icon: typeof GitBranch; tint: string; account: string; accountLabel: string; tokenLabel: string; help: string }> = {
  github: {
    icon: GitBranch,
    tint: "#24292f",
    account: "owner/repo or a github.com URL (demo: acme/reconciliation)",
    accountLabel: "Repository",
    tokenLabel: "Personal access token (repo scope)",
    help: "Agents read issues, pull requests and files; opening an issue or commenting waits for an approver.",
  },
  google_calendar: {
    icon: CalendarDays,
    tint: "#1a73e8",
    account: "primary",
    accountLabel: "Calendar",
    tokenLabel: "OAuth access token (calendar scope)",
    help: "Agents read free/busy and upcoming events; creating a meeting with a Meet link waits for an approver.",
  },
};

function SyncResult({ r }: { r: ConnectorSyncResult }) {
  const paths = [...(r.created ?? []), ...(r.updated ?? [])];
  return (
    <div className="rounded-xl bg-surface-2 p-2.5 text-xs">
      <p className="font-medium">
        {paths.length
          ? `${paths.length} ${paths.length === 1 ? "document" : "documents"} brought into /org`
          : "Up to date: nothing changed since the last sync"}
        {r.errors?.length ? <span className="text-st-failed"> · {r.errors.length} failed</span> : null}
      </p>
      <ul className="mt-1 space-y-0.5 font-mono">
        {paths.slice(0, 5).map((p) => (
          <li key={p}>
            <Link href={`/knowledge?path=${encodeURIComponent(p)}`} className="text-brand hover:underline">{p}</Link>
          </li>
        ))}
        {paths.length > 5 && <li className="text-text-2">and {paths.length - 5} more</li>}
        {r.errors?.map((e) => <li key={e} className="text-st-failed">{e}</li>)}
      </ul>
    </div>
  );
}

function ConnectorCard({ c, canManage }: { c: Connector; canManage: boolean }) {
  const client = useClient();
  const qc = useQueryClient();
  const look = LOOK[c.connector_id] ?? LOOK.github;
  const Icon = look.icon;
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState("");
  const [account, setAccount] = useState("");
  const [result, setResult] = useState<ConnectorSyncResult | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["connectors"] });
  const connect = useMutation({
    mutationFn: () => client.connect(c.connector_id, { token: token.trim() || null, account: account.trim() || null }),
    onSuccess: (x) => {
      refresh();
      setOpen(false);
      setToken("");
      toast.success(`${x.name} connected`, { description: x.mode === "live" ? "The token is in the vault; agents can use it through governed syscalls." : "Using the built-in demo data (no token given)." });
    },
    onError: (e) => toast.error("Not connected", { description: errText(e) }),
  });
  const disconnect = useMutation({
    mutationFn: () => client.disconnect(c.connector_id),
    onSuccess: () => {
      refresh();
      setResult(null);
      toast.success(`${c.name} disconnected`, { description: "Its token was deleted from the vault." });
    },
    onError: (e) => toast.error("Not disconnected", { description: errText(e) }),
  });
  const sync = useMutation({
    mutationFn: () => client.syncConnector(c.connector_id),
    onSuccess: (r) => {
      refresh();
      setResult(r);
    },
    onError: (e) => toast.error("Sync failed", { description: errText(e) }),
  });
  const connected = c.status === "connected";

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-xl text-white" style={{ background: look.tint }}>
          <Icon className="size-5.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 font-semibold">
            {c.name}
            <Pill tone={connected ? "ok" : "neutral"}>{c.status}</Pill>
            {connected && (
              <Pill tone={c.mode === "live" ? "brand" : "warn"} title={c.mode === "live" ? "A real token from the vault" : "Built-in stand-in with the demo company's data"}>
                {c.mode === "live" ? "live" : "demo data"}
              </Pill>
            )}
          </p>
          <p className="mt-0.5 text-sm text-text-2">{look.help}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {(c.capabilities ?? []).map((cap) => (
          <Pill key={cap} mono tone={cap.endsWith(".write") ? "warn" : "neutral"} title={cap.endsWith(".write") ? "Needs an approver (policies/default.yaml)" : "Allowed"}>
            {cap}
            {cap.endsWith(".write") && <ShieldCheck className="size-3" />}
          </Pill>
        ))}
      </div>

      {connected && (
        <dl className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-lg bg-surface-2 px-2.5 py-1.5">
            <dt className="text-text-2">Connected by</dt>
            <dd className="font-mono">{c.connected_by ?? "…"}{c.connected_at ? ` · ${formatTime(c.connected_at)}` : ""}</dd>
          </div>
          <div className="rounded-lg bg-surface-2 px-2.5 py-1.5">
            <dt className="text-text-2">Last sync</dt>
            <dd className="font-mono">{c.last_sync ? formatTime(c.last_sync) : "never"}</dd>
          </div>
        </dl>
      )}

      {!!c.recent_agents?.length && (
        <div className="flex items-center gap-2 text-xs text-text-2">
          <span>Used recently by</span>
          {c.recent_agents.slice(0, 5).map((a) => (
            <span key={a} className="flex items-center gap-1 rounded-full bg-surface-2 py-0.5 pr-2 pl-0.5 font-mono" title={a}>
              <AgentAvatar agent={a} size={18} state="COMPLETED" /> {a.replace(/-agent.*$/, "")}
            </span>
          ))}
        </div>
      )}

      {result && <SyncResult r={result} />}

      {canManage && open && !connected && (
        <form
          className="space-y-2 rounded-xl border border-hairline bg-surface-2 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            connect.mutate();
          }}
        >
          <label className="block text-xs">
            <span className="mb-1 block font-medium">{look.accountLabel}</span>
            <input value={account} onChange={(e) => setAccount(e.target.value)} placeholder={look.account} className={cn(field, "w-full bg-surface-1 font-mono")} />
          </label>
          <label className="block text-xs">
            <span className="mb-1 flex items-center gap-1 font-medium">
              <KeyRound className="size-3" /> {look.tokenLabel}
            </span>
            <input type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} placeholder="leave empty to use the built-in demo data" className={cn(field, "w-full bg-surface-1 font-mono")} />
          </label>
          <p className="text-[11px] text-text-2">Stored encrypted in the vault. Never shown again, never logged, never given to an agent.</p>
          <div className="flex gap-2">
            <button type="submit" disabled={connect.isPending} className={button.primary}>
              Connect
            </button>
            <button type="button" onClick={() => setOpen(false)} className={button.quiet}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {canManage && (
        <div className="mt-auto flex flex-wrap gap-2 pt-1">
          {connected ? (
            <>
              <button type="button" onClick={() => sync.mutate()} disabled={sync.isPending} className={button.primary}>
                <RefreshCw className={cn("size-4", sync.isPending && "animate-spin")} /> {sync.isPending ? "Syncing…" : "Sync into /org"}
              </button>
              <button type="button" onClick={() => disconnect.mutate()} disabled={disconnect.isPending} className={button.quiet}>
                <Unplug className="size-4" /> Disconnect
              </button>
            </>
          ) : (
            !open && (
              <button type="button" onClick={() => setOpen(true)} className={button.primary}>
                Connect {c.name}
              </button>
            )
          )}
        </div>
      )}
    </Card>
  );
}

/** Outside services as governed tools: connect an account, and agents may use it only through syscalls that policy
 *  checks, audit records and (for writes) a person approves. */
export function ConnectionsApp() {
  const client = useClient();
  const { me, can } = useSession();
  const connectors = useQuery({ queryKey: ["connectors"], queryFn: () => client.connectors(), refetchInterval: 20_000 });
  const canManage = can("connectors.manage");
  const live = (connectors.data ?? []).filter((c) => c.status === "connected").length;

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <AppHeader app="connections" title="Connections" sub="Outside services your agents may use, through governed tool calls only">
        <Pill tone={live ? "ok" : "neutral"}>{live} connected</Pill>
      </AppHeader>
      {!canManage && <NotAllowed role={me?.role} permission="connectors.manage" what="connect or disconnect services" />}
      {connectors.isPending && <Loading label="Loading connections" state="working" />}
      {connectors.isError && <p className="text-sm text-st-failed">Could not load connections: {errText(connectors.error)}</p>}
      <div className="grid gap-4 @3xl:grid-cols-2">
        {(connectors.data ?? []).map((c) => (
          <ConnectorCard key={c.connector_id} c={c} canManage={canManage} />
        ))}
      </div>
      <p className="text-xs text-text-2">
        Every call an agent makes through a connector is a syscall: checked against policy, written to the audit journal, and paused for approval when it writes. Syncing copies issues, READMEs and upcoming meetings into <span className="font-mono">/org/github</span> and <span className="font-mono">/org/calendar</span>, where agents can search them.
      </p>
    </div>
  );
}
