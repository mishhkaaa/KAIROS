import type { Task } from "@kairos/contracts";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { isActive } from "@/lib/events";
import { TaskStatusBadge, duration, formatTime } from "./status";

export function TaskRow({ t }: { t: Task }) {
  return (
    <Link
      href={`/tasks/${t.task_id}`}
      className="group flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg px-3 py-2.5 transition-colors hover:bg-surface-3 @xl:flex-nowrap"
    >
      <TaskStatusBadge status={t.status} className="justify-center @xl:w-[10.5rem]" />
      <div className="order-last min-w-0 basis-full @xl:order-none @xl:basis-auto @xl:flex-1">
        <p className="truncate text-sm">{t.goal}</p>
        <p className="font-mono text-xs text-text-2">
          {t.task_id} · {formatTime(t.created_at)}
          {t.priority ? ` · ${t.priority}` : ""}
        </p>
      </div>
      <span className="font-mono text-xs text-text-2" title="Duration">
        {duration(t.created_at, isActive(t.status) ? null : t.updated_at)}
      </span>
      <ArrowRight className="size-4 text-text-2 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
    </Link>
  );
}

export const byNewest = (a: Task, b: Task) => (b.created_at ?? "").localeCompare(a.created_at ?? "");
