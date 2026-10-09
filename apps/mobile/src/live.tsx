import type { Approval, Task } from "@kairos/contracts";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { AppState } from "react-native";
import { reason } from "./client";
import { notify } from "./notify";
import { useSession } from "./session";
import { isActive } from "./theme";

interface Live {
  tasks: Task[];
  approvals: Approval[];
  connected: boolean;
  error: string | null;
  loaded: boolean;
  refresh: () => Promise<void>;
}

const Ctx = createContext<Live>({ tasks: [], approvals: [], connected: false, error: null, loaded: false, refresh: async () => {} });
export const useLive = () => useContext(Ctx);

const VERB: Record<string, string> = { write: "write to", read: "read from", delete: "delete from", open: "open", exec: "run code in", send: "send via" };
const TARGET: Record<string, string> = { jira: "Jira", fs: "the file system", browser: "a web page", email: "email", slack: "Slack", github: "GitHub", calendar: "the calendar" };

/** "action-agent wants to write to Jira", from the capability (jira.write). */
export function headline(a: Approval): string {
  const [tool, op] = a.syscall.capability.split(".");
  return `${a.agent} wants ${VERB[op] ? `to ${VERB[op]} ${TARGET[tool] ?? tool}` : a.syscall.capability}`;
}

/** Tasks and pending approvals, kept fresh by the event stream (and a slow poll behind it), with a notification when
 *  an approval appears or a task finishes. */
export function LiveProvider({ children }: { children: React.ReactNode }) {
  const { client, notify: wantNotify, can } = useSession();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const seenApprovals = useRef<Set<string> | null>(null);
  const lastStatus = useRef<Map<string, string> | null>(null);
  const foreground = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const [t, a] = await Promise.all([client.tasks(), client.approvals("pending")]);
      t.sort((x, y) => (y.created_at ?? "").localeCompare(x.created_at ?? ""));
      // Notify only about changes after the first load.
      if (seenApprovals.current && wantNotify) {
        for (const x of a)
          if (!seenApprovals.current.has(x.approval_id))
            notify(can("approval.resolve") ? "Needs your decision" : "Waiting for an approver", headline(x), { screen: "approvals", approval: x.approval_id }, "approvals");
      }
      if (lastStatus.current && wantNotify) {
        for (const x of t) {
          const before = lastStatus.current.get(x.task_id);
          if (before && isActive(before) && (x.status === "completed" || x.status === "failed"))
            notify(x.status === "completed" ? "Task done" : "Task failed", x.goal, { screen: "task", task: x.task_id }, "tasks");
        }
      }
      seenApprovals.current = new Set(a.map((x) => x.approval_id));
      lastStatus.current = new Map(t.map((x) => [x.task_id, x.status ?? ""]));
      setTasks(t);
      setApprovals(a);
      setError(null);
    } catch (e) {
      setError(reason(e));
    } finally {
      setLoaded(true);
    }
  }, [client, wantNotify, can]);

  useEffect(() => {
    seenApprovals.current = null;
    lastStatus.current = null;
    refresh();
    // The stream says when something changed; the poll catches anything the stream missed.
    let soon: ReturnType<typeof setTimeout> | undefined;
    const kick = () => {
      soon ??= setTimeout(() => {
        soon = undefined;
        refresh();
      }, 300);
    };
    const stop = client.events(kick, ["task.*", "approval.*"], setConnected);
    const timer = setInterval(() => foreground.current && refresh(), 8_000);
    const sub = AppState.addEventListener("change", (s) => {
      foreground.current = s === "active";
      if (s === "active") refresh();
    });
    return () => {
      stop();
      clearTimeout(soon);
      clearInterval(timer);
      sub.remove();
    };
  }, [client, refresh]);

  const value = useMemo(() => ({ tasks, approvals, connected, error, loaded, refresh }), [tasks, approvals, connected, error, loaded, refresh]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
