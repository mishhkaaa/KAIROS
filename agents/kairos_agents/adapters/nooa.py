"""NOOA adapter: object-oriented agents run as governed KAIROS processes. Owner: P2 (stretch).

NVIDIA's Object-Oriented Agents (NOOA) describe an agent as a Python object: public methods are its capabilities,
docstrings are the model-facing instructions, type annotations are the contract. KAIROS keeps doing what it does for
every agent: PID, capabilities, quotas, memory mounts, policy and audit. "NOOA describes the agent; KAIROS governs
the process" (blueprint §12).

The adapter doesn't depend on the `nooa` package. It works with any object in that shape, so a class that subclasses
`nooa.Agent` works the same way as `Agent` below:

    class VendorAgent(Agent):
        \"\"\"Answers questions about vendor contracts.\"\"\"

        async def contract_terms(self, ctx, vendor: str) -> dict:
            \"\"\"Look up the contract terms for a vendor.\"\"\"
            ...

When the runtime loads a manifest with `framework: nooa`, `wrap(cls)` returns something with `run(goal, ctx)`:
- a class that already implements `run` (every agent in the library) runs unchanged;
- an object agent gets a planner step: the model sees each skill's name, docstring and typed parameters, picks one
  and its arguments (JSON), and the adapter calls it with `ctx` as the only door to the outside world.
"""
from __future__ import annotations

import inspect
import json
import logging
from typing import Any, get_type_hints

from kairos_contracts.schema import AgentResult, AgentResultStatus
from pydantic import BaseModel, Field

from kairos_agents.sdk import KairosAgent, ask_json

log = logging.getLogger("kairos.agents.adapters.nooa")

_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


class Agent:
    """Base for NOOA-style agents: subclass, add async methods with docstrings. `ctx` is passed to every skill."""


class _Choice(BaseModel):
    skill: str = Field(description="name of the skill to call")
    arguments: dict[str, Any] = Field(default_factory=dict, description="its arguments, by parameter name")
    reason: str = ""


def skills(obj: Any) -> dict[str, dict[str, Any]]:
    """Public async methods with a docstring: name -> {doc, params: {name: json type}, fn}. `ctx` isn't a parameter
    the model fills in; the adapter supplies it."""
    out: dict[str, dict[str, Any]] = {}
    for name, fn in inspect.getmembers(obj, predicate=inspect.iscoroutinefunction):
        if name.startswith("_") or name in ("run", "snapshot", "restore") or not inspect.getdoc(fn):
            continue
        hints = get_type_hints(fn)
        params = {
            p: _JSON_TYPES.get(getattr(hints.get(p), "__origin__", None) or hints.get(p), "string")
            for p in inspect.signature(fn).parameters
            if p not in ("self", "ctx")
        }
        out[name] = {"doc": inspect.getdoc(fn), "params": params, "fn": fn}
    return out


class NooaRunner(KairosAgent):
    """Runs an object agent as a KAIROS process: one model call chooses the skill, the skill runs with ctx."""

    def __init__(self, obj: Any) -> None:
        self.obj = obj

    async def run(self, goal: str, ctx: Any) -> AgentResult:
        available = skills(self.obj)
        name = ctx.manifest.name
        if not available:
            return self.result(ctx, f"{name} exposes no skills (public async methods with a docstring)", status=AgentResultStatus.FAILED)
        catalog = "\n".join(f"- {s}({', '.join(f'{p}: {t}' for p, t in m['params'].items())}): {m['doc']}" for s, m in available.items())
        about = inspect.getdoc(type(self.obj)) or name
        choice = await ask_json(ctx, f"You are {name}. {about}\nChoose the one skill that best achieves the goal.",
                                f"Goal: {goal}\n\nSkills:\n{catalog}\n\nAnswer as JSON: skill, arguments, reason.", _Choice, max_tokens=400)
        if choice is None or choice.skill not in available:
            picked = choice.skill if choice else None
            await ctx.log(f"nooa: no usable skill choice ({picked!r}); available: {', '.join(available)}", level="warning")
            return self.result(ctx, f"{name} could not choose a skill for the goal", status=AgentResultStatus.FAILED)
        skill = available[choice.skill]
        args = {k: v for k, v in choice.arguments.items() if k in skill["params"]}
        await ctx.log(f"nooa: {name}.{choice.skill}({json.dumps(args)[:200]})", data={"reason": choice.reason[:200]})
        output = await skill["fn"](ctx, **args)
        summary = output.get("summary") if isinstance(output, dict) else None
        return AgentResult(pid=ctx.pid, agent=name, status=AgentResultStatus.COMPLETED,
                           summary=summary or f"{name}.{choice.skill} completed",
                           output=output if isinstance(output, dict) else {"result": output},
                           evidence=list(output.get("evidence", [])) if isinstance(output, dict) else [])


def wrap(cls: type) -> Any:
    """What the runtime calls for `framework: nooa`: an object with run(goal, ctx)."""
    obj = cls()
    if callable(getattr(obj, "run", None)) and not isinstance(obj, Agent):
        return obj  # already speaks the KAIROS agent ABI (every library agent does)
    return NooaRunner(obj)


__all__ = ["Agent", "NooaRunner", "skills", "wrap"]
