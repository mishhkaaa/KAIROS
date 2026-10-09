"""Task scheduler: priority queues, admission control (slots + GPU memory) and preemption.

Preemption: when every slot is busy and a HIGH task is next, a running BACKGROUND task is paused (all its live
pids) and its slot is lent to the high task. Preempted tasks resume, oldest first, as soon as a slot frees up.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
from typing import TYPE_CHECKING

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    TERMINAL_STATES,
    TERMINAL_TASK_STATUSES,
    AgentState,
    AuditKind,
    ErrorInfo,
    Priority,
    SpawnRequest,
    Task,
    TaskStatus,
)

if TYPE_CHECKING:
    from ..kernel import Kernel

log = logging.getLogger("kairos.kernel.scheduler")

PRIORITY_RANK = {Priority.HIGH: 0, Priority.NORMAL: 1, Priority.BACKGROUND: 2}
ROOT_AGENT = "planner-agent"


class Scheduler:
    def __init__(self, kernel: Kernel, max_concurrent_tasks: int = 2, gpu_memory_limit: float = 0.95) -> None:
        self.k = kernel
        self.max_concurrent_tasks = max_concurrent_tasks
        self.gpu_memory_limit = gpu_memory_limit
        self.running: set[str] = set()
        self.preempted: list[str] = []
        self._seq = itertools.count()
        self._queue: asyncio.PriorityQueue | None = None
        self._freed: asyncio.Event | None = None
        self._loop_task: asyncio.Task | None = None
        self._pending: list[Task] = []  # enqueued before start()

    async def start(self) -> None:
        self._queue, self._freed = asyncio.PriorityQueue(), asyncio.Event()
        for t in self._pending:
            await self.enqueue(t)
        self._pending.clear()
        self._loop_task = asyncio.create_task(self._loop(), name="kairos-scheduler")

    async def stop(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
            await asyncio.gather(self._loop_task, return_exceptions=True)

    async def enqueue(self, task: Task) -> None:
        if self._queue is None:
            self._pending.append(task)
            return
        await self._queue.put((PRIORITY_RANK[task.priority], next(self._seq), task.task_id))

    def release(self, task_id: str) -> None:
        self.running.discard(task_id)
        if task_id in self.preempted:
            self.preempted.remove(task_id)
        if self.preempted and self._has_slot():
            self.k.spawn_background(self._resume_preempted())
        if self._freed is not None:
            self._freed.set()

    def _has_slot(self) -> bool:
        return len(self.running) < self.max_concurrent_tasks

    # ------------------------------------------------------------------ admission
    async def _admit(self, task: Task) -> None:
        while not self._has_slot() or not await self._gpu_ok():
            if not self._has_slot() and task.priority == Priority.HIGH and self.k.config.preemption:
                victim = self._victim()
                if victim is not None:
                    await self._preempt(victim, task.task_id)
                    continue
            self._freed.clear()
            try:
                await asyncio.wait_for(self._freed.wait(), timeout=1.0)
            except TimeoutError:
                pass

    def _victim(self) -> str | None:
        candidates = [tid for tid in self.running if (t := self.k.tasks.find(tid)) and t.priority == Priority.BACKGROUND
                      and t.status not in TERMINAL_TASK_STATUSES]
        return sorted(candidates)[0] if candidates else None

    async def _preempt(self, task_id: str, by: str) -> None:
        for p in self.k.procs.list(task_id):
            if p.state in (AgentState.RUNNING, AgentState.WAITING) and p.pid in self.k.lifecycle.contexts:
                try:
                    await self.k.lifecycle.pause(p.pid)
                except KairosError:
                    log.debug("pid %s could not be paused for preemption", p.pid)
        self.running.discard(task_id)
        self.preempted.append(task_id)
        await self.k.journal(task_id, AuditKind.TASK, f"Preempted by high-priority task {by}", actor="kernel.scheduler")

    async def _resume_preempted(self) -> None:
        while self.preempted and self._has_slot():
            task_id = self.preempted.pop(0)
            task = self.k.tasks.find(task_id)
            if task is None or task.status in TERMINAL_TASK_STATUSES:
                continue
            self.running.add(task_id)
            for p in self.k.procs.list(task_id):
                ctx = self.k.lifecycle.contexts.get(p.pid)
                if p.state not in TERMINAL_STATES and ctx is not None and not ctx.gate.is_set():
                    await self.k.lifecycle.resume(p.pid)
            await self.k.journal(task_id, AuditKind.TASK, "Resumed after preemption", actor="kernel.scheduler")

    async def _gpu_ok(self) -> bool:
        probe = self.k.services.probe
        if probe is None:
            return True
        try:
            gpu = (await probe.snapshot()).gpu
        except Exception:
            return True
        return gpu is None or gpu.memory_total_mb == 0 or gpu.memory_used_mb / gpu.memory_total_mb < self.gpu_memory_limit

    # ------------------------------------------------------------------ loop
    async def _loop(self) -> None:
        while True:
            _, _, task_id = await self._queue.get()
            task = self.k.tasks.find(task_id)
            if task is None or task.status != TaskStatus.QUEUED:
                continue  # cancelled while queued
            await self._admit(task)
            self.running.add(task_id)
            root = task.metadata.get("root_agent", ROOT_AGENT)
            try:
                await self.k.lifecycle.spawn(SpawnRequest(agent=root, goal=task.goal, task_id=task_id))
            except KairosError as e:
                await self.k.tasks.fail(task_id, f"could not start {root}: {e.message}", e.to_info())
            except Exception as e:  # never let one bad task kill the scheduler
                log.exception("starting task %s failed", task_id)
                await self.k.tasks.fail(task_id, str(e), ErrorInfo(code="INTERNAL", message=str(e)))
