"""Process table: PIDs, AgentProcess records, parent/child tree, and the enforced state machine."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    AgentProcess,
    AgentState,
    AuditKind,
    Capability,
    ErrorInfo,
    EventType,
    ProcessTreeNode,
    ResourceQuota,
    can_transition,
)
from kairos_contracts.schema.common import utcnow

if TYPE_CHECKING:
    from ..kernel import Kernel


class ProcessTable:
    def __init__(self, kernel: Kernel) -> None:
        self.k = kernel
        self._procs: dict[int, AgentProcess] = {}
        self._next_pid = kernel.store.max_pid() + 1  # PIDs start at 101 and are never reused

    def load(self, procs: list[AgentProcess]) -> None:
        for p in procs:
            self._procs[p.pid] = p
        self._next_pid = max([self._next_pid, *(p.pid + 1 for p in procs)])

    def create(self, *, task_id: str, agent: str, agent_version: str, goal: str, ppid: int | None, owner: str,
               capabilities: list[Capability], quota: ResourceQuota, memory_mounts: list[str]) -> AgentProcess:
        pid, self._next_pid = self._next_pid, self._next_pid + 1
        p = AgentProcess(pid=pid, ppid=ppid, task_id=task_id, owner=owner, agent=agent, agent_version=agent_version,
                         goal=goal, capabilities=capabilities, quota=quota, memory_mounts=memory_mounts)
        self._save(p)
        return p

    def _save(self, p: AgentProcess) -> AgentProcess:
        self._procs[p.pid] = p
        self.k.store.put_process(p)
        return p

    def find(self, pid: int | None) -> AgentProcess | None:
        return self._procs.get(pid) if pid is not None else None

    def get(self, pid: int) -> AgentProcess:
        p = self._procs.get(pid)
        if p is None:
            raise KairosError("PROCESS_NOT_FOUND", str(pid))
        return p

    def list(self, task_id: str | None = None) -> list[AgentProcess]:
        return [p for p in sorted(self._procs.values(), key=lambda p: p.pid) if task_id is None or p.task_id == task_id]

    def children(self, pid: int) -> list[AgentProcess]:
        return [p for p in self.list() if p.ppid == pid]

    def tree(self, task_id: str | None = None) -> list[ProcessTreeNode]:
        def node(p: AgentProcess) -> ProcessTreeNode:
            return ProcessTreeNode(pid=p.pid, agent=p.agent, state=p.state, children=[node(c) for c in self.children(p.pid)])

        return [node(p) for p in self.list(task_id) if p.ppid is None]

    def update(self, pid: int, **fields: Any) -> AgentProcess:
        return self._save(self.get(pid).model_copy(update={**fields, "updated_at": utcnow()}))

    async def transition(self, pid: int, new: AgentState, *, reason: str | None = None, waiting_on: str | None = None,
                         error: ErrorInfo | None = None) -> AgentProcess:
        p = self.get(pid)
        old = p.state
        if old == new:
            return p
        if not can_transition(old, new):
            raise KairosError("INVALID_STATE_TRANSITION", f"pid {pid}: {old.value} -> {new.value}")
        update: dict[str, Any] = {"state": new, "waiting_on": waiting_on if new == AgentState.WAITING else None}
        if error is not None:
            update["last_error"] = error
        p = self.update(pid, **update)
        payload = {"old": old.value, "new": new.value, "reason": reason}
        await self.k.emit(EventType.PROCESS_STATE_CHANGED, payload, task_id=p.task_id, pid=pid)
        await self.k.journal(p.task_id, AuditKind.STATE, f"{p.agent} {old.value} → {new.value}", pid=pid,
                             actor="kernel.process", data=payload)
        await self.k.tasks.on_process_change(p.task_id)
        return p
