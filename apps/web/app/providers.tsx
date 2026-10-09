"use client";

import type { Session } from "@kairos/contracts";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { createContext, useCallback, useContext, useMemo, useState, useSyncExternalStore } from "react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { resolveGatewayUrl } from "@/lib/gateway-url";
import { DEFAULT_BASE_URL, createKairosClient, type KairosClient, parseSession, readSessionRaw, saveSession, subscribeSession } from "@/lib/kairos-client";

const ClientContext = createContext<KairosClient | null>(null);

export function useClient(): KairosClient {
  const c = useContext(ClientContext);
  if (!c) throw new Error("useClient must be used inside <Providers>");
  return c;
}

export interface SessionState {
  /** False during the server render and hydration, before this browser's stored session has been read. */
  hydrated: boolean;
  session: Session | null;
  /** Start a session (after sign-in) or end it (null). Every cached query belonged to the previous caller. */
  setSession: (s: Session | null) => void;
}

const SessionContext = createContext<SessionState | null>(null);

export function useSessionState(): SessionState {
  const s = useContext(SessionContext);
  if (!s) throw new Error("useSessionState must be used inside <Providers>");
  return s;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 1_000 } } }),
  );
  const [baseUrl] = useState(() => resolveGatewayUrl(DEFAULT_BASE_URL, typeof window === "undefined" ? undefined : window.location));
  // null on the server (not read yet); "" in a browser with no stored session.
  const raw = useSyncExternalStore<string | null>(subscribeSession, readSessionRaw, () => null);
  const session = useMemo(() => parseSession(raw), [raw]);
  const token = session?.token ?? null;
  const client = useMemo(() => createKairosClient(baseUrl, "alice", "acme", token), [baseUrl, token]);
  const setSession = useCallback(
    (s: Session | null) => {
      queryClient.clear();
      saveSession(s);
    },
    [queryClient],
  );
  const state = useMemo(() => ({ hydrated: raw !== null, session, setSession }), [raw, session, setSession]);

  return (
    <ThemeProvider attribute="data-theme" defaultTheme="light" enableSystem storageKey="theme" disableTransitionOnChange>
      <SessionContext.Provider value={state}>
        <ClientContext.Provider value={client}>
          <QueryClientProvider client={queryClient}>
            <TooltipProvider delayDuration={200}>
              {children}
              <Toaster position="bottom-right" closeButton expand visibleToasts={4} duration={4_000} />
            </TooltipProvider>
          </QueryClientProvider>
        </ClientContext.Provider>
      </SessionContext.Provider>
    </ThemeProvider>
  );
}
