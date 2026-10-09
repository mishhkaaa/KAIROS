"""FinanceAgent — analyzes budget variance and financial drivers.

Owner: P3 — Agents & Models

Framework: nooa (listed in manifest), but we implement as a standard KairosAgent.
The Runtime falls back to running it as custom when the NOOA adapter is not installed.
"""
from __future__ import annotations

import logging
from typing import Any

from kairos_contracts.schema import AgentResult, AgentResultStatus, MessageType
from kairos_contracts.schema.common import new_id
from kairos_contracts.schema.ipc import A2AMessage

from kairos_agents.prompts import FinanceOut
from kairos_agents.sdk import (
    KairosAgent,
    ask_json,
    cite,
    gather_evidence,
    keep_retrieved,
    plural,
    project_of,
    remember_finding,
    think,
    think_flagged,
)

log = logging.getLogger("kairos.agents.finance")

FINANCE_SYSTEM = """You are the Finance Agent in KAIROS. Analyze budget variance and financial drivers.

Rules:
- Only cite /org paths that actually appeared in the evidence.
- Never fabricate numbers; if the evidence doesn't have a number, say "unknown".
- Be precise: give the overrun in lakh (₹100,000 units) and as a percentage.
- For each driver, identify the item, the delta (change), the cause, and the supporting /org paths.
- Respect the organization policies you are given: if a driver (for example emergency vendor spend) needs a sign-off
  under a policy, say so in the summary and cite the policy path.
"""

# What the finance agent checks its drivers against. Its memory derives from these too, so a policy change (for example
# security policy v2: CFO sign-off for emergency vendor spend) invalidates it.
POLICY_QUERY = "approval and sign-off rules for vendor contracts and emergency spend"


class FinanceAgent(KairosAgent):
    """Analyzes financial/budget information using knowledge base evidence."""

    async def run(self, goal: str, ctx: Any) -> AgentResult:
        await ctx.log("finance-agent: starting", data={"goal": goal[:200]})
        await think(ctx, "search", f"Searching finance records for Project {project_of(goal, ctx.inputs)}'s budget variance.")

        # Gather financial evidence
        evidence = await gather_evidence(
            ctx,
            goal,
            scope=["/org/finance", "/org/projects", "/org/decisions"],
            top_k=8,
        )
        policies = await gather_evidence(ctx, POLICY_QUERY, scope=["/org/policies"], top_k=3)
        evidence_text = cite(evidence)
        policy_text = cite(policies)
        await ctx.log(f"finance-agent: gathered {len(evidence.hits)} evidence hits and {len(policies.hits)} policies")
        await think_flagged(ctx, evidence, policies)

        if ctx.cancelled():
            return self.result(ctx, "cancelled", status=AgentResultStatus.CANCELLED)

        # Analyze with structured output
        user_prompt = (
            f"Task: {goal}\n\n"
            f"Evidence from knowledge base:\n{evidence_text}\n\n"
            f"Organization policies that apply:\n{policy_text}\n\n"
            "Based ONLY on the evidence above, produce a financial analysis as JSON:\n"
            "- overrun_lakh: total budget overrun in lakh (float)\n"
            "- overrun_pct: overrun as percentage (float)\n"
            "- drivers: list of {item, delta, cause, evidence: [/org paths]}\n"
            "- summary: brief text summary\n"
            "Only cite /org paths that appear in the evidence above."
        )

        finance_out = await ask_json(ctx, FINANCE_SYSTEM, user_prompt, FinanceOut, max_tokens=1200)

        # Fallback if LLM output is unusable
        if finance_out is None:
            await ctx.log("finance-agent: LLM output unusable, using fallback", level="warning")
            finance_out = FinanceOut(
                overrun_lakh=0.0,
                overrun_pct=0.0,
                drivers=[],
                summary="Unable to extract financial data from evidence. Manual review required.",
            )

        await ctx.log(f"finance-agent: analysis complete — overrun {finance_out.overrun_lakh}L ({finance_out.overrun_pct}%)")

        retrieved = {h.path for h in evidence.hits} | {h.path for h in policies.hits}
        for d in finance_out.drivers:
            if isinstance(d, dict):
                d["evidence"] = await keep_retrieved(ctx, d.get("evidence", []), retrieved, "drivers")
        # Counts only: the 7B's own overrun figures can be off (the planner's synthesis states the checked ones), and a
        # wrong number on the live story is worse than none.
        cited = sum(1 for d in finance_out.drivers if isinstance(d, dict) and d.get("evidence"))
        await think(ctx, "analyze", f"Found {plural(len(finance_out.drivers), 'cost driver')}, {cited} with cited evidence.")

        # Send evidence to parent if we have one
        if ctx.ppid:
            try:
                ev_paths = [h.path for h in evidence.hits]
                await ctx.send(
                    A2AMessage(
                        message_id=new_id("MSG"),
                        task_id=ctx.task_id,
                        sender_pid=ctx.pid,
                        receiver_pid=ctx.ppid,
                        sender=ctx.manifest.name,
                        receiver="",
                        type=MessageType.EVIDENCE,
                        content=finance_out.summary[:500],
                        provenance=ev_paths,
                    )
                )
            except Exception as e:
                await ctx.log(f"finance-agent: failed to send evidence to parent: {e}", level="warning")

        output = {
            "overrun_lakh": finance_out.overrun_lakh,
            "overrun_pct": finance_out.overrun_pct,
            "drivers": finance_out.drivers,
            "summary": finance_out.summary,
        }

        # Remember the finding, derived from the documents it rests on (they going stale invalidates it): what it cited,
        # every finance document it read (the model often uses a figure without citing its source, such as the cloud
        # bill behind the dual-run cost), and the policies it checked against.
        cited = sorted({q for d in finance_out.drivers if isinstance(d, dict) for q in d.get("evidence", [])} & retrieved)
        read = [h.path for h in evidence.hits if h.path.startswith("/org/finance/")]
        consulted = sorted(h.path for h in policies.hits)
        derived = list(dict.fromkeys([*(cited or sorted(retrieved)[:5]), *read, *consulted]))
        await remember_finding(ctx, finance_out.summary or "finance finding", derived,
                               tags=["finance", project_of(goal, ctx.inputs).lower()])

        return AgentResult(
            pid=ctx.pid,
            agent=ctx.manifest.name,
            status=AgentResultStatus.COMPLETED,
            summary=finance_out.summary or f"Financial analysis complete: {finance_out.overrun_lakh}L overrun ({finance_out.overrun_pct}%)",
            output=output,
            evidence=[h.path for h in evidence.hits] + [h.path for h in policies.hits],
        )
