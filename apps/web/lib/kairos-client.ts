// Typed client for the KAIROS gateway. The ONLY way the web UI talks to the backend.
// Works unchanged against the mock gateway (`uv run kairos-mock-gateway`) and the real kernel.
// Owner: P2. Types are generated from the Python contracts; never hand-write backend shapes here.
import type {
  AgentManifest,
  AgentProcess,
  Approval,
  AuthConfig,
  Checkpoint,
  Connector,
  ConnectorConnect,
  ConnectorSyncResult,
  IngestResult,
  KnowledgeMount,
  KnowledgeMountCreate,
  Me,
  Member,
  MemberInvite,
  Org,
  OrgCreate,
  OrgRole,
  PairCode,
  Session,
  SystemConfig,
  EvidenceSet,
  Event,
  GraphResult,
  KnowledgeListing,
  KnowledgeObject,
  MemoryRecord,
  ModelInfo,
  PolicyDocument,
  ProcessTreeNode,
  ResourceSnapshot,
  RunTimeline,
  SandboxInfo,
  SystemStatus,
  Task,
  TaskCreate,
  ToolSpec,
  ValidationReport,
} from "@kairos/contracts";
import { ORG_HEADER, USER_HEADER, WS_EVENTS_PATH } from "@kairos/contracts";


/** One file's progress through upload, conversion and indexing, from `ingest.progress` events. */
export interface IngestProgress {
  file: string;
  stage: "received" | "indexed" | "skipped" | "error";
  path?: string | null;
  error?: string | null;
}

/** Where the signed-in session lives in this browser. A tiny external store, so React reads it with
 *  useSyncExternalStore: other tabs signing in or out are seen through the storage event. */
export const SESSION_KEY = "kairos.session";
const SESSION_EVENT = "kairos:session";

export function parseSession(raw: string | null): Session | null {
  if (!raw) return null;
  try {
    const s = JSON.parse(raw) as Session;
    return s.token && new Date(s.expires_at).getTime() > Date.now() ? s : null;
  } catch {
    return null;
  }
}

export function readSessionRaw(): string {
  try {
    return window.localStorage.getItem(SESSION_KEY) ?? "";
  } catch {
    return "";
  }
}

export function loadSession(): Session | null {
  return typeof window === "undefined" ? null : parseSession(readSessionRaw());
}

export function saveSession(s: Session | null) {
  try {
    if (s) window.localStorage.setItem(SESSION_KEY, JSON.stringify(s));
    else window.localStorage.removeItem(SESSION_KEY);
  } catch {
    /* storage blocked: the session lasts until the next reload */
  }
  window.dispatchEvent(new Event(SESSION_EVENT));
}

export function subscribeSession(onChange: () => void): () => void {
  const onStorage = (e: StorageEvent) => e.key === SESSION_KEY && onChange();
  window.addEventListener(SESSION_EVENT, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(SESSION_EVENT, onChange);
    window.removeEventListener("storage", onStorage);
  };
}

export class KairosError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(`${code}: ${message}`);
  }
}

export type StreamStatus = "connecting" | "open" | "reconnecting" | "closed";

export const DEFAULT_BASE_URL = process.env.NEXT_PUBLIC_KAIROS_URL ?? "http://localhost:8080";

/** artifact://<task_id>/<name> → <baseUrl>/tasks/<task_id>/artifacts/<name> (each segment URL-encoded). */
export function artifactUrl(baseUrl: string, ref: string): string | null {
  const m = /^artifact:\/\/([^/]+)\/(.+)$/.exec(ref);
  if (!m) return null;
  const name = m[2].split("/").map(encodeURIComponent).join("/");
  return `${baseUrl}/tasks/${encodeURIComponent(m[1])}/artifacts/${name}`;
}

export function createKairosClient(baseUrl = DEFAULT_BASE_URL, user = "alice", org = "acme", token: string | null = null) {
  // Signed in: the session token. Otherwise (dev mode) the X-Kairos-User/Org headers, which the gateway treats as alice@acme.
  const auth = (): Record<string, string> => (token ? { Authorization: `Bearer ${token}` } : { [USER_HEADER]: user, [ORG_HEADER]: org });
  const json = () => ({ "Content-Type": "application/json", ...auth() });

  async function fail(res: Response): Promise<never> {
    const err = await res.json().catch(() => ({ code: "INTERNAL", message: res.statusText }));
    throw new KairosError(res.status, err.code ?? "INTERNAL", err.message ?? err.detail ?? res.statusText);
  }

  async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${baseUrl}${path}`, { method, headers: json(), body: body === undefined ? undefined : JSON.stringify(body) });
    if (!res.ok) return fail(res);
    return (res.status === 204 ? undefined : res.json()) as Promise<T>;
  }
  const q = (params: Record<string, string | number | undefined>) => {
    const s = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)]));
    return s.size ? `?${s}` : "";
  };

  const withToken = (url: string | null) => (url && token ? `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}` : url);
  const orgPath = (orgId: string) => `/orgs/${encodeURIComponent(orgId)}`;

  return {
    baseUrl,
    /** The session this client sends, if any (a new client is made when it changes). */
    token,
    // identity and the org
    authConfig: () => call<AuthConfig>("GET", "/auth/config"),
    devLogin: (email: string, name = "") => call<Session>("POST", "/auth/dev", { email, name }),
    googleLogin: (idToken: string) => call<Session>("POST", "/auth/google", { id_token: idToken }),
    me: () => call<Me>("GET", "/auth/me"),
    logout: () => call<void>("POST", "/auth/logout"),
    /** A one-time code that signs this person in on their phone. */
    pair: () => call<PairCode>("POST", "/auth/pair"),
    createOrg: (body: OrgCreate) => call<Org>("POST", "/orgs", body),
    myOrg: () => call<Org>("GET", "/orgs/me"),
    members: (orgId: string) => call<Member[]>("GET", `${orgPath(orgId)}/members`),
    invite: (orgId: string, body: MemberInvite) => call<Member>("POST", `${orgPath(orgId)}/members`, body),
    setRole: (orgId: string, member: string, role: string) =>
      call<Member>("PATCH", `${orgPath(orgId)}/members/${encodeURIComponent(member)}`, { role }),
    removeMember: (orgId: string, member: string) => call<void>("DELETE", `${orgPath(orgId)}/members/${encodeURIComponent(member)}`),
    roles: (orgId: string) => call<OrgRole[]>("GET", `${orgPath(orgId)}/roles`),
    // connectors (GitHub, Google Calendar): governed tools; tokens go to the vault and never come back
    connectors: () => call<Connector[]>("GET", "/connectors"),
    connect: (id: string, body: ConnectorConnect = {}) => call<Connector>("POST", `/connectors/${encodeURIComponent(id)}/connect`, body),
    disconnect: (id: string) => call<void>("DELETE", `/connectors/${encodeURIComponent(id)}`),
    syncConnector: (id: string) => call<ConnectorSyncResult>("POST", `/connectors/${encodeURIComponent(id)}/sync`),
    // tasks
    createTask: (body: TaskCreate) => call<Task>("POST", "/tasks", body),
    listTasks: () => call<Task[]>("GET", "/tasks"),
    getTask: (id: string) => call<Task>("GET", `/tasks/${id}`),
    cancelTask: (id: string) => call<Task>("POST", `/tasks/${id}/cancel`),
    taskArtifacts: (id: string) => call<string[]>("GET", `/tasks/${id}/artifacts`),
    /** URL of an artifact's bytes (for <img src>, links); null if `ref` isn't artifact://<task>/<name>. */
    artifactUrl: (ref: string) => withToken(artifactUrl(baseUrl, ref)),
    artifactText: async (ref: string) => {
      const url = artifactUrl(baseUrl, ref);
      if (!url) throw new KairosError(400, "BAD_REQUEST", `not an artifact ref: ${ref}`);
      const res = await fetch(url, { headers: auth() });
      if (!res.ok) return fail(res);
      return res.text();
    },
    // processes
    listProcesses: (taskId?: string) => call<AgentProcess[]>("GET", `/agents${q({ task_id: taskId })}`),
    processTree: (taskId?: string) => call<ProcessTreeNode[]>("GET", `/agents/tree${q({ task_id: taskId })}`),
    killProcess: (pid: number) => call<AgentProcess>("POST", `/agents/${pid}/kill`),
    pauseProcess: (pid: number) => call<AgentProcess>("POST", `/agents/${pid}/pause`),
    resumeProcess: (pid: number) => call<AgentProcess>("POST", `/agents/${pid}/resume`),
    registry: () => call<AgentManifest[]>("GET", "/registry/agents"),
    // knowledge
    search: (text: string, topK = 8) => call<EvidenceSet>("GET", `/knowledge/search${q({ q: text, top_k: topK })}`),
    tree: (path = "/org") => call<KnowledgeListing>("GET", `/knowledge/tree${q({ path })}`),
    object: (path: string) => call<KnowledgeObject>("GET", `/knowledge/object${q({ path })}`),
    graph: (path: string, depth = 1) => call<GraphResult>("GET", `/knowledge/graph${q({ path, depth })}`),
    validate: () => call<ValidationReport>("POST", "/knowledge/validate"),
    memory: (opts: { owner?: string; taskId?: string } = {}) =>
      call<MemoryRecord[]>("GET", `/memory${q({ owner: opts.owner, task_id: opts.taskId })}`),
    // governance
    approvals: (status?: string) => call<Approval[]>("GET", `/approvals${q({ status })}`),
    approve: (id: string, comment?: string) => call<Approval>("POST", `/approvals/${id}/approve`, { comment }),
    reject: (id: string, comment?: string) => call<Approval>("POST", `/approvals/${id}/reject`, { comment }),
    audit: (taskId: string) => call<RunTimeline>("GET", `/audit/${taskId}`),
    // added for the revamped console (existing routes only)
    health: () => call<Record<string, unknown>>("GET", "/health"),
    models: () => call<ModelInfo[]>("GET", "/models"),
    registryTools: () => call<ToolSpec[]>("GET", "/registry/tools"),
    getProcess: (pid: number) => call<AgentProcess>("GET", `/agents/${pid}`),
    checkpointProcess: (pid: number) => call<Checkpoint>("POST", `/agents/${pid}/checkpoint`),
    resumeTask: (id: string) => call<Task>("POST", `/tasks/${id}/resume`),
    checkpointTask: (id: string) => call<Checkpoint[]>("POST", `/tasks/${id}/checkpoint`),
    reindex: () => call<Record<string, number>>("POST", "/knowledge/reindex"),
    policies: () => call<PolicyDocument[]>("GET", "/policies"),
    // system
    status: () => call<SystemStatus>("GET", "/system/status"),
    systemConfig: () => call<SystemConfig>("GET", "/system/config"),
    resources: () => call<ResourceSnapshot>("GET", "/system/resources"),
    sandboxes: (taskId?: string) => call<SandboxInfo[]>("GET", `/sandboxes${q({ task_id: taskId })}`),
    // files from outside /org: uploads, and folders of this computer mounted into /org/mnt/<name>
    upload: async (files: File[], folder = "/org/uploads", privacy?: string) => {
      const fd = new FormData();
      for (const f of files) fd.append("files", f, f.name);
      fd.append("target_folder", folder);
      if (privacy) fd.append("privacy", privacy);
      const res = await fetch(`${baseUrl}/knowledge/upload`, { method: "POST", headers: auth(), body: fd });
      if (!res.ok) return fail(res);
      return res.json() as Promise<IngestResult>;
    },
    mounts: () => call<KnowledgeMount[]>("GET", "/knowledge/mounts"),
    addMount: (body: KnowledgeMountCreate) => call<KnowledgeMount>("POST", "/knowledge/mounts", body),
    syncMount: (name: string) => call<KnowledgeMount>("POST", `/knowledge/mounts/${encodeURIComponent(name)}/sync`),
    removeMount: (name: string) => call<void>("DELETE", `/knowledge/mounts/${encodeURIComponent(name)}`),

    /** Subscribe to the live event stream, reconnecting with exponential backoff. Returns an unsubscribe function.
     *  The real gateway replays a task's history on connect, so consumers must de-duplicate by event_id. */
    events(
      onEvent: (e: Event) => void,
      opts: { taskId?: string; types?: string[]; onStatus?: (s: StreamStatus) => void } = {},
    ): () => void {
      const socketUrl = () => {
        const url = new URL(WS_EVENTS_PATH + q({ task_id: opts.taskId, types: opts.types?.join(","), token: token ?? undefined }), baseUrl);
        url.protocol = url.protocol.replace("http", "ws");
        return url;
      };
      let ws: WebSocket | null = null;
      let stopped = false;
      let attempt = 0;
      let timer: ReturnType<typeof setTimeout> | undefined;

      const connect = () => {
        opts.onStatus?.(attempt === 0 ? "connecting" : "reconnecting");
        ws = new WebSocket(socketUrl());
        ws.onopen = () => {
          attempt = 0;
          opts.onStatus?.("open");
        };
        ws.onmessage = (m) => onEvent(JSON.parse(m.data) as Event);
        ws.onclose = () => {
          if (stopped) return;
          const delay = Math.min(10_000, 500 * 2 ** attempt) * (0.8 + Math.random() * 0.4);
          attempt += 1;
          opts.onStatus?.("reconnecting");
          timer = setTimeout(connect, delay);
        };
        ws.onerror = () => ws?.close();
      };
      connect();
      return () => {
        stopped = true;
        clearTimeout(timer);
        ws?.close();
        opts.onStatus?.("closed");
      };
    },
  };
}

export type KairosClient = ReturnType<typeof createKairosClient>;
