"""Task manager: create / cancel / resume tasks; derives TaskStatus from the process tree."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    TERMINAL_STATES,
    TERMINAL_TASK_STATUSES,
    AgentResult,
    AgentState,
    AuditKind,
    ErrorInfo,
    EventType,
    Principal,
    ResourceQuota,
    ResourceUsage,
    Task,
    TaskCreate,
    TaskResult,
    TaskStatus,
)
from kairos_contracts.schema.common import new_id, utcnow

if TYPE_CHECKING:
    from ..kernel import Kernel

log = logging.getLogger("kairos.kernel.tasks")


def sum_usage(usages: list[ResourceUsage]) -> ResourceUsage:
    total = ResourceUsage()
    for u in usages:
        total = ResourceUsage(**{f: getattr(total, f) + getattr(u, f) for f in ResourceUsage.model_fields})
    return total


class TaskManager:
    def __init__(self, kernel: Kernel) -> None:
        self.k = kernel
        self._tasks: dict[str, Task] = {}
        self._finishing: set[str] = set()  # terminal status saved, but its events/journal not yet written

    def load(self, tasks: list[Task]) -> None:
        for t in tasks:
            self._tasks[t.task_id] = t

    def find(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def get(self, task_id: str) -> Task:
        t = self._tasks.get(task_id)
        if t is None:
            raise KairosError("TASK_NOT_FOUND", task_id)
        return t

    def list(self, status: TaskStatus | None = None) -> list[Task]:
        return [t for t in sorted(self._tasks.values(), key=lambda t: t.created_at) if status is None or t.status == status]

    def _save(self, t: Task) -> Task:
        self._tasks[t.task_id] = t
        self.k.store.put_task(t)
        return t

    # ------------------------------------------------------------------ lifecycle of a task
    async def create(self, body: TaskCreate, user: Principal) -> Task:
        t = self._save(Task(
            task_id=new_id("T"), org_id=user.org_id, user_id=user.user_id, session_id=body.session_id, goal=body.goal,
            priority=body.priority, privacy=body.privacy, data_scope=body.data_scope, approval_policy=body.approval_policy,
            quota=body.quota or ResourceQuota(),
            metadata={**body.metadata, "max_privacy": user.max_privacy.value, "roles": list(user.roles)}))
        await self.k.emit(EventType.TASK_CREATED, {"goal": t.goal, "user_id": t.user_id}, task_id=t.task_id)
        await self.k.journal(t.task_id, AuditKind.TASK, "Task created", actor=f"user:{t.user_id}",
                             data={"goal": t.goal, "priority": t.priority.value})
        await self.k.scheduler.enqueue(t)
        return t

    def add_action(self, task_id: str, syscall_id: str) -> None:
        """Record a committed syscall on the task (persisted, so it survives restarts)."""
        t = self.get(task_id)
        self._save(t.model_copy(update={"metadata": {**t.metadata, "actions": [*t.metadata.get("actions", []), syscall_id]}}))

    async def set_root(self, task_id: str, pid: int) -> None:
        self._save(self.get(task_id).model_copy(update={"root_pid": pid, "updated_at": utcnow()}))

    async def _set_status(self, t: Task, status: TaskStatus, **extra) -> Task:
        old = t.status
        t = self._save(t.model_copy(update={"status": status, "updated_at": utcnow(), **extra}))
        if old != status:
            await self.k.emit(EventType.TASK_STATUS_CHANGED, {"old": old.value, "new": status.value}, task_id=t.task_id)
        if status in TERMINAL_TASK_STATUSES:
            self.k.lifecycle.drop_generated(t.task_id)
        return t

    def _derive(self, t: Task) -> TaskStatus:
        procs = self.k.procs.list(t.task_id)
        if not procs:
            return t.status
        live = [p for p in procs if p.state not in TERMINAL_STATES and p.state != AgentState.FAILED]
        waiting = [p for p in procs if p.state not in TERMINAL_STATES]  # FAILED pids can await an escalation
        if any(p.waiting_on and p.waiting_on.startswith("approval:") for p in waiting):
            return TaskStatus.WAITING_APPROVAL
        if live and all(p.state == AgentState.PAUSED for p in live):
            return TaskStatus.PAUSED
        root = self.k.procs.find(t.root_pid)
        if root is not None and root.state == AgentState.RUNNING and len(procs) == 1:
            return TaskStatus.PLANNING
        return TaskStatus.RUNNING

    async def on_process_change(self, task_id: str) -> None:
        t = self.find(task_id)
        if t is None or t.status in TERMINAL_TASK_STATUSES:
            return
        new = self._derive(t)
        if new != t.status:
            await self._set_status(t, new)

    async def complete(self, task_id: str, root_result: AgentResult) -> Task:
        t = self.get(task_id)
        if t.status in TERMINAL_TASK_STATUSES:
            return t
        procs = self.k.procs.list(task_id)
        results = [r for r in (self.k.store.result(p.pid) for p in procs) if r is not None]
        evidence = list(dict.fromkeys(e for r in results for e in r.evidence))
        artifacts = list(dict.fromkeys([*await self._artifacts(task_id), *root_result.artifacts]))
        result = TaskResult(summary=root_result.summary, artifacts=artifacts, evidence=evidence,
                            actions=list(t.metadata.get("actions", [])),
                            usage=sum_usage([p.usage for p in procs]))
        self._finishing.add(task_id)
        try:
            t = await self._set_status(t, TaskStatus.COMPLETED, result=result)
            await self.k.emit(EventType.TASK_COMPLETED, {"summary": result.summary}, task_id=task_id)
            await self.k.journal(task_id, AuditKind.TASK, "Task completed", actor="kernel.tasks",
                                 refs=result.artifacts, data={"actions": result.actions})
        finally:
            self._finishing.discard(task_id)
        self.k.scheduler.release(task_id)
        self.k.spawn_background(self._consolidate(task_id))
        return t

    async def fail(self, task_id: str, reason: str, error: ErrorInfo | None = None) -> Task:
        t = self.get(task_id)
        if t.status in TERMINAL_TASK_STATUSES:
            return t
        error = error or ErrorInfo(code="INTERNAL", message=reason)
        self._finishing.add(task_id)
        try:
            t = await self._set_status(t, TaskStatus.FAILED, error=error)
            await self.k.emit(EventType.TASK_FAILED, {"reason": reason, "error": error.model_dump(mode="json")},
                              task_id=task_id)
            await self.k.journal(task_id, AuditKind.TASK, f"Task failed: {reason}", actor="kernel.tasks")
        finally:
            self._finishing.discard(task_id)
        self.k.scheduler.release(task_id)
        return t

    async def cancel(self, task_id: str) -> Task:
        t = self.get(task_id)
        if t.status in TERMINAL_TASK_STATUSES:
            return t
        t = await self._set_status(t, TaskStatus.CANCELLED)
        await self.k.journal(task_id, AuditKind.TASK, "Task cancelled", actor="kernel.tasks")
        for p in self.k.procs.list(task_id):
            if p.ppid is None and p.state not in TERMINAL_STATES:
                await self.k.lifecycle.kill(p.pid, reason="task cancelled")
        self.k.scheduler.release(task_id)
        return self.get(task_id)

    async def resume(self, task_id: str) -> Task:
        self.get(task_id)
        for p in self.k.procs.list(task_id):
            if p.state == AgentState.PAUSED:
                await self.k.lifecycle.resume(p.pid)
        return self.get(task_id)

    # ------------------------------------------------------------------ helpers
    async def _artifacts(self, task_id: str) -> list[str]:
        store = self.k.services.artifacts
        if store is None:
            return []
        try:
            return await store.list(task_id)
        except Exception:
            log.exception("listing artifacts failed")
            return []

    async def _consolidate(self, task_id: str) -> None:
        if self.k.services.memory is not None:
            await self.k.services.memory.consolidate(task_id)

    def queued(self) -> int:
        return sum(1 for t in self._tasks.values() if t.status == TaskStatus.QUEUED)

    async def wait_terminal(self, task_id: str, timeout: float = 60) -> Task:
        """Test/CLI helper: poll until the task reaches a terminal status and its task.completed/failed is published.

        The status is saved before those events go out (subscribers read it); returning in between let a caller shut
        the kernel down mid-publish, and the terminal event was lost from the durable history."""
        async def poll() -> Task:
            while self.get(task_id).status not in TERMINAL_TASK_STATUSES or task_id in self._finishing:
                await asyncio.sleep(0.02)
            return self.get(task_id)

        return await asyncio.wait_for(poll(), timeout)
