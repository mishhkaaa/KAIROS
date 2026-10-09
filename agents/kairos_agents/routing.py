"""Jev agent router, run locally: who should work on a goal, decided in one forward pass instead of a planning call.

The router asks its questions in Jev's typed format (TypeSafe's System One interface: a state plus choice, score and
noul questions, answered with calibrated probabilities, never with generated text). Jev itself is a hosted API, so the
answers come from Laya (convaiinnovations/laya, Apache 2.0), the open Jev-compatible decision model, on this machine's
CPU: no key, and the goal never leaves the machine. The planner asks what kind of goal this is (a question, a data
question or an investigation), how likely each role is to be needed, and whether the goal asks for a change or for the
public web. The answers are shown to the user as the run's routing decision.

Optional: without the `laya` package (`uv sync --group jev`), with KAIROS_JEV=off, or when a call fails or is not
confident, the planner falls back to its rules.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("kairos.agents.routing")

THRESHOLD = 0.5          # a role is spawned when Jev puts its probability at or above this
CONFIDENT = 0.55         # below this, the goal-type answer is not trusted and the rules decide
TIMEOUT_S = 60.0         # the first call loads the checkpoint

GOAL_TYPES = {
    "question": "asks for a fact, a summary or an explanation that documents can answer",
    "data": "needs numbers computed from the company database: totals, payments, invoices, vendors, SQL",
    "investigation": "investigates a problem: why something is late, over budget or failing, root causes and a plan",
}

# What each role does, phrased as the question Jev answers about the goal.
ROLE_QUESTIONS = {
    "finance-agent": "Does handling this need someone to look at budgets, costs, spending or money?",
    "engineering-agent": "Does handling this need someone to look at engineering work: delays, blockers, bugs or systems?",
    "research-agent": "Does handling this need someone to check vendors, suppliers, contracts or external partners?",
    "analyst": "Does handling this need someone to compare, analyse trends or weigh options across documents?",
    "data-engineer": "Does handling this need a query on the company database (payments, invoices, totals)?",
    "writer": "Does the request ask for a written note, memo, email or report to be drafted?",
    "web-researcher": "Does answering this need the public internet (current events, latest releases, outside facts)?",
    "action-agent": "Does the request ask to change something: update a tracker, file, create, assign or notify?",
}


@dataclass
class RouteDecision:
    goal_type: str | None
    goal_type_p: float
    scores: dict[str, float] = field(default_factory=dict)
    wants_change: float = 0.0
    wants_web: float = 0.0
    ms: float = 0.0
    model: str = "jev-local"

    def confident(self) -> bool:
        return self.goal_type is not None and self.goal_type_p >= CONFIDENT

    def wanted(self, roles: list[str] | tuple[str, ...]) -> list[str]:
        return [r for r in roles if self.scores.get(r, 0.0) >= THRESHOLD]


_lock = threading.Lock()
_router: Any = None
_broken = False


def enabled() -> bool:
    if _broken or os.getenv("KAIROS_JEV", "on").lower() in ("off", "0", "false", "no"):
        return False
    try:
        import importlib.util

        return importlib.util.find_spec("laya") is not None
    except (ImportError, ValueError):
        return False


def _load() -> Any:
    global _router
    with _lock:
        if _router is None:
            from laya import Router  # noqa: PLC0415 — optional dependency, imported on first use

            _router = Router()  # downloads the checkpoint on first use (kairosd warms it up at boot)
        return _router


def _prob(answer: Any, key: str = "noul") -> float:
    """A yes-probability or the chosen option's probability from one Laya answer, whatever shape it comes in."""
    if isinstance(answer, (int, float)):
        return float(answer)
    if not isinstance(answer, dict):
        return 0.0
    for k in (key, "probability", "confidence", "score"):
        v = answer.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _choice(answer: Any) -> tuple[str | None, float]:
    if not isinstance(answer, dict):
        return None, 0.0
    choice = answer.get("choice")
    probs = answer.get("probabilities") or answer.get("probs") or {}
    p = probs.get(choice) if isinstance(probs, dict) else None
    if not isinstance(p, (int, float)):
        p = _prob(answer, "confidence")
    return (str(choice) if choice else None), float(p or 0.0)


def questions(roles: list[str]) -> dict[str, dict[str, Any]]:
    q: dict[str, dict[str, Any]] = {
        "goal_type": {"type": "choice", "instructions": "What kind of request is this?", "criteria": GOAL_TYPES},
        "wants_change": {"type": "noul", "instructions": ROLE_QUESTIONS["action-agent"]},
        "wants_web": {"type": "noul", "instructions": ROLE_QUESTIONS["web-researcher"]},
    }
    for r in roles:
        if r in ROLE_QUESTIONS:
            q[f"role:{r}"] = {"type": "noul", "instructions": ROLE_QUESTIONS[r]}
    return q


def decide_sync(goal: str, roles: list[str]) -> RouteDecision:
    t0 = time.perf_counter()
    result = _load().predict({"request": goal}, questions(roles))
    answers = result.get("answers", {}) if isinstance(result, dict) else {}
    goal_type, goal_type_p = _choice(answers.get("goal_type"))
    scores = {k.split(":", 1)[1]: round(_prob(v), 3) for k, v in answers.items() if k.startswith("role:")}
    model = ((result.get("routing") or {}).get("model") if isinstance(result, dict) else None) or "laya"
    return RouteDecision(goal_type=goal_type if goal_type in GOAL_TYPES else None, goal_type_p=round(goal_type_p, 3),
                         scores=scores, wants_change=round(_prob(answers.get("wants_change")), 3),
                         wants_web=round(_prob(answers.get("wants_web")), 3),
                         ms=round((time.perf_counter() - t0) * 1000, 1), model=f"jev-local ({model})")


async def decide(goal: str, roles: list[str]) -> RouteDecision | None:
    """Jev's decision for the goal (run locally), or None when it is not installed, switched off or failed (the rules decide)."""
    global _broken
    if not enabled():
        return None
    try:
        return await asyncio.wait_for(asyncio.to_thread(decide_sync, goal, roles), TIMEOUT_S)
    except Exception as e:  # noqa: BLE001 — routing must never end a task: the rules take over
        log.warning("Jev routing unavailable, using the rules: %s", e)
        if isinstance(e, (ImportError, OSError)):
            _broken = True  # a missing package or checkpoint will not fix itself during this run
        return None
