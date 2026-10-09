"""The Kernel: composes every kernel subsystem on top of a ServiceBundle (fake or real services).

Boot/shutdown semantics (blueprint §5):
  * shutdown SUSPENDS: running agents are cancelled but their tasks stay unfinished in the state store;
  * boot RESUMES: each unfinished task is re-run from its root agent's last checkpoint (up to max_restarts),
    queued tasks are re-queued, pending approvals expire (the resumed run asks again).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from kairos_contracts.schema import (
    TERMINAL_STATES,
    TERMINAL_TASK_STATUSES,
    AgentState,
    ApprovalStatus,
    AuditEntry,
    AuditKind,
    ComponentHealth,
    ErrorInfo,
    Event,
    EventType,
    Task,
    TaskStatus,
)
from kairos_contracts.schema.common import new_id, utcnow
from kairos_contracts.wiring import ServiceBundle, Settings

from .approvals.queue import ApprovalQueue
from .config import KernelConfig
from .context.mailboxes import Mailboxes
from .dynamic import EphemeralAgents
from .lifecycle.manager import Lifecycle
from .permissions import RolePermissions
from .persistence.store import StateStore
from .policy.engine import template_of
from .process.table import ProcessTable
from .quota.manager import QuotaManager
from .scheduler.cron import CronRunner, load_schedules
from .scheduler.scheduler import Scheduler
from .syscalls.gateway import SyscallGateway
from .tasks.manager import TaskManager
from .transactions.manager import TransactionManager

log = logging.getLogger("kairos.kernel")

HISTORY_PER_TASK = 5000


class Kernel:
    def __init__(self, settings: Settings, services: ServiceBundle, config: KernelConfig | None = None) -> None:
        self.settings, self.services = settings, services
        self.config = config or KernelConfig.from_env()
        self.bus = services.require("event_bus")
        self.audit = services.require("audit")
        self.policy = services.require("policy")
        self.store = StateStore(settings.data_dir / "kernel.db")
        self.procs = ProcessTable(self)
        self.tasks = TaskManager(self)
        self.quotas = QuotaManager(self)
        self.mailboxes = Mailboxes()
        self.approvals = ApprovalQueue(self)
        self.transactions = TransactionManager(self)
        self.syscalls = SyscallGateway(self, approval_timeout=self.config.approval_timeout_s)
        self.lifecycle = Lifecycle(self)
        # Dynamic agents: the task user's permissions bound every agent a task creates (C's RBAC, or the role stub).
        self.permissions = services.permissions or RolePermissions.from_dir(settings.policies_dir)
        self.ephemeral = EphemeralAgents(settings.data_dir / "ephemeral")
        self.scheduler = Scheduler(self, max_concurrent_tasks=self.config.max_concurrent_tasks)
        self.history: dict[str, deque[Event]] = {}
        self.ready = False
        self.started_at = time.monotonic()
        self._background: set[asyncio.Task] = set()
        self._subscriptions: list[Any] = []
        self.cron: CronRunner | None = None

    # ------------------------------------------------------------------ boot / shutdown
    async def boot(self) -> None:
        if swept := self.ephemeral.sweep():  # generated agents never survive a restart; a resumed root regenerates them
            log.info("swept the generated manifests and policies of %d interrupted tasks", swept)
        self.tasks.load(self.store.tasks())
        self.procs.load(self.store.processes())
        self.approvals.load(self.store.approvals())
        await self._restore_history()
        requeue = self._recover()
        self._subscriptions = [self.bus.subscribe("*", self._record_history),
                               self.bus.subscribe(EventType.KNOWLEDGE_CHANGED.value, self._on_knowledge_changed)]
        await self.scheduler.start()
        for t in requeue:
            if t.metadata.get("resume_from") is not None or t.metadata.get("restarts"):
                await self.journal(t.task_id, AuditKind.TASK, f"Resumed after kernel restart #{t.metadata['restarts']}",
                                   actor="kernel", data={"checkpoint": t.metadata.get("resume_from")})
            await self.scheduler.enqueue(t)
        schedules = load_schedules(self.config.schedules_file)
        if schedules:
            self.cron = CronRunner(self, schedules)
            self.spawn_background(self.cron.run())
        if self.config.policy_watch_interval_s > 0 and hasattr(self.policy, "policies_dir"):
            self.spawn_background(self._watch_policies(self._policy_fingerprint()))  # snapshot now: no edit is missed
        self.ready = True
        await self.emit(EventType.SYSTEM_READY, {"components": [c.model_dump(mode="json") for c in self.components()]})
        log.info("kernel ready (%d tasks known, %d queued/resumed)", len(self.tasks.list()), len(requeue))

    def _recover(self) -> list[Task]:
        """Interrupted processes are retired; unfinished tasks are resumed from their root checkpoint or failed."""
        restart = ErrorInfo(code="INTERNAL", message="kernel restarted", retriable=True)
        for p in self.procs.list():
            if p.state not in TERMINAL_STATES and p.state != AgentState.FAILED:
                self.procs.update(p.pid, state=AgentState.TERMINATED, waiting_on=None, last_error=restart)
        for a in self.approvals.list(ApprovalStatus.PENDING):
            self.approvals._save(a.model_copy(update={"status": ApprovalStatus.EXPIRED, "resolved_at": utcnow(),
                                                      "resolved_by": "kernel", "comment": "kernel restarted"}))
        requeue: list[Task] = []
        for t in self.tasks.list():
            if t.status == TaskStatus.QUEUED:
                requeue.append(t)
            elif t.status not in TERMINAL_TASK_STATUSES:
                restarts = int(t.metadata.get("restarts", 0))
                if restarts >= self.config.max_restarts:
                    self.tasks._save(t.model_copy(update={"status": TaskStatus.FAILED, "updated_at": utcnow(),
                                                          "error": restart.model_copy(update={
                                                              "message": f"kernel restarted {restarts + 1} times"})}))
                    continue
                cp = self.store.latest_checkpoint(t.root_pid) if t.root_pid else None
                meta = {**t.metadata, "restarts": restarts + 1, "resume_from": cp.checkpoint_id if cp else None,
                        "previous_root_pid": t.root_pid}
                requeue.append(self.tasks._save(t.model_copy(update={"status": TaskStatus.QUEUED, "root_pid": None,
                                                                     "metadata": meta, "updated_at": utcnow()})))
        return requeue

    async def _restore_history(self) -> None:
        replay = getattr(self.bus, "replay", None)
        if replay is None:
            return
        for event in await replay():
            if event.task_id:
                self.history.setdefault(event.task_id, deque(maxlen=HISTORY_PER_TASK)).append(event)

    async def shutdown(self) -> None:
        """Suspend: stop the scheduler and running agents without finishing their tasks (they resume on boot)."""
        self.ready = False
        await self.scheduler.stop()
        await self.lifecycle.suspend()
        for sub in self._subscriptions:
            sub.unsubscribe()
        for t in list(self._background):
            t.cancel()
        if self._background:
            await asyncio.gather(*self._background, return_exceptions=True)
        close_tools = getattr(self.services.tools, "aclose", None)
        if close_tools is not None:
            await close_tools()
        mirror = getattr(self.bus, "mirror", None)
        if mirror is not None:
            await mirror.close()

    # ------------------------------------------------------------------ shared helpers
    async def emit(self, type_: EventType | str, payload: dict[str, Any] | None = None, *, task_id: str | None = None,
                   pid: int | None = None, correlation_id: str | None = None, source: str = "kernel") -> Event:
        task = self.tasks.find(task_id) if task_id else None
        event = Event(type=str(type_), source=source, org_id=task.org_id if task else None, task_id=task_id, pid=pid,
                      correlation_id=correlation_id, payload=payload or {})
        await self.bus.publish(event)
        return event

    async def journal(self, task_id: str, kind: AuditKind, summary: str, *, pid: int | None = None, actor: str = "kernel",
                      refs: list[str] | tuple[str, ...] = (), data: dict[str, Any] | None = None) -> None:
        try:
            await self.audit.append(AuditEntry(entry_id=new_id("AU"), task_id=task_id, pid=pid, actor=actor, kind=kind,
                                               summary=summary, refs=list(refs), data=data or {}))
        except Exception:  # auditing must never take the kernel down, but it must be loud
            log.exception("audit append failed (%s %s)", task_id, kind)

    def actor(self, pid: int | None) -> str:
        p = self.procs.find(pid)
        return f"agent:{p.agent}#{p.pid}" if p else "kernel"

    def spawn_background(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)

        def done(t: asyncio.Task) -> None:
            self._background.discard(t)
            if not t.cancelled() and t.exception() is not None:
                log.error("background task failed", exc_info=t.exception())

        task.add_done_callback(done)

    def components(self) -> list[ComponentHealth]:
        modes = self.services.modes or {}
        out = [ComponentHealth(component="kernel", ok=self.ready, mode="real")]
        for name in ("event_bus", "policy", "audit", "models", "knowledge", "firewall", "memory", "agent_registry",
                     "agent_runtime", "tools", "sandbox", "browser", "artifacts", "converters", "probe"):
            svc = getattr(self.services, name, None)
            mode = modes.get(name) or ("fake" if type(svc).__module__.endswith(".fakes") else "real")
            out.append(ComponentHealth(component=name, ok=svc is not None, mode=mode,
                                       detail="" if svc is not None else "not wired"))
        return out

    # ------------------------------------------------------------------ subscriptions & watchers
    async def _record_history(self, event: Event) -> None:
        if event.task_id:
            self.history.setdefault(event.task_id, deque(maxlen=HISTORY_PER_TASK)).append(event)

    async def _on_knowledge_changed(self, event: Event) -> None:
        memory = self.services.memory
        path = event.payload.get("path")
        if memory is None or not path:
            return
        report = await memory.invalidate(path)
        if not report.affected_agents:
            return
        for p in self.procs.list():
            if template_of(p.agent) in report.affected_agents and p.state not in TERMINAL_STATES:
                await self.emit(EventType.AGENT_LOG, {"level": "warning", "data": report.model_dump(mode="json"),
                                                     "message": f"{path} changed: {len(report.invalidated)} memories are stale"},
                                task_id=p.task_id, pid=p.pid, source="kernel.events")

    def _policy_fingerprint(self) -> tuple:
        directory = Path(self.policy.policies_dir)
        return tuple(sorted((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in directory.glob("*.yaml")))

    async def _watch_policies(self, last: tuple) -> None:
        while True:
            await asyncio.sleep(self.config.policy_watch_interval_s)
            try:
                current = self._policy_fingerprint()
            except OSError:
                continue
            if current != last:
                last = current
                try:
                    await self.policy.reload()
                except Exception as e:  # a broken edit keeps the last good policy set
                    log.error("policy reload rejected, keeping the previous policies: %s", e)
                    await self.emit(EventType.POLICY_UPDATED, {"error": str(e), "policies": None}, source="kernel.policy")
