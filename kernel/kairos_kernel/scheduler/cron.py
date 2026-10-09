"""Scheduled agents ("cron", blueprint OS table): run a goal every N seconds as a normal task.

Configured with a YAML file named by KAIROS_KERNEL_SCHEDULES_FILE:

    schedules:
      - name: nightly-budget-check
        every_s: 86400
        goal: "Check every active project's budget variance and flag anything over 10%"
        priority: background          # optional (default background)
        root_agent: planner-agent     # optional
        run_at_boot: false            # optional: fire once right after boot

Each firing publishes cron.triggered {job} and creates a task owned by user "scheduler". A job never overlaps
itself: if its previous task is still unfinished, that firing is skipped.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from kairos_contracts.schema import (
    TERMINAL_TASK_STATUSES,
    EventType,
    Principal,
    PrincipalKind,
    Priority,
    TaskCreate,
)
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..kernel import Kernel

log = logging.getLogger("kairos.kernel.cron")


class Schedule(BaseModel):
    name: str
    every_s: float = Field(gt=0)
    goal: str
    priority: Priority = Priority.BACKGROUND
    root_agent: str = "planner-agent"
    run_at_boot: bool = False
    org_id: str = "acme"


def load_schedules(path: str | Path) -> list[Schedule]:
    if not path or not Path(path).is_file():
        return []
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return [Schedule.model_validate(s) for s in raw.get("schedules", [])]


class CronRunner:
    def __init__(self, kernel: Kernel, schedules: list[Schedule], tick_s: float = 0.5) -> None:
        self.k, self.schedules, self.tick_s = kernel, schedules, tick_s
        now = time.monotonic()
        self.next_run = {s.name: now if s.run_at_boot else now + s.every_s for s in schedules}
        self.last_task: dict[str, str] = {}

    async def run(self) -> None:
        while True:
            now = time.monotonic()
            for s in self.schedules:
                if now >= self.next_run[s.name]:
                    self.next_run[s.name] = now + s.every_s
                    await self.fire(s)
            await asyncio.sleep(self.tick_s)

    async def fire(self, s: Schedule) -> str | None:
        previous = self.last_task.get(s.name)
        if previous and (t := self.k.tasks.find(previous)) and t.status not in TERMINAL_TASK_STATUSES:
            log.info("schedule %s skipped: previous run %s still active", s.name, previous)
            return None
        scheduler = Principal(kind=PrincipalKind.SYSTEM, org_id=s.org_id, user_id="scheduler", roles=["scheduler"])
        task = await self.k.tasks.create(TaskCreate(goal=s.goal, priority=s.priority,
                                                    metadata={"root_agent": s.root_agent, "schedule": s.name}), scheduler)
        self.last_task[s.name] = task.task_id
        await self.k.emit(EventType.CRON_TRIGGERED, {"job": s.name, "task_id": task.task_id}, task_id=task.task_id,
                          source="kernel.cron")
        return task.task_id
