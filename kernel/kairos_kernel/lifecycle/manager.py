"""Agent lifecycle: spawn / run / retry / kill / pause / resume / checkpoint. One asyncio.Task per PID."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import (
    TERMINAL_STATES,
    AgentCreated,
    AgentManifest,
    AgentProcess,
    AgentResult,
    AgentResultStatus,
    AgentState,
    Approval,
    ApprovalStatus,
    AuditKind,
    Checkpoint,
    Decision,
    ErrorInfo,
    EventType,
    PolicyDecision,
    Principal,
    PrincipalKind,
    PrivacyLevel,
    ResourceQuota,
    Risk,
    SpawnRequest,
    SyscallRequest,
    Task,
    can_transition,
)
from kairos_contracts.schema.common import new_id, utcnow
from kairos_contracts.util import has_capability, path_matches

from ..context.agent_context import KernelAgentContext
from ..dynamic import generate, org_probe

if TYPE_CHECKING:
    from ..kernel import Kernel

log = logging.getLogger("kairos.kernel.lifecycle")

MAX_ATTEMPTS = 3          # first run + 2 retries (blueprint §49)
BACKEND_ERRORS = frozenset({"MODEL_UNAVAILABLE", "TIMEOUT"})  # may clear up on their own: retried after a backoff


# ---------------------------------------------------------------------------- scope helpers

def _base(glob: str) -> str:
    return re.sub(r"/?\*+$", "", glob.rstrip("/")) or "/org"


def _covers(outer: str, inner: str) -> bool:
    return path_matches(_base(inner), outer)


def mounts_as_globs(mounts: list[str]) -> list[str]:
    return [m.rstrip("/") + "/**" for m in mounts] or ["/org/**"]


def intersect_scopes(a: list[str], b: list[str]) -> list[str]:
    """Globs allowed by both sets (keeps the narrower glob of each overlapping pair)."""
    out: list[str] = []
    for x in a:
        for y in b:
            if _covers(y, x):
                out.append(x)
            elif _covers(x, y):
                out.append(y)
    return list(dict.fromkeys(out))


def parse_memory_mb(value: str) -> int:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(Gi|G|Mi|M)?\s*", value or "")
    if not m:
        return 1024
    n, unit = float(m.group(1)), (m.group(2) or "Mi")
    return int(n * 1024) if unit.startswith("G") else int(n)


# ---------------------------------------------------------------------------- lifecycle

class Lifecycle:
    def __init__(self, kernel: Kernel) -> None:
        self.k = kernel
        self.tasks: dict[int, asyncio.Task] = {}
        self.contexts: dict[int, KernelAgentContext] = {}
        self.manifests: dict[int, AgentManifest] = {}
        self.results: dict[int, asyncio.Future[AgentResult]] = {}
        self.suspending = False

    # ------------------------------------------------------------------ spawn
    async def spawn(self, req: SpawnRequest) -> int:
        k = self.k
        task = k.tasks.get(req.task_id)
        manifest = await k.services.require("agent_registry").get(req.agent)
        parent = k.procs.get(req.ppid) if req.ppid is not None else None
        if parent is not None:
            parent_manifest = self.manifests.get(parent.pid)
            if parent_manifest is None or req.agent not in parent_manifest.capabilities.agents:
                raise KairosError("CAPABILITY_DENIED", f"{parent.agent} may not spawn {req.agent}")
            await k.quotas.charge_child(parent.pid)
            # Every agent another agent creates is generated from its role template, for this task only.
            manifest = await self._generate(manifest, req, task, parent)

        caps = manifest.all_capabilities()
        if req.capabilities is not None:  # a request may only narrow (generated manifests are narrowed already)
            caps = [c for c in caps if has_capability(c, req.capabilities)]
        quota = ResourceQuota(
            max_tokens=manifest.resources.max_tokens_per_task, max_tool_calls=manifest.resources.max_tool_calls,
            max_wall_seconds=max(task.quota.max_wall_seconds, int(k.config.min_agent_wall_s)),
            max_children=task.quota.max_children if manifest.capabilities.agents else 0,
            cpu=manifest.resources.cpu, memory_mb=parse_memory_mb(manifest.resources.memory), gpu=manifest.resources.gpu)

        proc = k.procs.create(task_id=task.task_id, agent=manifest.name, agent_version=manifest.version, goal=req.goal,
                              ppid=req.ppid, owner=task.user_id, capabilities=caps, quota=quota,
                              memory_mounts=manifest.memory.mounts)
        pid = proc.pid
        principal = Principal(kind=PrincipalKind.AGENT, org_id=task.org_id, user_id=task.user_id, pid=pid,
                              agent=manifest.name, roles=list(task.metadata.get("roles", [])), capabilities=caps,
                              data_scopes=self._scopes(manifest, task, caps, req.scope),
                              max_privacy=PrivacyLevel(task.metadata.get("max_privacy", PrivacyLevel.INTERNAL.value)))
        ctx = KernelAgentContext(k, pid=pid, ppid=req.ppid, task_id=task.task_id, manifest=manifest,
                                 principal=principal, inputs=req.inputs)
        self.manifests[pid], self.contexts[pid] = manifest, ctx
        self.results[pid] = asyncio.get_running_loop().create_future()
        restore_state: dict | None = None
        if parent is None:
            await k.tasks.set_root(task.task_id, pid)
            restore_state = self._resume_state(task)

        await k.emit(EventType.PROCESS_SPAWNED, {"agent": manifest.name, "ppid": req.ppid}, task_id=task.task_id, pid=pid)
        if req.ppid is not None:  # the story's "created" step: agents a planner creates (the root planner is the task itself)
            await k.emit(EventType.AGENT_CREATED, AgentCreated(pid=pid, manifest_name=manifest.name,
                                                               template=manifest.template or manifest.name,
                                                               generated=manifest.generated).model_dump(mode="json"),
                         task_id=task.task_id, pid=pid)
        await k.journal(task.task_id, AuditKind.SPAWN, f"Spawned {manifest.name}", pid=pid,
                        actor=k.actor(req.ppid) if req.ppid else "kernel.lifecycle",
                        data={"agent": manifest.name, "ppid": req.ppid, "goal": req.goal, "capabilities": caps})
        for state in (AgentState.INITIALIZING, AgentState.READY, AgentState.RUNNING):
            await k.procs.transition(pid, state)
        if restore_state is not None:
            ctx.last_state = dict(restore_state)
            await k.emit(EventType.AGENT_LOG, {"level": "info", "message": "resuming from checkpoint after kernel restart",
                                              "data": {"checkpoint": task.metadata.get("resume_from")}},
                         task_id=task.task_id, pid=pid, source="kernel.lifecycle")
        self.tasks[pid] = asyncio.create_task(self._run(pid, manifest, ctx, restore_state), name=f"pid-{pid}")
        return pid

    async def _generate(self, template: AgentManifest, req: SpawnRequest, task: Task, parent: AgentProcess) -> AgentManifest:
        """The child's ephemeral manifest and policy: template ∩ request ∩ user permissions ∩ org policy (∩ the parent's
        bounds when the parent is generated too). What was narrowed, and why, goes into a `policy` audit entry."""
        k = self.k
        user = await k.permissions.resolve(task.user_id, task.org_id, list(task.metadata.get("roles", [])) or None)
        parent_manifest = self.manifests.get(parent.pid)
        inherit = parent_manifest is not None and parent_manifest.generated
        parent_ctx = self.contexts.get(parent.pid)
        permits = getattr(k.policy, "permits", None)
        probe = org_probe(template, task.org_id, task.user_id, list(task.metadata.get("roles", [])))
        g = generate(template, req, name=k.ephemeral.name_for(template.name, task.task_id), task_id=task.task_id, user=user,
                     org_refuses=(lambda c: permits(c, probe)) if permits else (lambda c: None),
                     parent=parent_manifest if inherit else None,
                     parent_caps=list(parent.capabilities) if inherit else None,
                     parent_scopes=list(parent_ctx.principal.data_scopes) if inherit and parent_ctx else None)
        k.ephemeral.add(task.task_id, g)
        if hasattr(k.policy, "register_generated"):
            k.policy.register_generated(g.manifest.name, g.policy)
        if g.dropped:
            summary = f"Narrowed {g.manifest.name}: " + "; ".join(f"{x} ({why})" for x, why in g.dropped.items())
            await k.journal(task.task_id, AuditKind.POLICY, summary[:500], pid=parent.pid, actor="kernel.lifecycle",
                            data={"agent": g.manifest.name, "template": template.name, "requested": g.requested,
                                  "granted": g.manifest.all_capabilities(), "scope": g.manifest.memory.mounts,
                                  "dropped": g.dropped, "user": user.user_id, "roles": user.roles, "why": req.why})
        return g.manifest

    def drop_generated(self, task_id: str) -> None:
        """The task ended: its generated manifests and policies go (memory, disk, policy overlay)."""
        names = self.k.ephemeral.remove_task(task_id)
        if names and hasattr(self.k.policy, "drop_generated"):
            self.k.policy.drop_generated(names)

    def _resume_state(self, task: Task) -> dict | None:
        cp_id = task.metadata.get("resume_from")
        if not cp_id:
            return None
        previous = task.metadata.get("previous_root_pid")
        cp = self.k.store.latest_checkpoint(previous) if previous else None
        meta = {k: v for k, v in task.metadata.items() if k != "resume_from"}
        self.k.tasks._save(self.k.tasks.get(task.task_id).model_copy(update={"metadata": meta}))
        return dict(cp.agent_state) if cp and cp.checkpoint_id == cp_id and cp.agent_state else None

    def _scopes(self, manifest: AgentManifest, task: Task, caps: list[str], requested: list[str] | None = None) -> list[str]:
        scopes = intersect_scopes(mounts_as_globs(manifest.memory.mounts), list(task.data_scope))
        if requested is not None:  # a spawn request may only narrow
            scopes = intersect_scopes(scopes, list(requested))
        knowledge_allow = getattr(self.k.policy, "knowledge_allow", None)
        if knowledge_allow is not None:
            probe = Principal(kind=PrincipalKind.AGENT, org_id=task.org_id, user_id=task.user_id, agent=manifest.name,
                              roles=list(task.metadata.get("roles", [])), capabilities=caps)
            allow = knowledge_allow(probe)
            if allow:
                scopes = intersect_scopes(scopes, allow)
        return scopes

    # ------------------------------------------------------------------ run
    async def _run(self, pid: int, manifest: AgentManifest, ctx: KernelAgentContext,
                   restore_state: dict | None = None) -> None:
        k = self.k
        runtime = k.services.require("agent_runtime")
        proc = k.procs.get(pid)
        goal = proc.goal
        # The wall-time quota holds while the agent is blocked too (a model call, a child, a backoff), not only when
        # it next calls ctx.*, which is all QuotaManager.check_wall can see.
        wall = proc.quota.max_wall_seconds
        deadline = asyncio.get_running_loop().time() + wall - (utcnow() - proc.created_at).total_seconds()
        result: AgentResult | None = None
        try:
            async with asyncio.timeout_at(deadline):
                result = await self._attempts(pid, manifest, ctx, goal, runtime, restore_state)
        except TimeoutError:
            error = ErrorInfo(code="QUOTA_EXCEEDED", message=f"pid {pid} exceeded {wall}s wall clock", retriable=False)
            await self.k.emit(EventType.AGENT_LOG, {"level": "warning", "message": f"{manifest.name} stopped: {error.message}"},
                              task_id=proc.task_id, pid=pid, source="kernel.lifecycle")
            result = self._failed(pid, manifest, error)
        except asyncio.CancelledError:
            if self.suspending:
                return  # kernel shutdown: leave the process unfinished; its task resumes on the next boot
            result = AgentResult(pid=pid, agent=manifest.name, status=AgentResultStatus.CANCELLED,
                                 summary=f"{manifest.name} was terminated")
            await self._finish(pid, result, AgentState.TERMINATED)
            return
        target = AgentState.COMPLETED if result.status == AgentResultStatus.COMPLETED else AgentState.FAILED
        if result.status == AgentResultStatus.CANCELLED:
            target = AgentState.TERMINATED
        await self._finish(pid, result, target)

    async def _attempts(self, pid: int, manifest: AgentManifest, ctx: KernelAgentContext, goal: str, runtime,
                        restore_state: dict | None) -> AgentResult:
        k = self.k
        attempt, budget = 0, MAX_ATTEMPTS
        while True:
            error: ErrorInfo | None = None
            try:
                state = restore_state if attempt == 0 else self._checkpoint_state(pid)
                if state:
                    result = await runtime.restore(manifest, goal, ctx, state)
                else:
                    result = await runtime.run(manifest, goal, ctx)
                # The runtime returns a handled KairosError as a FAILED result rather than raising it, so a model
                # outage reaches us here. Re-run only where that repeats nothing (see _rerun_is_safe).
                if not (result.status == AgentResultStatus.FAILED and result.error is not None
                        and result.error.code in BACKEND_ERRORS and self._rerun_is_safe(pid, manifest)):
                    return result
                if attempt + 1 >= budget:
                    return result
                error = result.error
            except KairosError as e:
                error = e.to_info()
                if e.code == "QUOTA_EXCEEDED":
                    return self._failed(pid, manifest, error)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("agent %s (pid %s) crashed", manifest.name, pid)
                error = ErrorInfo(code="INTERNAL", message=f"{type(e).__name__}: {e}", retriable=True)
            attempt += 1
            await self._to(pid, AgentState.FAILED, reason=error.message, error=error)
            k.procs.update(pid, attempt_count=attempt)
            if attempt >= budget:
                if not await self._escalate(pid, manifest, error, attempt):
                    return self._failed(pid, manifest, error)
                budget += 1  # a human granted one more attempt
            await self._to(pid, AgentState.RETRYING, reason=f"attempt {attempt + 1}/{budget}")
            if error.code in BACKEND_ERRORS and k.config.retry_backoff_s > 0:
                delay = k.config.retry_backoff_s * 3 ** (attempt - 1)
                await k.emit(EventType.AGENT_LOG, {"level": "warning", "message": f"{manifest.name}: {error.message}; "
                                                   f"retrying in {delay:g}s (attempt {attempt + 1}/{budget})"},
                             task_id=k.procs.get(pid).task_id, pid=pid, source="kernel.lifecycle")
                await asyncio.sleep(delay)
            await self._to(pid, AgentState.RUNNING)

    def _rerun_is_safe(self, pid: int, manifest: AgentManifest) -> bool:
        """A re-run starts the agent over: fine for one that only reads and thinks, not for one that has spawned
        children (their whole subtree would run again) or that holds approval-gated capabilities (a write could repeat)."""
        return not manifest.approval.required and self.k.procs.get(pid).usage.children_spawned == 0

    def _checkpoint_state(self, pid: int) -> dict | None:
        cp = self.k.store.latest_checkpoint(pid)
        return dict(cp.agent_state) if cp is not None and cp.agent_state else None

    async def _escalate(self, pid: int, manifest: AgentManifest, error: ErrorInfo, attempts: int) -> bool:
        """Blueprint §49 human escalation: ask the approval center whether to try once more. False = give up."""
        k = self.k
        timeout = k.config.escalation_timeout_s
        if timeout <= 0:
            return False
        proc = k.procs.get(pid)
        req = SyscallRequest(syscall_id=new_id("SC"), task_id=proc.task_id, pid=pid, capability="agent.retry",
                             tool="kernel", operation="retry", risk=Risk.HIGH, resource=f"pid/{pid}",
                             justification=f"{manifest.name} failed {attempts} times: {error.message}")
        decision = PolicyDecision(decision=Decision.REQUIRES_APPROVAL, policy="kernel.escalation",
                                  approval_id=new_id("APR"), matched_rules=["retries-exhausted"],
                                  reason=f"{manifest.name} failed {attempts} times; retry once more?")
        fut = await k.approvals.create(Approval(approval_id=decision.approval_id, task_id=proc.task_id, pid=pid,
                                                agent=manifest.name, syscall=req, decision=decision))
        k.procs.update(pid, waiting_on=f"approval:{decision.approval_id}")
        await k.tasks.on_process_change(proc.task_id)
        await k.journal(proc.task_id, AuditKind.APPROVAL, f"Escalated to a human after {attempts} failed attempts",
                        pid=pid, actor="kernel.lifecycle", refs=[decision.approval_id], data={"error": error.message})
        try:
            status = await asyncio.wait_for(asyncio.shield(fut), timeout)
        except TimeoutError:
            await k.approvals.expire(decision.approval_id, "escalation timed out")
            status = ApprovalStatus.EXPIRED
        except asyncio.CancelledError:
            await k.approvals.expire(decision.approval_id, "process terminated")
            raise
        finally:
            k.procs.update(pid, waiting_on=None)
            await k.tasks.on_process_change(proc.task_id)
        return status == ApprovalStatus.APPROVED

    @staticmethod
    def _failed(pid: int, manifest: AgentManifest, error: ErrorInfo) -> AgentResult:
        return AgentResult(pid=pid, agent=manifest.name, status=AgentResultStatus.FAILED,
                           summary=f"{manifest.name} failed: {error.message}", error=error)

    async def _to(self, pid: int, target: AgentState, **kw) -> None:
        """Transition, routing through RUNNING when the direct edge doesn't exist (e.g. PAUSED -> COMPLETED)."""
        state = self.k.procs.get(pid).state
        if state == target:
            return
        if not can_transition(state, target) and can_transition(state, AgentState.RUNNING):
            await self.k.procs.transition(pid, AgentState.RUNNING)
        await self.k.procs.transition(pid, target, **kw)

    async def _finish(self, pid: int, result: AgentResult, target: AgentState) -> None:
        k = self.k
        k.quotas.record_wall(pid)
        proc = k.procs.get(pid)
        result = result.model_copy(update={"pid": pid, "agent": proc.agent, "usage": proc.usage})
        k.store.put_result(result)
        try:
            await self._to(pid, target, reason=result.summary[:200], error=result.error)
        except KairosError:
            log.exception("could not move pid %s to %s", pid, target)
        await k.journal(proc.task_id, AuditKind.STATE, f"{proc.agent} finished: {result.status.value}", pid=pid,
                        actor=k.actor(pid), refs=result.evidence, data={"summary": result.summary[:500]})
        fut = self.results.get(pid)
        if fut is not None and not fut.done():
            fut.set_result(result)
        k.mailboxes.close(pid)
        self.contexts.pop(pid, None)
        if proc.ppid is None:
            await self._root_finished(proc.task_id, pid, result)

    async def _root_finished(self, task_id: str, root_pid: int, result: AgentResult) -> None:
        for p in self.k.procs.list(task_id):  # orphans die with their root
            if p.pid != root_pid and p.state not in TERMINAL_STATES:
                await self.kill(p.pid, reason="root finished")
        if result.status == AgentResultStatus.COMPLETED:
            await self.k.tasks.complete(task_id, result)
        elif result.status == AgentResultStatus.FAILED:
            await self.k.tasks.fail(task_id, result.summary, result.error)
        else:
            await self.k.tasks.cancel(task_id)

    # ------------------------------------------------------------------ control
    async def wait_result(self, pid: int, timeout: float | None = None) -> AgentResult:
        fut = self.results.get(pid)
        if fut is None:
            stored = self.k.store.result(pid)
            if stored is None:
                raise KairosError("PROCESS_NOT_FOUND", str(pid))
            return stored
        try:
            return await asyncio.wait_for(asyncio.shield(fut), timeout)
        except TimeoutError as e:
            raise KairosError("TIMEOUT", f"pid {pid} did not finish within {timeout}s") from e

    async def kill(self, pid: int, reason: str = "killed") -> None:
        # The target first: killed children first would let a parent waiting on them return normally, so an operator's
        # kill could end the task as completed (and the kill itself then failed on COMPLETED -> TERMINATED).
        self.k.procs.get(pid)  # PROCESS_NOT_FOUND for an unknown pid
        ctx = self.contexts.get(pid)
        if ctx is not None:
            ctx.request_cancel()
        task = self.tasks.get(pid)
        if task is not None and not task.done():
            if task is asyncio.current_task():
                raise KairosError("BAD_REQUEST", "a process cannot kill itself; return from run() instead")
            task.cancel()
            await asyncio.wait({task}, timeout=10)
        for child in self.k.procs.children(pid):
            if child.state not in TERMINAL_STATES:
                await self.kill(child.pid, reason)
        if (task is None or task.done()) and self.k.procs.get(pid).state not in TERMINAL_STATES:
            try:
                await self._to(pid, AgentState.TERMINATED, reason=reason)
            except KairosError as e:  # it reached a terminal state on its own meanwhile
                if e.code != "INVALID_STATE_TRANSITION" or self.k.procs.get(pid).state not in TERMINAL_STATES:
                    raise

    async def pause(self, pid: int) -> None:
        ctx = self.contexts.get(pid)
        proc = self.k.procs.get(pid)
        if ctx is None or proc.state not in (AgentState.RUNNING, AgentState.WAITING):
            raise KairosError("INVALID_STATE_TRANSITION", f"pid {pid} is {proc.state.value}; cannot pause")
        ctx.gate.clear()
        if proc.state == AgentState.RUNNING:
            await self.k.procs.transition(pid, AgentState.PAUSED, reason="paused by user")

    async def resume(self, pid: int) -> None:
        ctx = self.contexts.get(pid)
        proc = self.k.procs.get(pid)
        if ctx is not None:
            ctx.gate.set()
        if proc.state == AgentState.PAUSED:
            await self.k.procs.transition(pid, AgentState.RUNNING, reason="resumed by user")

    async def checkpoint(self, pid: int) -> Checkpoint:
        proc = self.k.procs.get(pid)
        ctx = self.contexts.get(pid)
        running = proc.state == AgentState.RUNNING
        if running:
            await self.k.procs.transition(pid, AgentState.CHECKPOINTING)
        ws = None
        if self.k.services.memory is not None:
            try:
                ws = await self.k.services.memory.rehydrate(pid)
            except Exception:
                log.exception("rehydrate failed for pid %s", pid)
        cp = Checkpoint(checkpoint_id=new_id("CKPT"), pid=pid, task_id=proc.task_id,
                        agent_state=dict(ctx.last_state) if ctx else {},
                        memory_refs=[i.ref for i in ws.items] if ws else [])
        self.k.store.put_checkpoint(cp)
        self.k.procs.update(pid, checkpoint_id=cp.checkpoint_id)
        await self.k.emit(EventType.PROCESS_CHECKPOINTED, {"checkpoint_id": cp.checkpoint_id}, task_id=proc.task_id, pid=pid)
        if running:
            await self.k.procs.transition(pid, AgentState.RUNNING)
        return cp

    async def suspend(self) -> None:
        """Kernel shutdown: cancel running agents WITHOUT finishing their processes/tasks (resumed on next boot)."""
        self.suspending = True
        live = [t for t in self.tasks.values() if not t.done()]
        for t in live:
            t.cancel()
        if live:
            await asyncio.wait(live, timeout=10)
