"""The agents work for a project other than Apollo (the Zeus scenario), and Apollo's strings stay exactly as they were.
Fake context only: canned LLM replies, no Ollama."""
import asyncio

from kairos_agents.library.action import ActionAgent
from kairos_agents.library.engineering import EngineeringAgent
from kairos_agents.library.finance import FinanceAgent
from kairos_agents.library.planner import PlannerAgent
from kairos_agents.library.research import ResearchAgent
from kairos_agents.sdk import project_of, tracking_issue
from kairos_contracts.schema import AgentResultStatus

from .test_agents_units import ENG_REPLY, FINANCE_REPLY, _planner_ctx, ctx_for

ZEUS = ("Prepare a steering-committee briefing on Project Zeus budget risk for Q4: identify the risk drivers with "
        "evidence, update the tracker, and propose mitigations.")
APOLLO = ("Investigate why Project Apollo is over budget and six weeks behind schedule. "
          "Identify root causes, update the tracker, and prepare a recovery plan.")
# What qwen2.5:7b really plans: step goals that never name the project.
GENERIC_PLAN = {"rationale": "r", "steps": [
    {"step_id": "s1", "agent": "finance-agent", "goal": "Analyze the budget variance and identify the specific cost drivers."},
    {"step_id": "s2", "agent": "engineering-agent", "goal": "Identify the technical issues and schedule slips."},
    {"step_id": "s3", "agent": "research-agent", "goal": "Gather evidence from the documents for Project Zeus."},
    {"step_id": "s4", "agent": "action-agent", "goal": "Update the project tracker.", "depends_on": ["s1", "s2", "s3"]},
]}


# Specialists that come back with findings (what the canned children return when a test isn't about failures).
WITH_FINDINGS = {
    "finance-agent": ({"drivers": [{"item": "Cloud", "cause": "dual-run", "evidence": ["/org/finance/apollo-budget"]}]},
                      ["/org/finance/apollo-budget"]),
    "engineering-agent": ({"blockers": [{"issue": "APOLLO-12", "cause": "backfill failed",
                                         "evidence": ["/org/engineering/apollo-status"]}]}, ["/org/engineering/apollo-status"]),
    "research-agent": ({"findings": [], "urls_opened": ["http://vendor-docs/sdk-v5.html"]}, []),
}


def _spawned(ctx) -> list[tuple[str, str]]:
    return [(agent, goal) for agent, goal, _ in ctx.spawned.values()]


def test_project_of_and_tracking_issue():
    assert project_of(ZEUS) == "Zeus" and project_of(APOLLO) == "Apollo"
    assert project_of("Why is Apollo late?") == "Apollo", "no 'Project <Name>': the default"
    assert project_of("Update the project tracker.", {"project": "Zeus"}) == "Zeus", "what the planner passed wins"
    assert tracking_issue("Apollo") == "APOLLO-12" and tracking_issue("Zeus") == "ZEUS-11" and tracking_issue("Iris") == "IRIS-1"


def test_planner_plans_the_zeus_goal_and_anchors_generic_steps_to_the_project():
    ctx, inputs = _planner_ctx(GENERIC_PLAN, children=WITH_FINDINGS)
    result = asyncio.run(PlannerAgent().run(ZEUS, ctx))
    assert result.output["steps_executed"] == 4
    assert _spawned(ctx) == [
        ("finance-agent", "Project Zeus: Analyze the budget variance and identify the specific cost drivers."),
        ("engineering-agent", "Project Zeus: Identify the technical issues and schedule slips."),
        ("research-agent", "Gather evidence from the documents for Project Zeus."),  # already names it
        ("action-agent", "Project Zeus: Update the project tracker."),
    ]
    assert all(i["project"] == "Zeus" for _, i in inputs)


def test_planner_leaves_apollo_step_goals_untouched():
    ctx, inputs = _planner_ctx(GENERIC_PLAN, children=WITH_FINDINGS)
    asyncio.run(PlannerAgent().run(APOLLO, ctx))
    assert [g for _, g in _spawned(ctx)] == [s["goal"] for s in GENERIC_PLAN["steps"]]
    assert all(i["project"] == "Apollo" for _, i in inputs)


def test_fallback_plan_names_the_project_and_its_tracking_issue():
    unusable = {"rationale": "r", "steps": []}
    ctx, _ = _planner_ctx(unusable, children=WITH_FINDINGS)
    asyncio.run(PlannerAgent().run(ZEUS, ctx))
    goals = dict(_spawned(ctx))
    assert set(goals) == {"finance-agent", "engineering-agent", "research-agent", "action-agent"}
    assert "Zeus" in goals["finance-agent"] and "ZEUS-11" in goals["action-agent"]

    ctx, _ = _planner_ctx(unusable, children=WITH_FINDINGS)
    asyncio.run(PlannerAgent().run(APOLLO, ctx))
    assert _spawned(ctx) == [
        ("finance-agent", "Explain the Apollo budget variance with evidence"),
        ("engineering-agent", "Identify engineering causes of the schedule slip"),
        ("research-agent", "Collect vendor SDK context"),
        ("action-agent", "Record root causes on APOLLO-12"),
    ], "the Apollo fallback plan is unchanged"


def _action(project: str | None):
    inputs = {"upstream": {"f": {"drivers": [{"item": "cloud", "evidence": ["/org/finance/apollo-budget"]}]}}}
    if project:
        inputs["project"] = project
    ctx = ctx_for("action-agent", inputs=inputs)
    asyncio.run(ActionAgent().run("Update the project tracker.", ctx))
    return {req.capability: req for req, _ in ctx.syscalls}


def test_action_agent_writes_to_the_projects_own_tracking_issue():
    zeus = _action("Zeus")
    assert zeus["jira.write"].arguments["key"] == "ZEUS-11" and zeus["jira.write"].resource == "ZEUS-11"
    assert zeus["fs.write"].arguments["path"] == "reports/zeus-recovery.md"
    assert zeus["fs.write"].arguments["content"].startswith("# Zeus Recovery Plan\n")
    assert "APOLLO" not in str(zeus["jira.write"].arguments) and "Apollo" not in zeus["jira.write"].justification

    apollo = _action(None)
    assert apollo["jira.write"].arguments["key"] == "APOLLO-12" and apollo["jira.write"].resource == "APOLLO-12"
    assert apollo["jira.write"].justification.startswith("Update Apollo tracking issue with root causes: ")
    assert apollo["fs.write"].arguments["path"] == "reports/apollo-recovery.md"
    assert apollo["fs.write"].arguments["content"].startswith("# Apollo Recovery Plan\n")


def test_engineering_searches_the_projects_issues_and_tags_its_memory():
    for project, key in (("Zeus", "ZEUS"), (None, "APOLLO")):
        ctx = ctx_for("engineering-agent", {"engineering analysis": ENG_REPLY}, inputs={"project": project} if project else {})
        asyncio.run(EngineeringAgent().run("Identify the technical issues and schedule slips.", ctx))
        [jira] = [req for req, _ in ctx.syscalls if req.capability == "jira.read"]
        assert jira.arguments == {"project": key}
        assert jira.justification == f"Retrieve {key} project issues for engineering analysis"
        [mem] = ctx.memory.records.values()
        assert mem.tags == ["engineering", key.lower()]


def test_finance_tags_its_memory_with_the_project():
    ctx = ctx_for("finance-agent", {"financial analysis": FINANCE_REPLY}, inputs={"project": "Zeus"})
    asyncio.run(FinanceAgent().run("Analyze the budget variance.", ctx))
    [mem] = ctx.memory.records.values()
    assert mem.tags == ["finance", "zeus"]


def test_research_opens_the_projects_vendor_page():
    for project, url in (("Zeus", "http://vendor-docs/warehouse-pricing.html"), (None, "http://vendor-docs/sdk-v5.html")):
        ctx = ctx_for("research-agent", inputs={"project": project} if project else {})
        result = asyncio.run(ResearchAgent().run("Gather evidence.", ctx))
        [browser] = [req for req, _ in ctx.syscalls if req.capability == "browser.open"]
        assert browser.arguments == {"url": url}
        assert result.output["urls_opened"] == [url]
    assert browser.justification == "Retrieve vendor SDK v5 documentation for research", "Apollo's wording is unchanged"


def test_planner_warns_when_it_continues_without_a_failed_specialist():
    from kairos_contracts.schema import AgentResult, AgentResultStatus, ErrorInfo

    from .test_agents_units import manifest

    async def child(agent, goal, inputs):
        if agent == "engineering-agent":
            return AgentResult(pid=1, agent=agent, status=AgentResultStatus.FAILED, error=ErrorInfo(code="TIMEOUT", message="t"),
                               summary="engineering-agent failed: ollama qwen2.5:7b-instruct: no answer within 180s (ReadTimeout)")
        return AgentResult(pid=1, agent=agent, status=AgentResultStatus.COMPLETED, summary="ok")

    from kairos_contracts.testing.fakes import FakeAgentContext

    ctx = FakeAgentContext(manifest=manifest("planner-agent"), responses={"produce a plan": GENERIC_PLAN}, child_runner=child)
    asyncio.run(PlannerAgent().run(APOLLO, ctx))
    warnings = [m for level, m, _ in ctx.logs if level == "warning" and "continuing without" in m]
    assert warnings == ["planner: step s2 (engineering-agent) failed: engineering-agent failed: ollama qwen2.5:7b-instruct: "
                        "no answer within 180s (ReadTimeout); continuing without its findings"]
    assert not any("s1 (finance-agent) completed" in m for level, m, _ in ctx.logs if level == "warning")


def _plan_text(ctx) -> str:
    [ref] = [r for r in ctx.artifacts._data if r.endswith("/recovery-plan.md")]
    return ctx.artifacts._data[ref].decode()


def _with(**replace):
    """WITH_FINDINGS, with some specialists' results replaced by AgentResults."""
    from kairos_contracts.schema import AgentResult

    async def child(agent, goal, inputs):
        if agent in replace:
            return replace[agent](agent)
        out, ev = WITH_FINDINGS.get(agent, ({}, []))
        return AgentResult(pid=1, agent=agent, status=AgentResultStatus.COMPLETED, summary=f"{agent} done", output=out,
                           evidence=ev)
    return child


def _failed_child(agent):
    from kairos_contracts.schema import AgentResult, ErrorInfo

    reason = "ollama qwen2.5:7b-instruct: cannot reach Ollama at http://127.0.0.1:11434 (ConnectError)"
    return AgentResult(pid=1, agent=agent, status=AgentResultStatus.FAILED, summary=f"{agent} failed: {reason}",
                       error=ErrorInfo(code="MODEL_UNAVAILABLE", message=reason, retriable=True))


def _planner(child):
    from kairos_contracts.testing.fakes import FakeAgentContext

    from .test_agents_units import manifest

    return FakeAgentContext(manifest=manifest("planner-agent"), responses={"produce a plan": GENERIC_PLAN}, child_runner=child)


def test_a_failed_specialist_means_no_tracker_update_and_a_partial_plan():
    from kairos_contracts.schema import AgentResultStatus as S

    ctx = _planner(_with(**{"engineering-agent": _failed_child}))
    result = asyncio.run(PlannerAgent().run(APOLLO, ctx))
    assert "action-agent" not in [a for a, _ in _spawned(ctx)], "no action agent, so no jira.write can happen"
    assert ctx.syscalls == []
    assert ("warning", "planner: skipping tracker update: incomplete findings from engineering-agent") in \
        [(level, m) for level, m, _ in ctx.logs]
    plan = _plan_text(ctx)
    assert plan.splitlines()[:3] == ["# Recovery Plan", "", "**Partial: engineering-agent failed; tracker not updated.**"]
    assert "## Root Causes" in plan, "still written from what the other specialists found"
    assert result.status == S.FAILED and result.artifacts
    assert result.error.code == "MODEL_UNAVAILABLE"
    assert result.error.message.startswith("incomplete findings from engineering-agent: engineering-agent failed: ollama")
    assert result.summary == "Partial: engineering-agent failed; tracker not updated."


def test_a_specialist_with_no_usable_findings_counts_as_incomplete():
    from kairos_contracts.schema import AgentResult

    def empty(agent):
        return AgentResult(pid=1, agent=agent, status=AgentResultStatus.COMPLETED, output={"drivers": [], "summary": "Unable to "
                           "extract financial data from evidence. Manual review required."}, summary="nothing")

    ctx = _planner(_with(**{"finance-agent": empty, "research-agent": _failed_child}))
    result = asyncio.run(PlannerAgent().run(APOLLO, ctx))
    assert "action-agent" not in [a for a, _ in _spawned(ctx)]
    assert result.status == AgentResultStatus.FAILED and result.error.code == "MODEL_UNAVAILABLE"
    assert result.summary == "Partial: finance-agent, research-agent failed; tracker not updated."
    assert "finance-agent returned no usable findings" in result.error.message


def test_when_every_specialist_has_findings_the_action_step_runs_as_before():
    """The Apollo path, pinned: same spawns in the same order, the action step last with every specialist's output."""
    ctx, inputs = _planner_ctx(GENERIC_PLAN, children=WITH_FINDINGS)
    result = asyncio.run(PlannerAgent().run(APOLLO, ctx))
    assert _spawned(ctx) == [(s["agent"], s["goal"]) for s in GENERIC_PLAN["steps"]]
    action_inputs = inputs[-1][1]
    assert inputs[-1][0] == "action-agent" and set(action_inputs["upstream"]) == {"s1", "s2", "s3"}
    assert result.status == AgentResultStatus.COMPLETED
    assert "Partial" not in _plan_text(ctx) and not any("skipping tracker update" in m for _, m, _ in ctx.logs)


def test_a_specialist_the_model_forgot_is_added_back_before_the_action_step():
    """A real Apollo run's plan had no research step: nobody read the vendor email or opened the vendor docs (6/8)."""
    no_research = {"rationale": "r", "steps": [s for s in GENERIC_PLAN["steps"] if s["agent"] != "research-agent"]}
    ctx, inputs = _planner_ctx(no_research, children=WITH_FINDINGS)
    asyncio.run(PlannerAgent().run(APOLLO, ctx))
    assert [a for a, _ in _spawned(ctx)] == ["finance-agent", "engineering-agent", "research-agent", "action-agent"]
    assert ("research-agent", "Collect vendor SDK context") in _spawned(ctx)
    assert inputs[-1][0] == "action-agent" and set(inputs[-1][1]["upstream"]) == {"s1", "s2", "s3"}


def test_the_floor_adds_specialists_but_never_a_tracker_update_the_model_did_not_plan():
    only_finance = {"rationale": "r", "steps": [GENERIC_PLAN["steps"][0]]}
    ctx, _ = _planner_ctx(only_finance, children=WITH_FINDINGS)
    asyncio.run(PlannerAgent().run(APOLLO, ctx))
    assert [a for a, _ in _spawned(ctx)] == ["finance-agent", "engineering-agent", "research-agent"]
