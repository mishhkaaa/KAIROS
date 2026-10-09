import AsyncStorage from "@react-native-async-storage/async-storage";
import type { Me, Session } from "@kairos/contracts";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Platform } from "react-native";
import { type Client, createClient, GatewayError } from "./client";
import { googleSignOut } from "./google";
import { permissionsFor } from "./rbac";

const KEY = "kairos.phone";
/** The Android emulator reaches the computer it runs on as 10.0.2.2; the demo gateway listens on 8089. */
export const DEFAULT_SERVER = Platform.OS === "android" ? "http://10.0.2.2:8089" : "http://localhost:8089";

interface Stored {
  server: string;
  session: Session | null;
  notify: boolean;
}

interface SessionApi extends Stored {
  ready: boolean;
  client: Client;
  me: Me | null;
  can: (permission: string) => boolean;
  setServer: (server: string) => void;
  signIn: (s: Session) => void;
  signOut: () => void;
  setNotify: (on: boolean) => void;
}

const Ctx = createContext<SessionApi | null>(null);

export function useSession(): SessionApi {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession outside <SessionProvider>");
  return s;
}

/** Who is signed in on this phone, against which server; kept on the device. */
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [stored, setStored] = useState<Stored>({ server: DEFAULT_SERVER, session: null, notify: true });
  const [ready, setReady] = useState(false);
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((raw) => {
        if (!raw) return;
        const s = JSON.parse(raw) as Stored;
        const live = s.session && new Date(s.session.expires_at).getTime() > Date.now() ? s.session : null;
        setStored({ server: s.server || DEFAULT_SERVER, session: live, notify: s.notify !== false });
        if (live) setMe(live.me);
      })
      .catch(() => undefined)
      .finally(() => setReady(true));
  }, []);

  const save = useCallback((next: Stored) => {
    setStored(next);
    AsyncStorage.setItem(KEY, JSON.stringify(next)).catch(() => undefined);
  }, []);

  const client = useMemo(() => createClient(stored.server, stored.session?.token ?? null), [stored.server, stored.session?.token]);

  // Refresh who we are (role changes, a new org) whenever the session changes; an expired session signs out.
  useEffect(() => {
    if (!ready || !stored.session) return;
    let live = true;
    client
      .me()
      .then((m) => live && setMe(m))
      .catch((e) => {
        if (live && e instanceof GatewayError && e.status === 401) {
          setMe(null);
          save({ ...stored, session: null });
        }
      });
    return () => {
      live = false;
    };
    // only when the session or server changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, client]);

  const api = useMemo<SessionApi>(
    () => ({
      ...stored,
      ready,
      client,
      me,
      can: (p) => !!me && permissionsFor(me.role, me.permissions).has(p),
      setServer: (server) => save({ ...stored, server, session: null }),
      signIn: (session) => {
        setMe(session.me);
        save({ ...stored, session });
      },
      signOut: () => {
        client.logout().catch(() => undefined);
        googleSignOut();
        setMe(null);
        save({ ...stored, session: null });
      },
      setNotify: (notify) => save({ ...stored, notify }),
    }),
    [stored, ready, client, me, save],
  );
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}
