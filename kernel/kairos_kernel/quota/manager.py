"""Resource quotas per pid: tokens, tool calls, children, wall clock. Publishes process.usage (throttled)."""
from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING

from kairos_contracts.errors import KairosError
from kairos_contracts.schema import EventType
from kairos_contracts.schema.common import utcnow

if TYPE_CHECKING:
    from ..kernel import Kernel


class QuotaManager:
    def __init__(self, kernel: Kernel, publish_interval: float = 1.0) -> None:
        self.k = kernel
        self.publish_interval = publish_interval
        self._last_publish: dict[int, float] = {}
        self._token_log: deque[tuple[float, int]] = deque()

    def check_tokens(self, pid: int) -> None:
        p = self.k.procs.get(pid)
        if p.usage.tokens_total >= p.quota.max_tokens:
            raise KairosError("QUOTA_EXCEEDED", f"pid {pid} used {p.usage.tokens_total}/{p.quota.max_tokens} tokens")

    def check_wall(self, pid: int) -> None:
        p = self.k.procs.get(pid)
        elapsed = (utcnow() - p.created_at).total_seconds()
        if elapsed > p.quota.max_wall_seconds:
            raise KairosError("QUOTA_EXCEEDED", f"pid {pid} exceeded {p.quota.max_wall_seconds}s wall clock")

    async def charge_tokens(self, pid: int, prompt: int, completion: int) -> None:
        p = self.k.procs.get(pid)
        usage = p.usage.model_copy(update={"tokens_prompt": p.usage.tokens_prompt + prompt,
                                           "tokens_completion": p.usage.tokens_completion + completion})
        self.k.procs.update(pid, usage=usage)
        now = time.monotonic()
        self._token_log.append((now, prompt + completion))
        await self._publish(pid)

    async def charge_tool_call(self, pid: int) -> None:
        p = self.k.procs.get(pid)
        if p.usage.tool_calls >= p.quota.max_tool_calls:
            raise KairosError("QUOTA_EXCEEDED", f"pid {pid} reached {p.quota.max_tool_calls} tool calls")
        self.k.procs.update(pid, usage=p.usage.model_copy(update={"tool_calls": p.usage.tool_calls + 1}))
        await self._publish(pid, force=True)

    async def charge_child(self, pid: int) -> None:
        p = self.k.procs.get(pid)
        if p.usage.children_spawned >= p.quota.max_children:
            raise KairosError("QUOTA_EXCEEDED", f"pid {pid} reached {p.quota.max_children} children")
        self.k.procs.update(pid, usage=p.usage.model_copy(update={"children_spawned": p.usage.children_spawned + 1}))

    def record_wall(self, pid: int) -> None:
        p = self.k.procs.get(pid)
        elapsed = (utcnow() - p.created_at).total_seconds()
        self.k.procs.update(pid, usage=p.usage.model_copy(update={"wall_seconds": round(elapsed, 3)}))

    def tokens_last_minute(self) -> int:
        cutoff = time.monotonic() - 60
        while self._token_log and self._token_log[0][0] < cutoff:
            self._token_log.popleft()
        return sum(n for _, n in self._token_log)

    async def _publish(self, pid: int, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_publish.get(pid, 0) < self.publish_interval:
            return
        self._last_publish[pid] = now
        p = self.k.procs.get(pid)
        await self.k.emit(EventType.PROCESS_USAGE, p.usage.model_dump(mode="json"), task_id=p.task_id, pid=pid)
