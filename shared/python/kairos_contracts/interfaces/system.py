"""Interface PROVIDED BY P4 (Platform, Data & Demo), consumed by P1 (GET /system/resources, ai-top, scheduler).

The probe reports HOST resources only (CPU, RAM, GPU). P1 fills the kernel-side counters
(running_processes, queued_tasks, active_sandboxes, tokens_last_minute) with model_copy(update=...).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..schema import ResourceSnapshot


@runtime_checkable
class ResourceProbe(Protocol):
    async def snapshot(self) -> ResourceSnapshot:
        """Must return within ~500 ms and never raise: gpu=None when no NVIDIA GPU / nvidia-smi missing."""
