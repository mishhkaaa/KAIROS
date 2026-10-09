"use client";

import type { AuthConfig, Me, Session } from "@kairos/contracts";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, Building2, LogOut, Smartphone, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useClient, useSessionState } from "@/app/providers";
import { Mark, Wordmark } from "@/components/desktop/logo";
import { Orb } from "@/components/desktop/orb";
import { GlobalEvents } from "@/components/global-events";
import { KairosError } from "@/lib/kairos-client";
import { cn } from "@/lib/utils";

export interface SessionApi {
  /** Who is at the keyboard; undefined when the gateway could not say (an older gateway, or it is down). */
  me?: Me;
  /** The caller may do this. Permissive when `me` is unknown: the gateway enforces every permission anyway. */
  can: (permission: string) => boolean;
  signOut: () => void;
  switchUser: () => void;
}

const SessionContext = createContext<SessionApi>({ can: () => true, signOut: () => {}, switchUser: () => {} });

export const useSession = () => useContext(SessionContext);

export const firstName = (me?: Me) => (me?.user.name || me?.user.email.split("@")[0] || "there").split(" ")[0].replace(/^./, (c) => c.toUpperCase());

/** A person's face: their Google picture, or their initials on a colour picked from their email. */
export function PersonAvatar({ name, email, url, size = 28, className }: { name?: string | null; email: string; url?: string | null; size?: number; className?: string }) {
  const hues = ["#0d9488", "#2563eb", "#7c3aed", "#db2777", "#ea580c", "#16a34a", "#0891b2"];
  let h = 0;
  for (const c of email) h = (h * 31 + c.charCodeAt(0)) | 0;
  const initials = (name || email.split("@")[0]).split(/[\s._-]+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="" width={size} height={size} className={cn("shrink-0 rounded-full object-cover", className)} referrerPolicy="no-referrer" />;
  }
  return (
    <span className={cn("inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white", className)} style={{ width: size, height: size, fontSize: size * 0.4, background: hues[Math.abs(h) % hues.length] }} aria-hidden>
      {initials}
    </span>
  );
}

/** Between the browser and the desktop: who is signed in, and whether they belong to an organization yet. In dev mode
 *  with no session the desktop opens straight away as alice (the gateway's header caller); in Google mode a session
 *  is required. When the gateway cannot answer, the desktop opens anyway and shows what it can. */
export function SessionGate({ children }: { children: React.ReactNode }) {
  const client = useClient();
  const { hydrated, session, setSession } = useSessionState();
  const [signingIn, setSigningIn] = useState(false);
  const config = useQuery({ queryKey: ["auth-config"], queryFn: () => client.authConfig(), staleTime: Infinity, retry: 1, enabled: hydrated });
  const me = useQuery({ queryKey: ["me"], queryFn: () => client.me(), retry: false, staleTime: 5 * 60_000, enabled: hydrated });
  const unauth = me.error instanceof KairosError && me.error.status === 401;

  // A stored session the gateway no longer honours (expired, revoked, a reset database): forget it.
  useEffect(() => {
    if (unauth && session) setSession(null);
  }, [unauth, session, setSession]);

  const signOut = useCallback(() => {
    client.logout().catch(() => undefined);
    setSession(null);
    setSigningIn(true);
  }, [client, setSession]);
  const api = useMemo<SessionApi>(
    () => ({
      me: me.data,
      can: (p) => !me.data || (me.data.permissions ?? []).includes(p),
      signOut,
      switchUser: () => setSigningIn(true),
    }),
    [me.data, signOut],
  );

  if (!hydrated || me.isPending || (config.isPending && !config.isError)) return <Splash />;
  if (signingIn || unauth) {
    return (
      <SignIn
        config={config.data}
        current={session ? me.data : undefined}
        onSignedIn={(s) => {
          setSigningIn(false);
          setSession(s);
        }}
        onDevHeaders={
          config.data?.mode !== "google"
            ? () => {
                setSigningIn(false);
                setSession(null);
              }
            : undefined
        }
      />
    );
  }
  if (me.data && !me.data.org) return <Onboarding me={me.data} onDone={() => me.refetch()} onSignOut={signOut} />;
  return (
    <SessionContext.Provider value={api}>
      {children}
      <GlobalEvents />
    </SessionContext.Provider>
  );
}

/** The floor the sign-in screens stand on: the desktop's tiles, drawn in CSS. */
function Floor({ children }: { children: React.ReactNode }) {
  return (
    <div className="ground floor fixed inset-0 z-[9000] flex items-center justify-center overflow-y-auto p-4 text-foreground">
      {children}
    </div>
  );
}

function Splash() {
  return (
    <Floor>
      <div className="flex flex-col items-center gap-4" role="status" aria-label="Starting">
        <Mark className="size-12" />
        <Orb state="breathing" size={32} label="starting" />
      </div>
    </Floor>
  );
}

/** Seeded in dev mode (kernel/kairos_kernel/identity): one person per level of power, to show roles at work. */
const DEMO_PEOPLE = [
  { email: "alice@acme.example", name: "Alice", role: "owner", note: "Runs the org; can do everything" },
  { email: "priya@acme.example", name: "Priya", role: "approver", note: "Starts tasks and signs off on actions" },
  { email: "sam@acme.example", name: "Sam", role: "viewer", note: "Reads knowledge and results only" },
];

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (o: { client_id: string; callback: (r: { credential: string }) => void; auto_select?: boolean; ux_mode?: string }) => void;
          renderButton: (el: HTMLElement, o: Record<string, unknown>) => void;
          prompt: () => void;
        };
      };
    };
  }
}

function GoogleButton({ clientId, onToken }: { clientId: string; onToken: (idToken: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const cb = useRef(onToken);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    cb.current = onToken;
  }, [onToken]);
  useEffect(() => {
    const render = () => {
      if (!window.google || !box.current) return;
      window.google.accounts.id.initialize({ client_id: clientId, callback: (r) => cb.current(r.credential), ux_mode: "popup" });
      window.google.accounts.id.renderButton(box.current, { theme: "outline", size: "large", shape: "pill", text: "signin_with", width: 300 });
    };
    if (window.google) return render();
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = render;
    script.onerror = () => setFailed(true);
    document.head.appendChild(script);
  }, [clientId]);
  if (failed) return <p className="text-sm text-st-failed">Could not reach Google. Check the network and reload.</p>;
  return <div ref={box} className="flex min-h-11 justify-center" />;
}

function SignIn({ config, current, onSignedIn, onDevHeaders }: { config?: AuthConfig; current?: Me; onSignedIn: (s: Session) => void; onDevHeaders?: () => void }) {
  const client = useClient();
  const [email, setEmail] = useState("");
  const google = config?.mode === "google";
  const login = useMutation({
    mutationFn: (v: { kind: "dev"; email: string; name?: string } | { kind: "google"; token: string }) =>
      v.kind === "dev" ? client.devLogin(v.email, v.name) : client.googleLogin(v.token),
    onSuccess: onSignedIn,
  });
  const error = login.error instanceof KairosError ? login.error.message.replace(/^[A-Z_]+: /, "") : login.error ? String(login.error) : null;

  return (
    <Floor>
      <main className="panel stage-in w-full max-w-[420px] rounded-[24px] p-7 shadow-window" aria-label="Sign in">
        <div className="flex flex-col items-center text-center">
          <Mark className="size-11" />
          <h1 className="mt-3 text-2xl font-semibold tracking-tight">
            Sign in to <Wordmark />
          </h1>
          <p className="mt-1 text-sm text-text-2">Your organization&apos;s AI: agents, knowledge and every action they take, in one place.</p>
        </div>

        {google ? (
          <div className="mt-7 space-y-3">
            {config?.google_client_id ? (
              <GoogleButton clientId={config.google_client_id} onToken={(token) => login.mutate({ kind: "google", token })} />
            ) : (
              <p className="text-sm text-st-failed">Google sign-in is on but KAIROS_GOOGLE_CLIENT_ID is not set on the server.</p>
            )}
            <p className="text-center text-xs text-text-2">People from your company&apos;s email domain join its organization automatically.</p>
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-2">Demo organization · Acme Corp</p>
              <ul className="space-y-1.5">
                {DEMO_PEOPLE.map((p) => (
                  <li key={p.email}>
                    <button
                      type="button"
                      onClick={() => login.mutate({ kind: "dev", email: p.email, name: p.name })}
                      disabled={login.isPending}
                      className={cn(
                        "group flex w-full items-center gap-3 rounded-xl border border-hairline bg-surface-1 p-2.5 text-left transition-colors hover:border-brand/40 hover:bg-brand-subtle/50 disabled:opacity-60",
                        current?.user.email === p.email && "border-brand/50",
                      )}
                    >
                      <PersonAvatar name={p.name} email={p.email} size={34} />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2 text-sm font-semibold">
                          {p.name}
                          <span className="rounded-full bg-surface-3 px-1.5 py-px font-mono text-[10.5px] font-medium text-text-2">{p.role}</span>
                        </span>
                        <span className="block truncate text-xs text-text-2">{p.note}</span>
                      </span>
                      <ArrowRight className="size-4 text-text-2 opacity-0 transition-opacity group-hover:opacity-100" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (email.includes("@")) login.mutate({ kind: "dev", email });
              }}
            >
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="or any email, e.g. you@startup.io"
                aria-label="Email"
                className="h-10 min-w-0 flex-1 rounded-xl border border-hairline bg-surface-2 px-3 text-sm outline-none focus:border-brand"
              />
              <button type="submit" disabled={!email.includes("@") || login.isPending} className="h-10 rounded-xl bg-brand px-4 text-sm font-medium text-white hover:bg-brand-hover disabled:opacity-50">
                Continue
              </button>
            </form>
            {onDevHeaders && (
              <button type="button" onClick={onDevHeaders} className="w-full text-center text-xs text-text-2 underline-offset-2 hover:underline">
                Skip: continue as the local developer (Alice, owner)
              </button>
            )}
          </div>
        )}

        {login.isPending && (
          <p className="mt-4 flex items-center justify-center gap-2 text-sm text-text-2" role="status">
            <Orb state="working" label="signing in" /> Signing in…
          </p>
        )}
        {error && <p className="mt-4 rounded-lg bg-st-failed/10 px-3 py-2 text-sm text-st-failed" role="alert">{error}</p>}
        <p className="mt-6 border-t border-hairline pt-3 text-center font-mono text-[11px] text-text-2">
          {google ? "google sign-in · sessions expire after a working day" : "dev sign-in · KAIROS_AUTH=google for Google accounts"}
        </p>
      </main>
    </Floor>
  );
}

function Onboarding({ me, onDone, onSignOut }: { me: Me; onDone: () => void; onSignOut: () => void }) {
  const client = useClient();
  const domain = me.user.email.split("@")[1] ?? "";
  const [name, setName] = useState("");
  const [join, setJoin] = useState(true);
  const create = useMutation({ mutationFn: () => client.createOrg({ name: name.trim(), domain: join ? domain : null }), onSuccess: onDone });
  const error = create.error instanceof KairosError ? create.error.message.replace(/^[A-Z_]+: /, "") : null;
  return (
    <Floor>
      <main className="panel stage-in w-full max-w-[460px] rounded-[24px] p-7 shadow-window" aria-label="Create your organization">
        <div className="flex items-center gap-3">
          <PersonAvatar name={me.user.name} email={me.user.email} url={me.user.avatar_url} size={40} />
          <div>
            <p className="text-lg font-semibold">Welcome, {firstName(me)}.</p>
            <p className="text-sm text-text-2">{me.user.email} is not in an organization yet.</p>
          </div>
        </div>
        <form
          className="mt-6 space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) create.mutate();
          }}
        >
          <label className="block">
            <span className="mb-1 block text-sm font-medium">Organization name</span>
            <span className="flex items-center gap-2 rounded-xl border border-hairline bg-surface-2 px-3 focus-within:border-brand">
              <Building2 className="size-4 text-text-2" />
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Startup Labs" className="h-10 min-w-0 flex-1 bg-transparent text-sm outline-none" autoFocus />
            </span>
          </label>
          {domain && (
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" checked={join} onChange={(e) => setJoin(e.target.checked)} className="mt-0.5 accent-[var(--brand)]" />
              <span>
                Anyone with an <span className="font-mono">@{domain}</span> email joins as a member when they sign in.
              </span>
            </label>
          )}
          <button type="submit" disabled={!name.trim() || create.isPending} className="flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-brand text-sm font-medium text-white hover:bg-brand-hover disabled:opacity-50">
            {create.isPending ? <Orb state="working" label="creating" /> : null}
            Create organization. You will be its owner.
          </button>
          {error && <p className="rounded-lg bg-st-failed/10 px-3 py-2 text-sm text-st-failed" role="alert">{error}</p>}
        </form>
        <div className="mt-6 flex items-center justify-between border-t border-hairline pt-3 text-xs text-text-2">
          <span>Joining a team? Ask an admin to invite {me.user.email}.</span>
          <button type="button" onClick={onSignOut} className="flex items-center gap-1 hover:text-foreground">
            <LogOut className="size-3.5" /> Sign out
          </button>
        </div>
      </main>
    </Floor>
  );
}

/** Sign in on the phone: a one-time code from the gateway, typed into the KAIROS app with this server's address. */
export function PairPhone({ onClose }: { onClose: () => void }) {
  const client = useClient();
  const code = useMutation({ mutationFn: () => client.pair() });
  const [now, setNow] = useState(() => Date.now());
  const { mutate } = code;
  useEffect(() => mutate(), [mutate]);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const left = code.data ? Math.max(0, Math.round((new Date(code.data.expires_at).getTime() - now) / 1000)) : 0;
  const local = /localhost|127\.0\.0\.1/.test(client.baseUrl);
  // A portal: opened from the menu bar, whose backdrop blur would otherwise contain this fixed overlay.
  return createPortal(
    <div className="fixed inset-0 z-[8000] flex items-center justify-center bg-[rgb(15_23_42/0.18)] p-4" onPointerDown={onClose}>
      <section role="dialog" aria-modal="true" aria-label="Sign in on your phone" onPointerDown={(e) => e.stopPropagation()} className="panel spotlight-in w-full max-w-[420px] rounded-[22px] p-6 shadow-window">
        <div className="flex items-center gap-3">
          <span className="flex size-10 items-center justify-center rounded-xl bg-brand text-white">
            <Smartphone className="size-5" />
          </span>
          <div className="flex-1">
            <h2 className="font-semibold">Sign in on your phone</h2>
            <p className="text-sm text-text-2">Open the KAIROS app and choose &ldquo;I have a code&rdquo;.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-text-2 hover:bg-surface-3">
            <X className="size-4" />
          </button>
        </div>
        <div className="mt-5 rounded-2xl bg-surface-2 p-4 text-center">
          {code.data ? (
            <>
              <p className="font-mono text-[34px] font-bold tracking-[0.18em]" aria-label="Pairing code">{code.data.code}</p>
              <p className={cn("mt-1 font-mono text-xs", left < 60 ? "text-st-waiting" : "text-text-2")}>
                {left > 0 ? `works once, for ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}` : "expired"}
              </p>
            </>
          ) : code.isError ? (
            <p className="text-sm text-st-failed">{code.error instanceof KairosError ? code.error.message.replace(/^[A-Z_]+: /, "") : "Could not make a code."}</p>
          ) : (
            <Orb state="working" size={32} label="making a code" className="mx-auto" />
          )}
        </div>
        <dl className="mt-4 space-y-1 text-sm">
          <div className="flex justify-between gap-3">
            <dt className="text-text-2">Server</dt>
            <dd className="truncate font-mono text-xs">{client.baseUrl}</dd>
          </div>
        </dl>
        {local && (
          <p className="mt-2 text-xs text-text-2">
            On a phone, use this computer&apos;s network address instead of localhost (<span className="font-mono">scripts\win\phone-access.ps1</span> prints it). The Android emulator reaches it as <span className="font-mono">10.0.2.2</span>.
          </p>
        )}
        <button type="button" onClick={() => mutate()} disabled={code.isPending} className="mt-4 w-full rounded-xl border border-hairline py-2 text-sm hover:bg-surface-3 disabled:opacity-50">
          New code
        </button>
      </section>
    </div>,
    document.body,
  );
}
