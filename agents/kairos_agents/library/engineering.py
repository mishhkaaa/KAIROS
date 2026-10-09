"""EngineeringAgent — identifies engineering blockers, schedule slips and technical root causes.

Owner: P3 — Agents & Models
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

from kairos_contracts.schema import AgentResult, AgentResultStatus, MessageType, Risk, SyscallRequest
from kairos_contracts.schema.common import new_id
from kairos_contracts.schema.ipc import A2AMessage

from kairos_agents.prompts import EngOut
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

log = logging.getLogger("kairos.agents.engineering")

_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}
_WEEKS = re.compile(r"\b(\d{1,2}|" + "|".join(_WORDS) + r")[\s-]+weeks?\b", re.I)
_SLIP = re.compile(r"\b(late|behind|slip\w*|delay\w*|overdue|schedule)\b", re.I)


def stated_slips(text: str) -> Counter[int]:
    """Week counts the text states in sentences about a slip or delay ("six weeks behind schedule", "a 6-week slip")."""
    found: Counter[int] = Counter()
    for sentence in re.split(r"(?<=[.!?\n])\s+", text):
        if _SLIP.search(sentence):
            for m in _WEEKS.finditer(sentence):
                v = m.group(1).lower()
                found[int(v) if v.isdigit() else _WORDS[v]] += 1
    return found


def grounded_slip(model_weeks: int, text: str) -> int:
    """The model's slip if the evidence states it; otherwise the slip the evidence states most often (qwen2.5:7b once
    reported 24 weeks where every document says six)."""
    stated = stated_slips(text)
    if not stated or model_weeks in stated:
        return model_weeks
    return stated.most_common(1)[0][0]

ENG_SYSTEM = """You are the Engineering Agent in KAIROS. Identify engineering blockers, schedule slips
and technical root causes based on project evidence.

Rules:
- Only cite /org paths that actually appeared in the evidence.
- Be specific about slip duration (in weeks) and each blocker's technical cause.
- Include Jira issues where referenced in the evidence.
"""


class EngineeringAgent(KairosAgent):
    """Analyzes engineering status and identifies technical root causes."""

    async def run(self, goal: str, ctx: Any) -> AgentResult:
        await ctx.log("engineering-agent: starting", data={"goal": goal[:200]})
        project = project_of(goal, ctx.inputs)
        issue_prefix = project.upper()
        await think(ctx, "search", f"Reading engineering status reports on Project {project} for blockers.")

        # Gather engineering evidence
        evidence = await gather_evidence(
            ctx,
            goal,
            scope=["/org/engineering", "/org/projects", "/org/systems", "/org/decisions"],
            top_k=8,
        )
        evidence_text = cite(evidence)
        await ctx.log(f"engineering-agent: gathered {len(evidence.hits)} evidence hits")
        await think_flagged(ctx, evidence)

        if ctx.cancelled():
            return self.result(ctx, "cancelled", status=AgentResultStatus.CANCELLED)

        # Optional: search Jira for project issues (jira.read is in capabilities)
        jira_context = ""
        if "jira.read" in (ctx.manifest.capabilities.tools or []):
            try:
                req = SyscallRequest(
                    syscall_id=new_id("SC"),
                    task_id=ctx.task_id,
                    pid=ctx.pid,
                    capability="jira.read",
                    tool="jira",
                    operation="search_issues",
                    arguments={"project": issue_prefix},
                    risk=Risk.LOW,
                    justification=f"Retrieve {issue_prefix} project issues for engineering analysis",
                    evidence=[h.path for h in evidence.hits[:3]],
                )
                result = await ctx.syscall(req)
                if result.tool_result and result.tool_result.output:
                    issues = result.tool_result.output.get("issues", [])
                    # key/status/summary only: the raw issue list costs the small local models most of their context
                    lines = [f"- {i.get('key', '?')} [{i.get('status', '?')}] {str(i.get('summary', ''))[:120]}"
                             for i in issues[:20] if isinstance(i, dict)]
                    jira_context = "\nJira issues:\n" + "\n".join(lines)
                    await ctx.log(f"engineering-agent: retrieved {len(issues)} Jira issues")
                    await think(ctx, "query", f"Checked {plural(len(issues), issue_prefix + ' issue')} in Jira.")
            except Exception as e:
                await ctx.log(f"engineering-agent: Jira search failed (non-fatal): {e}", level="warning")

        # Analyze with structured output
        user_prompt = (
            f"Task: {goal}\n\n"
            f"Evidence from knowledge base:\n{evidence_text}"
            f"{jira_context}\n\n"
            "Based ONLY on the evidence above, produce an engineering analysis as JSON:\n"
            "- slip_weeks: schedule slip in weeks (integer)\n"
            "- blockers: list of {issue, cause, evidence: [/org paths]}\n"
            "- summary: brief text summary\n"
            "Only cite /org paths that appear in the evidence above."
        )

        eng_out = await ask_json(ctx, ENG_SYSTEM, user_prompt, EngOut, max_tokens=1200)

        # Fallback
        if eng_out is None:
            await ctx.log("engineering-agent: LLM output unusable, using fallback", level="warning")
            eng_out = EngOut(
                slip_weeks=0,
                blockers=[],
                summary="Unable to extract engineering data from evidence. Manual review required.",
            )

        weeks = grounded_slip(eng_out.slip_weeks, f"{goal}\n{evidence_text}{jira_context}")
        if weeks != eng_out.slip_weeks:
            await ctx.log(f"engineering-agent: the evidence states a {weeks}-week slip, not {eng_out.slip_weeks}; using {weeks}",
                          level="warning")
            eng_out.slip_weeks = weeks
        await ctx.log(f"engineering-agent: analysis complete — {eng_out.slip_weeks} weeks slip, {len(eng_out.blockers)} blockers")
        await think(ctx, "analyze", f"Found {plural(len(eng_out.blockers), 'blocker')} behind a {eng_out.slip_weeks}-week slip.")

        retrieved = {h.path for h in evidence.hits}
        for d in eng_out.blockers:
            if isinstance(d, dict):
                d["evidence"] = await keep_retrieved(ctx, d.get("evidence", []), retrieved, "blockers")

        # Send evidence to parent
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
                        content=eng_out.summary[:500],
                        provenance=ev_paths,
                    )
                )
            except Exception as e:
                await ctx.log(f"engineering-agent: failed to send evidence to parent: {e}", level="warning")

        output = {
            "slip_weeks": eng_out.slip_weeks,
            "blockers": eng_out.blockers,
            "summary": eng_out.summary,
        }

        # Remember the finding, derived from the documents it rests on (they going stale invalidates it)
        cited = sorted({q for d in eng_out.blockers if isinstance(d, dict) for q in d.get("evidence", [])} & retrieved)
        await remember_finding(ctx, eng_out.summary or "engineering finding", cited or sorted(retrieved)[:5],
                               tags=["engineering", project.lower()])

        return AgentResult(
            pid=ctx.pid,
            agent=ctx.manifest.name,
            status=AgentResultStatus.COMPLETED,
            summary=eng_out.summary or f"Engineering analysis: {eng_out.slip_weeks} weeks slip, {len(eng_out.blockers)} blockers",
            output=output,
            evidence=[h.path for h in evidence.hits],
        )
