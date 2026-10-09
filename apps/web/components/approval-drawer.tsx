"use client";

import { BellRing } from "lucide-react";
import { useCallback, useState } from "react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { drawerOpen, seenAfterClose } from "@/lib/approval-drawer-state";
import type { TaskView } from "@/lib/events";
import { ApprovalCard } from "./approval-card";

/** Opens by itself the first time each approval turns up pending, and via the banner afterwards. */
export function ApprovalDrawer({ view }: { view: TaskView }) {
  const pending = view.pendingApprovalIds.map((id) => view.approvals[id]).filter(Boolean);
  const pendingIds = pending.map((a) => a.approval_id);
  const [seen, setSeen] = useState<string[]>([]);
  const [manualOpen, setManualOpen] = useState(false);
  const [lingering, setLingering] = useState(false);
  const onResolved = useCallback(() => {
    setLingering(true);
    setTimeout(() => setLingering(false), 2000);
  }, []);
  const open = drawerOpen({ pending: pendingIds, seen, manualOpen, lingering });

  const [rendered, setRendered] = useState<string[]>([]);
  const onShown = useCallback((id: string) => setRendered((r) => (r.includes(id) ? r : [...r, id])), []);
  const close = () => {
    setSeen((s) => seenAfterClose(s, pendingIds, rendered));
    setManualOpen(false);
    setLingering(false);
  };

  return (
    <>
      {pending.length > 0 && (
        <button
          type="button"
          onClick={() => setManualOpen(true)}
          className="flex h-9 items-center gap-2 rounded-md border border-st-waiting bg-st-waiting/12 px-3 text-sm font-semibold text-st-waiting transition-colors hover:bg-st-waiting/20"
        >
          <BellRing className="size-4" aria-hidden />
          {pending.length === 1 ? "1 approval waiting" : `${pending.length} approvals waiting`}
        </button>
      )}
      <Sheet open={open} onOpenChange={(o) => (o ? setManualOpen(true) : close())}>
        <SheetContent
          side="right"
          className="gap-0 overflow-y-auto border-l border-line bg-background p-0 duration-220 sm:max-w-none"
          style={{ width: "min(720px, 100vw)", maxWidth: "100vw" }}
        >
          <SheetHeader className="border-b border-line px-5 py-4">
            <SheetTitle className="flex items-center gap-2 text-xl">
              <BellRing className="size-5 text-st-waiting" aria-hidden /> Approval required
            </SheetTitle>
            <SheetDescription className="text-sm text-text-2">
              Agent intent is not authorization. Policy sent this syscall to a human: check the evidence, then decide.
            </SheetDescription>
          </SheetHeader>
          <div className="space-y-4 p-5">
            {pending.map((a) => (
              <ApprovalCard key={a.approval_id} approval={a} flaggedPaths={view.flaggedPaths} onShown={onShown} onResolved={onResolved} />
            ))}
            {pending.length === 0 && <p className="text-sm text-text-2">All caught up. Nothing is waiting for approval.</p>}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
