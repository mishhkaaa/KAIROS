"""KernelAgentContext — the real AgentContext (the agent ABI).

Every method: pause gate -> capability check -> quota -> service call -> event -> audit.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    A2AMessage,
    AgentManifest,
    AgentResult,
    AgentState,
    AgentThought,
    AuditKind,
    Checkpoint,
    EventType,
    EvidenceSet,
    KnowledgeListing,
    KnowledgeObject,
    MemoryQuery,
    MemoryRecord,
    ModelPolicy,
    ModelRequest,
    ModelResponse,
    NarrationPayload,
    Principal,
    PrivacyLevel,
    SearchQuery,
    SpawnRequest,
    SyscallRequest,
    SyscallResult,
)
from kairos_contracts.schema.common import new_id
from kairos_contracts.schema.events import NARRATION_EVENTS
from kairos_contracts.util import has_capability

if TYPE_CHECKING:
    from ..kernel import Kernel


class KernelAgentContext:
    def __init__(self, kernel: Kernel, *, pid: int, ppid: int | None, task_id: str, manifest: AgentManifest,
                 principal: Principal, inputs: dict[str, Any]) -> None:
        self.k = kernel
        self.pid, self.ppid, self.task_id = pid, ppid, task_id
        self.manifest, self.principal, self.inputs = manifest, principal, dict(inputs)
        self.gate = asyncio.Event()
        self.gate.set()
        self.last_state: dict[str, Any] = {}
        self._cancel_requested = False
        self._wait_depth = 0

    # ------------------------------------------------------------------ plumbing
    def request_cancel(self) -> None:
        self._cancel_requested = True
        self.gate.set()

    def cancelled(self) -> bool:
        return self._cancel_requested

    async def _enter(self, capability: str | None = None) -> None:
        if not self.gate.is_set():
            if self.k.procs.get(self.pid).state == AgentState.RUNNING:
                await self.k.procs.transition(self.pid, AgentState.PAUSED, reason="paused")
            await self.gate.wait()
            if self.k.procs.get(self.pid).state == AgentState.PAUSED:
                await self.k.procs.transition(self.pid, AgentState.RUNNING, reason="resumed")
        self.k.quotas.check_wall(self.pid)
        if capability is not None and not has_capability(capability, self.principal.capabilities):
            raise KairosError("CAPABILITY_DENIED", f"{self.manifest.name} lacks {capability}")

    @asynccontextmanager
    async def waiting(self, on: str) -> AsyncIterator[None]:
        """RUNNING -> WAITING(waiting_on=on) for the duration; nested/concurrent waits are reference-counted."""
        self._wait_depth += 1
        if self._wait_depth == 1 and self.k.procs.get(self.pid).state == AgentState.RUNNING:
            await self.k.procs.transition(self.pid, AgentState.WAITING, waiting_on=on)
        try:
            yield
        finally:
            self._wait_depth -= 1
            if self._wait_depth == 0 and self.k.procs.get(self.pid).state == AgentState.WAITING:
                await self.k.procs.transition(self.pid, AgentState.RUNNING)

    def _actor(self) -> str:
        return f"agent:{self.manifest.name}#{self.pid}"

    # ------------------------------------------------------------------ compute
    async def llm(self, request: ModelRequest) -> ModelResponse:
        await self._enter()
        self.k.quotas.check_tokens(self.pid)
        update: dict[str, Any] = {"task_id": self.task_id, "pid": self.pid}
        if self.manifest.runtime.model_policy == ModelPolicy.LOCAL_ONLY:
            update["privacy"] = PrivacyLevel.RESTRICTED
        if request.model_hint is None and self.manifest.runtime.model_hint:
            update["model_hint"] = self.manifest.runtime.model_hint
        resp = await self.k.services.require("models").generate(request.model_copy(update=update))
        await self.k.quotas.charge_tokens(self.pid, resp.usage.prompt, resp.usage.completion)
        self.k.procs.update(self.pid, model=resp.model)
        tokens = resp.usage.prompt + resp.usage.completion
        await self.k.emit(EventType.MODEL_INVOKED, {"model": resp.model, "provider": resp.provider, "local": resp.local,
                                                    "tokens": tokens}, task_id=self.task_id, pid=self.pid)
        await self.k.journal(self.task_id, AuditKind.MODEL, f"{resp.model} ({tokens} tokens)", pid=self.pid,
                             actor=self._actor(), data={"model": resp.model, "provider": resp.provider, "local": resp.local,
                                                        "task_class": request.task_class.value, "tokens": tokens})
        return resp

    # ------------------------------------------------------------------ knowledge
    async def search(self, query: SearchQuery) -> EvidenceSet:
        await self._enter("knowledge.search")
        ev = await self.k.services.require("knowledge").search(query, self.principal)  # P2 screens with the firewall
        paths = [h.path for h in ev.hits]
        flagged = [h.path for h in ev.hits if h.firewall_flags]
        await self.k.emit(EventType.KNOWLEDGE_RETRIEVED, {"query": query.text, "hits": len(ev.hits),
                                                         "filtered_by_policy": ev.filtered_by_policy, "paths": paths,
                                                         "flagged": flagged},
                          task_id=self.task_id, pid=self.pid)
        await self.k.journal(self.task_id, AuditKind.KNOWLEDGE,
                             f"Retrieved {len(paths)} objects ({ev.filtered_by_policy} filtered by policy)", pid=self.pid,
                             actor=self._actor(), refs=paths, data={"query": query.text, "flagged": flagged})
        if flagged:
            await self.log(f"Context firewall flagged {', '.join(flagged)} — treated as data", level="warning")
        return ev

    async def read(self, path: str) -> KnowledgeObject:
        await self._enter("knowledge.read")
        obj = await self.k.services.require("knowledge").read(path, self.principal)
        await self.k.journal(self.task_id, AuditKind.KNOWLEDGE, f"Read {path}", pid=self.pid, actor=self._actor(),
                             refs=[obj.path])
        return obj

    async def list(self, path: str) -> KnowledgeListing:
        await self._enter("knowledge.read")
        return await self.k.services.require("knowledge").list(path, self.principal)

    # ------------------------------------------------------------------ memory
    async def recall(self, query: MemoryQuery) -> list[MemoryRecord]:
        await self._enter()
        return await self.k.services.require("memory").recall(query.model_copy(update={"org_id": self.principal.org_id}))

    async def remember(self, record: MemoryRecord) -> str:
        await self._enter()
        update: dict[str, Any] = {"org_id": self.principal.org_id}
        if record.task_id is None:
            update["task_id"] = self.task_id
        memory_id = await self.k.services.require("memory").store(record.model_copy(update=update))
        await self.k.journal(self.task_id, AuditKind.MEMORY, f"Stored {record.kind.value} memory", pid=self.pid,
                             actor=self._actor(), refs=[memory_id, *record.derived_from])
        return memory_id

    # ------------------------------------------------------------------ processes
    async def spawn(self, agent: str, goal: str, inputs: dict[str, Any] | None = None, *,
                    capabilities: list[str] | None = None, scope: list[str] | None = None, why: str | None = None) -> int:
        await self._enter("agent.spawn")
        return await self.k.lifecycle.spawn(SpawnRequest(agent=agent, goal=goal, task_id=self.task_id, ppid=self.pid,
                                                         inputs=inputs or {}, capabilities=capabilities, scope=scope,
                                                         why=why))

    async def wait(self, pid: int, timeout: float | None = None) -> AgentResult:
        await self._enter()
        child = self.k.procs.get(pid)
        if child.ppid != self.pid:
            raise KairosError("PROCESS_NOT_FOUND", f"pid {pid} is not a child of {self.pid}")
        async with self.waiting(f"pid:{pid}"):
            return await self.k.lifecycle.wait_result(pid, timeout)

    # ------------------------------------------------------------------ IPC
    async def send(self, message: A2AMessage) -> None:
        await self._enter()
        receiver = self.k.procs.get(message.receiver_pid)
        if receiver.task_id != self.task_id:
            raise KairosError("CAPABILITY_DENIED", "agents may only message processes of the same task")
        msg = message.model_copy(update={"task_id": self.task_id, "sender_pid": self.pid, "sender": self.manifest.name,
                                         "receiver": receiver.agent})
        self.k.mailboxes.put(receiver.pid, msg)
        await self.k.emit(EventType.IPC_MESSAGE, {"message_id": msg.message_id, "sender": msg.sender,
                                                 "receiver": msg.receiver, "type": msg.type.value},
                          task_id=self.task_id, pid=self.pid, correlation_id=msg.message_id)
        await self.k.journal(self.task_id, AuditKind.IPC, f"{msg.type.value} → {receiver.agent}#{receiver.pid}",
                             pid=self.pid, actor=self._actor(), refs=[msg.message_id, *msg.provenance],
                             data={"content": msg.content[:300]})

    async def receive(self, timeout: float | None = None) -> A2AMessage | None:
        await self._enter()
        if self.k.mailboxes.pending(self.pid):
            return await self.k.mailboxes.get(self.pid, 0)
        async with self.waiting("ipc"):
            return await self.k.mailboxes.get(self.pid, timeout)

    # ------------------------------------------------------------------ world actions
    async def syscall(self, request: SyscallRequest) -> SyscallResult:
        await self._enter()
        return await self.k.syscalls.handle(request.model_copy(update={"task_id": self.task_id, "pid": self.pid}), self)

    # ------------------------------------------------------------------ artifacts
    async def put_artifact(self, name: str, data: bytes | str | dict, content_type: str = "application/json") -> str:
        await self._enter()
        raw = json.dumps(data).encode() if isinstance(data, dict) else data.encode() if isinstance(data, str) else data
        return await self.k.services.require("artifacts").put(self.task_id, name, raw, content_type)

    async def get_artifact(self, ref: str) -> bytes:
        await self._enter()
        if not ref.startswith(f"artifact://{self.task_id}/"):
            raise KairosError("CAPABILITY_DENIED", "agents may only read artifacts of their own task")
        return await self.k.services.require("artifacts").get(ref)

    # ------------------------------------------------------------------ observability
    async def log(self, message: str, level: str = "info", data: dict[str, Any] | None = None) -> None:
        await self._enter()  # a paused process must not keep producing output
        await self.k.emit(EventType.AGENT_LOG, {"level": level, "message": message, "data": data},
                          task_id=self.task_id, pid=self.pid, source=f"pid:{self.pid}")

    async def narrate(self, payload: NarrationPayload) -> None:
        """task.understood / agent.planned / agent.thought for the UI's story. The pid is the kernel's, never the agent's."""
        event_type = NARRATION_EVENTS.get(type(payload))
        if event_type is None:
            raise KairosError("BAD_REQUEST", f"agents may narrate only {', '.join(t.value for t in NARRATION_EVENTS.values())}")
        await self._enter()
        if isinstance(payload, AgentThought):
            payload = payload.model_copy(update={"pid": self.pid})
        await self.k.emit(event_type, payload.model_dump(mode="json"), task_id=self.task_id, pid=self.pid,
                          source=f"pid:{self.pid}")

    async def checkpoint(self, state: dict[str, Any]) -> str:
        await self._enter()
        self.last_state = dict(state)
        cp = Checkpoint(checkpoint_id=new_id("CKPT"), pid=self.pid, task_id=self.task_id, agent_state=self.last_state)
        self.k.store.put_checkpoint(cp)
        self.k.procs.update(self.pid, checkpoint_id=cp.checkpoint_id)
        await self.k.emit(EventType.PROCESS_CHECKPOINTED, {"checkpoint_id": cp.checkpoint_id},
                          task_id=self.task_id, pid=self.pid)
        return cp.checkpoint_id
