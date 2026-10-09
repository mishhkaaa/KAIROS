"use client";

import type { AgentProcess } from "@kairos/contracts";
import { ALLOWED_TRANSITIONS } from "@kairos/contracts";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { useClient } from "@/app/providers";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { KairosError } from "@/lib/kairos-client";

export type ProcessAction = "kill" | "pause" | "resume" | "checkpoint";

export const canTransition = (state: string | undefined, next: string) => (ALLOWED_TRANSITIONS[state ?? ""] ?? []).includes(next);

/** Which controls a process offers, from the contract's legal state transitions. */
export function availableActions(p: AgentProcess): ProcessAction[] {
  const out: ProcessAction[] = [];
  if (canTransition(p.state, "PAUSED")) out.push("pause");
  if (p.state === "PAUSED" && canTransition(p.state, "RUNNING")) out.push("resume");
  if (canTransition(p.state, "CHECKPOINTING")) out.push("checkpoint");
  if (canTransition(p.state, "TERMINATED")) out.push("kill");
  return out;
}

const DONE: Record<ProcessAction, string> = { kill: "killed", pause: "paused", resume: "resumed", checkpoint: "checkpointed" };

/** Pause/resume/checkpoint run at once; kill asks first (it's recorded and can't be undone). Render `dialog` once. */
export function useProcessActions() {
  const client = useClient();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState<AgentProcess | null>(null);
  const mutation = useMutation({
    mutationFn: ({ action, pid }: { action: ProcessAction; pid: number }): Promise<unknown> =>
      action === "kill"
        ? client.killProcess(pid)
        : action === "pause"
          ? client.pauseProcess(pid)
          : action === "resume"
            ? client.resumeProcess(pid)
            : client.checkpointProcess(pid),
    onSuccess: (_, { action, pid }) => toast(`PID ${pid} ${DONE[action]}`),
    onError: (e) => toast.error("Process control failed", { description: e instanceof KairosError ? e.message : String(e) }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
  const act = (action: ProcessAction, p: AgentProcess) => (action === "kill" ? setConfirm(p) : mutation.mutate({ action, pid: p.pid }));
  const dialog = (
    <AlertDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            Kill PID {confirm?.pid} ({confirm?.agent})?
          </AlertDialogTitle>
          <AlertDialogDescription>
            The process and its children are terminated. This is recorded in the audit journal and can&apos;t be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep running</AlertDialogCancel>
          <AlertDialogAction
            className="bg-st-failed text-white hover:bg-st-failed/90"
            onClick={() => confirm && mutation.mutate({ action: "kill", pid: confirm.pid })}
          >
            Kill
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
  return { act, dialog, pending: mutation.isPending };
}
