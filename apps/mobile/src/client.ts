// Typed gateway client for the phone. Shapes come from @kairos/contracts (generated from the Python contracts); never
// hand-write them. Signed in, it sends the session token; before that only the sign-in routes are used.
import type {
  Approval,
  AuthConfig,
  EvidenceSet,
  Event,
  Me,
  ProcessTreeNode,
  RunTimeline,
  Session,
  Task,
  TaskCreate,
} from "@kairos/contracts";
import { WS_EVENTS_PATH } from "@kairos/contracts";

export class GatewayError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

/** A readable reason for a failed call, for the screen. */
export function reason(e: unknown): string {
  if (e instanceof GatewayError) return e.message;
  const msg = e instanceof Error ? e.message : String(e);
  // Timeouts and refused connections arrive as AbortError, TypeError or Expo's "fetch failed: ... canceled".
  if (e instanceof TypeError || (e instanceof Error && e.name === "AbortError") || /fetch failed|cancel|abort|network request failed/i.test(msg))
    return "Cannot reach the server. Check the address, and that this phone is on the same network (or connected by USB with adb reverse).";
  return msg;
}

export const normaliseUrl = (url: string) => {
  const u = url.trim().replace(/\/+$/, "");
  return /^https?:\/\//.test(u) ? u : `http://${u}`;
};

export function createClient(baseUrl: string, token: string | null) {
  const root = normaliseUrl(baseUrl);

  async function call<T>(method: "GET" | "POST", path: string, body?: unknown, timeoutMs = 12_000): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(root + path, {
        method,
        signal: controller.signal,
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const text = await res.text();
      const data = text ? JSON.parse(text) : null;
      if (!res.ok) throw new GatewayError(res.status, data?.code ?? "HTTP_ERROR", data?.message ?? data?.detail ?? res.statusText);
      return data as T;
    } finally {
      clearTimeout(timer);
    }
  }
  const q = (params: Record<string, string | number | undefined>) => {
    const s = Object.entries(params)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
      .join("&");
    return s ? `?${s}` : "";
  };

  return {
    root,
    health: () => call<{ ok: boolean }>("GET", "/health", undefined, 5_000),
    authConfig: () => call<AuthConfig>("GET", "/auth/config", undefined, 5_000),
    devLogin: (email: string, name = "") => call<Session>("POST", "/auth/dev", { email, name }),
    redeem: (code: string) => call<Session>("POST", "/auth/pair/redeem", { code }),
    googleLogin: (idToken: string) => call<Session>("POST", "/auth/google", { id_token: idToken }),
    me: () => call<Me>("GET", "/auth/me"),
    logout: () => call<void>("POST", "/auth/logout"),
    tasks: () => call<Task[]>("GET", "/tasks"),
    task: (id: string) => call<Task>("GET", `/tasks/${encodeURIComponent(id)}`),
    createTask: (body: TaskCreate) => call<Task>("POST", "/tasks", body),
    cancelTask: (id: string) => call<Task>("POST", `/tasks/${encodeURIComponent(id)}/cancel`),
    processTree: (taskId: string) => call<ProcessTreeNode[]>("GET", `/agents/tree${q({ task_id: taskId })}`),
    timeline: (taskId: string) => call<RunTimeline>("GET", `/audit/${encodeURIComponent(taskId)}`),
    approvals: (status = "pending") => call<Approval[]>("GET", `/approvals${q({ status })}`),
    approve: (id: string, comment?: string) => call<Approval>("POST", `/approvals/${encodeURIComponent(id)}/approve`, { comment: comment || null }),
    reject: (id: string, comment?: string) => call<Approval>("POST", `/approvals/${encodeURIComponent(id)}/reject`, { comment: comment || null }),
    search: (text: string, topK = 8) => call<EvidenceSet>("GET", `/knowledge/search${q({ q: text, top_k: topK })}`),

    /** The live event stream, reconnecting with backoff. Returns a function that closes it. */
    events(onEvent: (e: Event) => void, types: string[], onOpen?: (open: boolean) => void): () => void {
      let ws: WebSocket | null = null;
      let stopped = false;
      let attempt = 0;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const url = root.replace(/^http/, "ws") + WS_EVENTS_PATH + q({ types: types.join(","), token: token ?? undefined });
      const connect = () => {
        ws = new WebSocket(url);
        ws.onopen = () => {
          attempt = 0;
          onOpen?.(true);
        };
        ws.onmessage = (m) => {
          try {
            onEvent(JSON.parse(String(m.data)) as Event);
          } catch {
            /* not an event */
          }
        };
        ws.onclose = () => {
          onOpen?.(false);
          if (stopped) return;
          attempt += 1;
          timer = setTimeout(connect, Math.min(15_000, 800 * 2 ** attempt));
        };
        ws.onerror = () => ws?.close();
      };
      connect();
      return () => {
        stopped = true;
        clearTimeout(timer);
        ws?.close();
      };
    },
  };
}

export type Client = ReturnType<typeof createClient>;
