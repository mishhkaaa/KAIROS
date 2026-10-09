"""Structured output schemas for P3 agents.

These Pydantic models define the JSON contracts between agents.
They live in prompts/ because they are tightly coupled to the prompt templates.

Owner: P3 — Agents & Models
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PlanStep(BaseModel):
    """A single step in the planner's execution plan."""

    step_id: str
    agent: str
    goal: str
    depends_on: list[str] = Field(default_factory=list)


class PlanOut(BaseModel):
    """The planner's structured output from its planning call."""

    rationale: str = ""
    steps: list[PlanStep] = Field(default_factory=list)


class RootCause(BaseModel):
    cause: str
    evidence: list[str] = Field(default_factory=list, description="/org paths from the findings")


class RootCausesOut(BaseModel):
    """The planner's simpler retry when the full synthesis fails (small local models)."""

    root_causes: list[RootCause] = Field(default_factory=list)


class SynthesisOut(BaseModel):
    """The planner's structured synthesis output."""

    root_causes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Each: {cause: str, evidence: [/org paths]}",
    )
    # A list, not one string: asked for "numbered steps" under a string schema, qwen2.5:7b starts a JSON array inside the
    # string and the grammar closes it straight away, leaving ":[" as the whole plan.
    recovery_plan: list[str] = Field(
        default_factory=list,
        description="Recovery steps, one per item, each referencing a root cause",
    )
    summary: str = ""

    @field_validator("recovery_plan", mode="before")
    @classmethod
    def _steps_from_text(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [re.sub(r"^\s*(?:\d+[.)]|[-*])\s*", "", line).strip() for line in v.splitlines() if line.strip()]
        return v


class FinanceOut(BaseModel):
    """Finance agent structured output."""

    overrun_lakh: float = 0.0
    overrun_pct: float = 0.0
    drivers: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Each: {item, delta, cause, evidence: [/org paths]}",
    )
    summary: str = ""


class EngOut(BaseModel):
    """Engineering agent structured output."""

    slip_weeks: int = 0
    blockers: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Each: {issue, cause, evidence: [/org paths]}",
    )
    summary: str = ""


class ResearchOut(BaseModel):
    """Research agent structured output."""

    findings: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Each: {claim, source}",
    )
    urls_opened: list[str] = Field(default_factory=list)
    summary: str = ""


class Finding(BaseModel):
    claim: str
    evidence: list[str] = Field(default_factory=list, description="/org paths the claim rests on")


class TemplateOut(BaseModel):
    """What a generic template agent (analyst, data-engineer, writer) answers."""

    findings: list[Finding] = Field(default_factory=list)
    summary: str = ""


class SqlOut(BaseModel):
    """The data engineer's query."""

    sql: str = ""
    explanation: str = ""


class AnswerOut(BaseModel):
    """The planner's direct answer to a question that needs no specialists."""

    answer: str = ""
    answered: bool = Field(True, description="false when the evidence does not contain the answer")
    sources: list[str] = Field(default_factory=list, description="/org paths and URLs the answer rests on")


class NoteOut(BaseModel):
    """The writer's draft."""

    subject: str = ""
    body: str = ""


__all__ = ["AnswerOut", "SqlOut", "NoteOut", "Finding", "TemplateOut", "PlanStep", "PlanOut", "RootCause", "RootCausesOut", "SynthesisOut", "FinanceOut", "EngOut", "ResearchOut"]
