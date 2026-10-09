"""ActionAgent — turns approved plans into governed tool actions via ctx.syscall.

Owner: P3 — Agents & Models

CRITICAL: This agent NEVER directly executes operations. ALL actions flow through:
  ActionAgent → ctx.syscall(req) → P1 capability/policy layer → approval → execution

Handles:
- jira.write: update issue status and add comment
- fs.write: write recovery plan report
- Graceful handling of: DENIED, REJECTED, ROLLED_BACK, FAILED outcomes
"""
from __future__ import annotations

import logging
from typing import Any

from kairos_contracts.schema import AgentResult, AgentResultStatus, Risk, SyscallStatus

from kairos_agents.sdk import KairosAgent, gather_evidence, project_of, propose_action, think, tracking_issue

log = logging.getLogger("kairos.agents.action")

ACTION_SYSTEM = """You are the Action Agent in KAIROS. You translate root causes into actionable
Jira updates and reports. You NEVER execute operations directly — all actions go through the
governed syscall interface."""


class ActionAgent(KairosAgent):
    """Executes governed actions based on upstream specialist findings."""

    async def run(self, goal: str, ctx: Any) -> AgentResult:
        await ctx.log("action-agent: starting", data={"goal": goal[:200]})

        # Get upstream findings from the planner
        upstream = ctx.inputs.get("upstream", {})
        syscall_results: list[dict[str, Any]] = []

        # The approver must see the documents behind the root causes: the specialists' citations (already checked
        # against what they retrieved). Only without upstream citations fall back to a search of our own.
        ev_paths = self._upstream_evidence(upstream)
        if not ev_paths:
            evidence = await gather_evidence(ctx, goal, scope=["/org/projects", "/org/engineering"], top_k=4)
            ev_paths = [h.path for h in evidence.hits]

        if ctx.cancelled():
            return self.result(ctx, "cancelled", status=AgentResultStatus.CANCELLED)

        # Build comment from upstream findings
        comment = self._build_comment(goal, upstream)
        project = project_of(goal, ctx.inputs)
        issue = tracking_issue(project)
        report_path = f"reports/{project.lower()}-recovery.md"

        # Action 1: Update the project's tracking issue in Jira (requires approval — jira.write)
        report_path_result = ""
        if "jira.write" in (ctx.manifest.capabilities.tools or []):
            try:
                req = propose_action(
                    ctx,
                    capability="jira.write",
                    tool="jira",
                    operation="update_issue",
                    arguments={
                        "key": issue,
                        "fields": {"status": "At Risk"},
                        "comment": comment,
                    },
                    justification=f"Update {project} tracking issue with root causes: {goal[:100]}",
                    evidence=ev_paths,
                    risk=Risk.MEDIUM,
                    resource=issue,
                )

                await ctx.log("action-agent: issuing jira.write syscall (may require approval)")
                await think(ctx, "act", f"Asking to record the root causes on {issue}; this needs a person's approval.")
                result = await ctx.syscall(req)

                syscall_results.append({
                    "capability": "jira.write",
                    "status": result.status.value,
                    "issue": issue,
                })

                status_msg = result.status.value
                await think(ctx, "act", f"The update to {issue} ended {status_msg.lower().replace('_', ' ')}.")
                await ctx.log(f"action-agent: jira.write syscall completed with status={status_msg}")

                if result.status == SyscallStatus.DENIED:
                    await ctx.log("action-agent: jira.write denied by policy", level="warning")
                elif result.status == SyscallStatus.REJECTED:
                    await ctx.log("action-agent: jira.write rejected by human approver", level="warning")
                elif result.status == SyscallStatus.ROLLED_BACK:
                    await ctx.log("action-agent: jira.write rolled back (verification failed)", level="warning")

            except Exception as e:
                await ctx.log(f"action-agent: jira.write syscall error (non-fatal): {e}", level="warning")
                syscall_results.append({"capability": "jira.write", "status": "error", "error": str(e)})

        if ctx.cancelled():
            return self.result(ctx, "cancelled after jira update", status=AgentResultStatus.CANCELLED)

        # Action 2: Write recovery plan report (fs.write)
        if "fs.write" in (ctx.manifest.capabilities.tools or []):
            try:
                report_content = self._build_report(project, goal, upstream, comment)
                req = propose_action(
                    ctx,
                    capability="fs.write",
                    tool="fs",
                    operation="write_file",
                    arguments={"path": report_path, "content": report_content},
                    justification="Write recovery plan report to workspace",
                    evidence=ev_paths,
                    risk=Risk.LOW,
                    resource=report_path,
                )

                await ctx.log(f"action-agent: writing report to {report_path}")
                result = await ctx.syscall(req)

                syscall_results.append({
                    "capability": "fs.write",
                    "status": result.status.value,
                    "path": report_path,
                })

                if result.status == SyscallStatus.COMPLETED:
                    report_path_result = report_path
                    await ctx.log(f"action-agent: report written to {report_path}")

            except Exception as e:
                await ctx.log(f"action-agent: fs.write syscall error (non-fatal): {e}", level="warning")
                syscall_results.append({"capability": "fs.write", "status": "error", "error": str(e)})

        # Determine overall status: say what happened to each action (the planner's synthesis reads this)
        summary = "Action agent: " + (", ".join(f"{r['capability']} {r['status']}" for r in syscall_results)
                                      or "no actions")
        if report_path_result:
            summary += f", report at {report_path_result}"

        return AgentResult(
            pid=ctx.pid,
            agent=ctx.manifest.name,
            status=AgentResultStatus.COMPLETED,
            summary=summary,
            output={
                "syscalls": syscall_results,
                "report_path": report_path_result,
                "comment": comment[:200],
            },
            evidence=ev_paths,
        )

    @staticmethod
    def _upstream_evidence(upstream: dict) -> list[str]:
        paths: list[str] = []
        for out in upstream.values():
            if not isinstance(out, dict):
                continue
            for item in [*out.get("drivers", []), *out.get("blockers", [])]:
                if isinstance(item, dict):
                    paths.extend(p for p in item.get("evidence", []) if isinstance(p, str))
            for f in out.get("findings", []):
                if isinstance(f, dict) and str(f.get("source", "")).startswith("/org"):
                    paths.append(f["source"])
        return list(dict.fromkeys(paths))

    def _build_comment(self, goal: str, upstream: dict) -> str:
        """Build a Jira comment from upstream specialist findings."""
        lines = [f"KAIROS automated analysis: {goal[:150]}", ""]

        for _, out in upstream.items():
            if not isinstance(out, dict):
                continue
            # Finance findings
            if "overrun_lakh" in out:
                lines.append(f"Financial: {out.get('overrun_lakh', 0)}L overrun ({out.get('overrun_pct', 0):.1f}%)")
                for d in out.get("drivers", [])[:3]:
                    lines.append(f"  - {d.get('item', '?')}: {d.get('cause', '?')}")
            # Engineering findings
            if "slip_weeks" in out:
                lines.append(f"Engineering: {out.get('slip_weeks', 0)} weeks slip")
                for b in out.get("blockers", [])[:3]:
                    lines.append(f"  - {b.get('issue', '?')}: {b.get('cause', '?')}")
            # Research findings
            if "findings" in out:
                lines.append(f"Research: {len(out.get('findings', []))} findings")

        return "\n".join(lines) or f"Root cause investigation complete for: {goal[:100]}"

    def _build_report(self, project: str, goal: str, upstream: dict, comment: str) -> str:
        """Build the recovery plan markdown report."""
        parts = [
            f"# {project} Recovery Plan\n",
            f"**Investigation Goal:** {goal}\n",
            "## Executive Summary\n",
            comment,
            "\n## Specialist Findings\n",
        ]
        for step_id, out in upstream.items():
            if isinstance(out, dict) and out:
                parts.append(f"\n### Step {step_id}\n")
                parts.append(str(out)[:500])

        parts.append("\n---\n*Generated by KAIROS ActionAgent*\n")
        return "\n".join(parts)
