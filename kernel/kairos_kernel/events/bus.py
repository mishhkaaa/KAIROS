"""In-process event bus with bounded per-subscriber queues, optionally mirrored to a Redis Stream.

The mirror makes the event history durable: after a restart the kernel replays it, so the UI's timeline for
an older task is still complete. Redis being down never breaks publishing (the mirror just logs and skips).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from fnmatch import fnmatch

from kairos_contracts.schema import Event

log = logging.getLogger("kairos.kernel.events")

Handler = Callable[[Event], Awaitable[None]]
STREAM_KEY = "kairos:events"


class _Subscription:
    def __init__(self, cancel: Callable[[], None]) -> None:
        self._cancel = cancel

    def unsubscribe(self) -> None:
        self._cancel()


class EventStream:
    """Registered on creation, so nothing published after `stream()` returns is lost. Call close() when done."""

    def __init__(self, bus: KernelEventBus, pattern: str, task_id: str | None, maxsize: int) -> None:
        self._bus = bus
        self.pattern, self.task_id = pattern, task_id
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        bus._streams.append(self)

    def matches(self, event: Event) -> bool:
        return fnmatch(event.type, self.pattern) and (self.task_id is None or event.task_id == self.task_id)

    def offer(self, event: Event) -> None:
        if self.queue.full():  # slow consumer (e.g. a stalled WebSocket): drop the oldest, keep the newest
            self.queue.get_nowait()
        self.queue.put_nowait(event)

    def __aiter__(self) -> EventStream:
        return self

    async def __anext__(self) -> Event:
        return await self.queue.get()

    def close(self) -> None:
        if self in self._bus._streams:
            self._bus._streams.remove(self)


class RedisMirror:
    """Appends every event to a capped Redis Stream and can read the history back."""

    def __init__(self, url: str, key: str = STREAM_KEY, maxlen: int = 100_000) -> None:
        self.url, self.key, self.maxlen = url, key, maxlen
        self._client = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._failures = 0

    def _redis(self):
        loop = asyncio.get_running_loop()
        if self._client is None or self._loop is not loop:  # asyncio clients are bound to the loop that created them
            import redis.asyncio as redis

            self._client = redis.from_url(self.url, socket_timeout=2, socket_connect_timeout=2)
            self._loop = loop
        return self._client

    async def append(self, event: Event) -> None:
        if self._failures >= 20:  # redis is gone; stop paying the timeout on every event
            return
        try:
            await self._redis().xadd(self.key, {"e": event.model_dump_json()}, maxlen=self.maxlen, approximate=True)
            self._failures = 0
        except Exception as e:
            self._failures += 1
            log.warning("redis mirror append failed (%s/20): %s", self._failures, e)

    async def history(self, count: int = 50_000) -> list[Event]:
        try:
            rows = await self._redis().xrevrange(self.key, count=count)
        except Exception as e:
            log.warning("redis history unavailable: %s", e)
            return []
        return [Event.model_validate_json(fields[b"e"]) for _, fields in reversed(rows)]

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class KernelEventBus:
    def __init__(self, stream_maxsize: int = 1000, mirror: RedisMirror | None = None) -> None:
        self._subs: list[tuple[str, Handler]] = []
        self._streams: list[EventStream] = []
        self._maxsize = stream_maxsize
        self.mirror = mirror

    async def publish(self, event: Event) -> None:
        for pattern, handler in list(self._subs):
            if fnmatch(event.type, pattern):
                try:
                    await handler(event)
                except Exception:  # a broken subscriber must never break the publisher
                    log.exception("event handler failed for %s", event.type)
        for stream in list(self._streams):
            if stream.matches(event):
                stream.offer(event)
        if self.mirror is not None:
            await self.mirror.append(event)

    def subscribe(self, pattern: str, handler: Handler) -> _Subscription:
        entry = (pattern, handler)
        self._subs.append(entry)
        return _Subscription(lambda: entry in self._subs and self._subs.remove(entry))

    def stream(self, pattern: str = "*", task_id: str | None = None) -> AsyncIterator[Event]:
        return EventStream(self, pattern, task_id, self._maxsize)

    async def replay(self) -> list[Event]:
        """Durable history (oldest first); empty without a mirror."""
        return await self.mirror.history() if self.mirror is not None else []


def redis_reachable(url: str) -> bool:
    try:
        import redis

        return bool(redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5).ping())
    except Exception:
        return False
