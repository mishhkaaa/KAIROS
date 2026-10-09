"""TemplateAgent — runs a role template that has no library class of its own (analyst, data-engineer, writer).

Owner: P3 — Agents & Models

It searches its own scope (the generated manifest's mounts), asks the model for cited findings with the template's
system prompt, keeps only citations that were really retrieved, and returns {findings, summary}. Retrieved text goes
into the prompt as data (cite() marks flagged hits UNTRUSTED); thoughts are counts written here.
"""
from __future__ import annotations

import logging
from typing import Any

from kairos_contracts.schema import AgentResult, AgentResultStatus

from kairos_agents.prompts import TemplateOut
from kairos_agents.sdk import (
    KairosAgent,
    ask_json,
    cite,
    gather_evidence,
    keep_retrieved,
    plural,
    project_of,
    role_of,
    think,
    think_flagged,
)

log = logging.getLogger("kairos.agents.template")

DEFAULT_PROMPT = "You are a specialist agent in KAIROS. Answer the task from the evidence only, citing /org paths."


class TemplateAgent(KairosAgent):
    async def run(self, goal: str, ctx: Any) -> AgentResult:
        role = role_of(ctx)
        scope = [m.rstrip("/") for m in ctx.manifest.memory.mounts] or ["/org"]
        await think(ctx, "search", f"Searching {', '.join(scope[:3])} for Project {project_of(goal, ctx.inputs)}.")
        evidence = await gather_evidence(ctx, goal, scope=scope, top_k=8)
        await think_flagged(ctx, evidence)
        if ctx.cancelled():
            return self.result(ctx, "cancelled", status=AgentResultStatus.CANCELLED)

        out = await ask_json(ctx, ctx.manifest.system_prompt or DEFAULT_PROMPT,
                             f"Task: {goal}\n\nEvidence:\n{cite(evidence)}\n\n"
                             "Answer as JSON: findings (list of {claim, evidence: [/org paths from the evidence]}), "
                             "summary (two sentences).", TemplateOut, max_tokens=1200) or TemplateOut()
        retrieved = {h.path for h in evidence.hits}
        findings = []
        for f in out.findings:
            cited = await keep_retrieved(ctx, f.evidence, retrieved, "findings")
            if f.claim.strip() and cited:
                findings.append({"claim": f.claim.strip()[:300], "evidence": cited})
        await think(ctx, "analyze", f"Found {plural(len(findings), 'cited finding')}.")
        await ctx.log(f"{role}: {len(findings)} cited findings from {len(evidence.hits)} hits")
        return self.result(ctx, out.summary or f"{role}: {len(findings)} findings",
                           output={"findings": findings, "summary": out.summary},
                           evidence=sorted({p for f in findings for p in f["evidence"]}))
