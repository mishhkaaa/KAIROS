"""Per-pid IPC mailboxes (A2A messages)."""
from __future__ import annotations

import asyncio

from kairos_contracts.schema import A2AMessage


class Mailboxes:
    def __init__(self) -> None:
        self._boxes: dict[int, asyncio.Queue[A2AMessage]] = {}

    def _box(self, pid: int) -> asyncio.Queue[A2AMessage]:
        return self._boxes.setdefault(pid, asyncio.Queue())

    def put(self, pid: int, message: A2AMessage) -> None:
        self._box(pid).put_nowait(message)

    async def get(self, pid: int, timeout: float | None) -> A2AMessage | None:
        try:
            return await asyncio.wait_for(self._box(pid).get(), timeout)
        except TimeoutError:
            return None

    def pending(self, pid: int) -> int:
        return self._box(pid).qsize()

    def close(self, pid: int) -> None:
        self._boxes.pop(pid, None)
