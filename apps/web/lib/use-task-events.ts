"use client";

import type { Event } from "@kairos/contracts";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useClient } from "@/app/providers";
import { buildTaskView, isActive, mergeEvents, type TaskView } from "./events";
import type { StreamStatus } from "./kairos-client";

// Events after which a snapshot is worth re-reading (the stream carries ids, the snapshot carries detail).
const REFRESH_ON: Record<string, string[][]> = {
  "approval.requested": [["approvals"]],
  "approval.resolved": [["approvals"]],
  "process.spawned": [["agents"]],
  "process.state_changed": [["agents"]],
  "task.completed": [["task"], ["artifacts"]],
  "task.failed": [["task"]],
  "sandbox.screenshot": [["artifacts"]],
};

/** Snapshot (task, processes, pending approvals) + the live /ws/events stream → one TaskView (brief §7). */
export function useTaskEvents(taskId: string): TaskView & { stream: StreamStatus; events: Event[] } {
  const client = useClient();
  const qc = useQueryClient();
  const [received, setReceived] = useState<{ taskId: string; events: Event[] }>({ taskId, events: [] });
  const events = useMemo(() => (received.taskId === taskId ? received.events : []), [received, taskId]);
  const [stream, setStream] = useState<StreamStatus>("connecting");

  const task = useQuery({ queryKey: ["task", taskId], queryFn: () => client.getTask(taskId) });
  const active = isActive(task.data?.status);
  const agents = useQuery({
    queryKey: ["agents", taskId],
    queryFn: () => client.listProcesses(taskId),
    refetchInterval: active ? 4_000 : false,
  });
  const approvals = useQuery({ queryKey: ["approvals", taskId], queryFn: () => client.approvals() });

  useEffect(() => {
    const seen = new Map<string, Event>();
    let pending: ReturnType<typeof setTimeout> | undefined;
    const refresh = new Set<string>();
    const unsubscribe = client.events(
      (e) => {
        if (e.task_id && e.task_id !== taskId) return;
        if (mergeEvents(seen, [e])) setReceived({ taskId, events: [...seen.values()] });
        for (const key of REFRESH_ON[e.type] ?? []) refresh.add(key[0]);
        if (refresh.size && !pending) {
          pending = setTimeout(() => {
            for (const k of refresh) qc.invalidateQueries({ queryKey: [k, taskId] });
            refresh.clear();
            pending = undefined;
          }, 250);
        }
      },
      { taskId, onStatus: setStream },
    );
    return () => {
      clearTimeout(pending);
      unsubscribe();
    };
  }, [client, qc, taskId]);

  const view = useMemo(
    () =>
      buildTaskView(
        { task: task.data, processes: agents.data, approvals: approvals.data?.filter((a) => a.task_id === taskId) },
        events,
      ),
    [task.data, agents.data, approvals.data, events, taskId],
  );
  return { ...view, stream, events };
}
