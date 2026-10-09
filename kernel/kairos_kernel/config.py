"""Kernel-only tuning knobs (KAIROS_KERNEL_<FIELD> env vars). Cross-split settings live in kairos_contracts.wiring."""
from __future__ import annotations

import os
from dataclasses import dataclass, fields


@dataclass
class KernelConfig:
    max_concurrent_tasks: int = 2
    """Tasks whose agents run at the same time; more are queued (by priority)."""
    approval_timeout_s: float = 1800.0
    """How long a privileged syscall waits for a human before it is rejected (approval → EXPIRED). Any human decision
    in the same task restarts the clock of the task's other pending approvals."""
    escalation_timeout_s: float = 0.0
    """>0: after an agent exhausts its retries, ask a human (approval center) whether to retry once more. 0 = off."""
    retry_backoff_s: float = 5.0
    """Wait before retrying an agent that failed on a backend error (MODEL_UNAVAILABLE, TIMEOUT); tripled each time
    (5 s, then 15 s), so an Ollama restart is ridden out. Other failures retry at once. 0 = no wait."""
    min_agent_wall_s: float = 1800.0
    """Every agent's wall-time quota is at least this (a human approval can take a while), whatever the task's."""
    max_restarts: int = 2
    """How many kernel restarts an unfinished task survives (it is resumed from its root checkpoint on boot)."""
    policy_watch_interval_s: float = 2.0
    """Poll policies/ for changes and hot-reload them. 0 = off."""
    preemption: bool = True
    """A high-priority task pauses a running background task when all slots are busy."""
    schedules_file: str = ""
    """YAML file of scheduled agents (see scheduler/cron.py). Empty = no schedules."""

    @classmethod
    def from_env(cls) -> KernelConfig:
        kw = {}
        for f in fields(cls):
            raw = os.getenv(f"KAIROS_KERNEL_{f.name.upper()}")
            if raw is None:
                continue
            kw[f.name] = raw.lower() in ("1", "true", "yes", "on") if f.type in (bool, "bool") else type(getattr(cls, f.name))(raw)
        return cls(**kw)
