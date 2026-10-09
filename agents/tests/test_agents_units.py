"""Unit tests for P3's agents on FakeAgentContext (fixtures in shared/fixtures/okf, canned LLM replies)."""
import asyncio

import yaml
from kairos_agents.library.engineering import EngineeringAgent
from kairos_agents.library.finance import FinanceAgent
from kairos_contracts.schema import AgentManifest, MemoryKind
from kairos_contracts.testing.fakes import FakeAgentContext
from kairos_contracts.wiring import REPO_ROOT


def manifest(name: str) -> AgentManifest:
    return AgentManifest.model_validate(yaml.safe_load((REPO_ROOT / "agents" / "manifests" / f"{name}.yaml").read_text()))


def ctx_for(name: str, responses: dict | None = None, **kw) -> FakeAgentContext:
    return FakeAgentContext(manifest=manifest(name), ppid=100, responses=responses or {}, **kw)


FINANCE_REPLY = {"overrun_lakh": 6.2, "overrun_pct": 31.0, "summary": "Apollo is 31% over budget",
                 "drivers": [{"item": "cloud", "delta": "+4.1L", "cause": "dual-run", "evidence": ["/org/finance/apollo-budget"]}]}
ENG_REPLY = {"slip_weeks": 3, "summary": "3 weeks slip",
             "blockers": [{"issue": "APOLLO-12", "cause": "backfill failed", "evidence": ["/org/engineering/apollo-status"]}]}


def test_finance_and_engineering_remember_their_findings():
    for agent, name, reply, key in ((FinanceAgent(), "finance-agent", FINANCE_REPLY, "financial analysis"),
                                    (EngineeringAgent(), "engineering-agent", ENG_REPLY, "engineering analysis")):
        ctx = ctx_for(name, {key: reply})
        asyncio.run(agent.run("Why is Apollo over budget and late?", ctx))
        [mem] = ctx.memory.records.values()
        assert mem.owner == name and mem.kind == MemoryKind.EPISODIC and mem.importance >= 0.5
        assert mem.content == reply["summary"]
        cited = [reply["drivers" if "drivers" in reply else "blockers"][0]["evidence"][0]]
        if name == "engineering-agent":
            assert mem.derived_from == cited
            continue
        # finance also rests on the policies it checked its drivers against (a policy change invalidates it)
        assert mem.derived_from[0] == cited[0] and mem.derived_from[-1] == "/org/policies/security"


def test_finance_finding_depends_on_every_finance_document_it_read():
    # The model often uses a figure without citing its source (the September cloud bill); an edit there must still
    # invalidate the finding, or the live invalidation demo depends on what the model chose to cite.
    cites_project_only = {**FINANCE_REPLY, "drivers": [{**FINANCE_REPLY["drivers"][0], "evidence": ["/org/projects/apollo"]}]}
    ctx = ctx_for("finance-agent", {"financial analysis": cites_project_only})
    result = asyncio.run(FinanceAgent().run("Why is Apollo over budget?", ctx))
    [mem] = ctx.memory.records.values()
    read = [p for p in result.evidence if p.startswith("/org/finance/")]
    assert read == ["/org/finance/apollo-budget"]  # read, never cited
    assert mem.derived_from[0] == "/org/projects/apollo" and set(read) <= set(mem.derived_from)
    assert not any(p.startswith("/org/engineering") for p in mem.derived_from)


def test_finance_checks_its_drivers_against_the_policies():
    ctx = ctx_for("finance-agent", {"financial analysis": FINANCE_REPLY})
    result = asyncio.run(FinanceAgent().run("Why is Apollo over budget?", ctx))
    assert "/org/policies/security" in result.evidence
    prompt = ctx.models.calls[-1].messages[-1].content
    assert "Organization policies that apply:" in prompt and "/org/policies/security" in prompt


def test_citations_that_were_not_retrieved_are_dropped():
    reply = {**FINANCE_REPLY, "drivers": [{"item": "cloud", "delta": "+4.1L", "cause": "dual-run",
                                           "evidence": ["/org/finance/apollo-budget", "/org/finance/made-up"]}]}
    ctx = ctx_for("finance-agent", {"financial analysis": reply})
    result = asyncio.run(FinanceAgent().run("Why is Apollo over budget?", ctx))
    assert result.output["drivers"][0]["evidence"] == ["/org/finance/apollo-budget"]
    assert any("dropped citation '/org/finance/made-up'" in m for level, m, _ in ctx.logs if level == "warning")


def test_research_keeps_only_findings_from_retrieved_sources():
    from kairos_agents.library.research import ResearchAgent

    reply = {"summary": "SDK v5 slipped", "urls_opened": ["http://evil.example/"],
             "findings": [{"claim": "v5 delayed", "source": "/org/inbox/vendor-email-2026-09-12"},
                          {"claim": "invented", "source": "/org/nowhere"}]}
    ctx = ctx_for("research-agent", {"synthesize your findings": reply})
    result = asyncio.run(ResearchAgent().run("vendor SDK v5 email", ctx))
    assert [f["source"] for f in result.output["findings"]] == ["/org/inbox/vendor-email-2026-09-12"]
    assert "http://evil.example/" not in result.output["urls_opened"]


def _planner_ctx(plan: dict, synthesis: dict | None = None, children: dict | None = None):
    from kairos_contracts.schema import AgentResult, AgentResultStatus

    spawned: list[tuple[str, dict]] = []

    async def child(agent, goal, inputs):
        spawned.append((agent, inputs))
        out, ev = (children or {}).get(agent, ({}, []))
        return AgentResult(pid=1, agent=agent, status=AgentResultStatus.COMPLETED, summary=f"{agent} done", output=out,
                           evidence=ev)

    responses = {"produce a plan": plan}
    if synthesis is not None:
        responses["synthesize into"] = synthesis
    return ctx_for("planner-agent", responses, child_runner=child), spawned


def test_planner_runs_exactly_one_action_agent_last():
    from kairos_agents.library.planner import PlannerAgent

    plan = {"rationale": "r", "steps": [
        {"step_id": "a1", "agent": "action-agent", "goal": "update APOLLO-12", "depends_on": ["f"]},
        {"step_id": "f", "agent": "finance-agent", "goal": "budget", "depends_on": ["e"]},
        {"step_id": "e", "agent": "engineering-agent", "goal": "slip", "depends_on": ["f", "nope"]},
        {"step_id": "a2", "agent": "action-agent", "goal": "update APOLLO-31", "depends_on": []},
        {"step_id": "x", "agent": "hr-agent", "goal": "?", "depends_on": []},
        {"step_id": "a3", "agent": "action-agent", "goal": "update APOLLO-40", "depends_on": ["a1"]},
    ]}
    ctx, spawned = _planner_ctx(plan, children=CHILDREN)  # specialists with findings: the action step runs
    asyncio.run(PlannerAgent().run("Investigate why Apollo is late and update the tracker.", ctx))
    agents = [a for a, _ in spawned]
    assert agents.count("action-agent") == 1 and agents[-1] == "action-agent", agents
    # the plan had no research step: the planner adds the default one back (the default plan's specialists are the floor)
    assert sorted(agents[:-1]) == ["engineering-agent", "finance-agent", "research-agent"]
    assert set(spawned[-1][1]["upstream"]) == {"f", "e", "s3"}, "the action step gets every specialist's output"


def test_action_agent_shows_the_root_cause_documents_to_the_approver():
    from kairos_agents.library.action import ActionAgent

    upstream = {"f": {"drivers": [{"item": "cloud", "evidence": ["/org/finance/apollo-budget", "/org/decisions/ADR-042"]}]},
                "e": {"blockers": [{"issue": "APOLLO-12", "evidence": ["/org/engineering/apollo-status"]}]},
                "r": {"findings": [{"claim": "v5 late", "source": "/org/inbox/vendor-email-2026-09-12"},
                                   {"claim": "docs", "source": "http://vendor-docs/sdk-v5.html"}]}}
    ctx = ctx_for("action-agent", inputs={"upstream": upstream})
    result = asyncio.run(ActionAgent().run("Record root causes on APOLLO-12", ctx))
    jira = next(req for req, _ in ctx.syscalls if req.capability == "jira.write")
    assert jira.evidence == ["/org/finance/apollo-budget", "/org/decisions/ADR-042", "/org/engineering/apollo-status",
                             "/org/inbox/vendor-email-2026-09-12"]
    assert "jira.write completed" in result.summary


PLAN = {"rationale": "r", "steps": [{"step_id": "f", "agent": "finance-agent", "goal": "budget"},
                                    {"step_id": "e", "agent": "engineering-agent", "goal": "slip"}]}
CHILDREN = {
    "finance-agent": ({"drivers": [{"item": "Cloud", "cause": "dual-run of old and new stacks",
                                    "evidence": ["/org/decisions/ADR-042"]}]}, ["/org/decisions/ADR-042"]),
    "engineering-agent": ({"blockers": [{"issue": "APOLLO-12", "cause": "backfill failed",
                                         "evidence": ["/org/engineering/apollo-status"]},
                                        {"issue": "APOLLO-31", "cause": "vendor SDK v5 certification",
                                         "evidence": ["/org/engineering/apollo-status"]}]},
                          ["/org/engineering/apollo-status"]),
    # research counts as having findings when it opened a page (the planner adds it back when a plan leaves it out)
    "research-agent": ({"findings": [], "urls_opened": ["http://vendor-docs/sdk-v5.html"]}, []),
}


def _plan_md(ctx) -> str:
    [ref] = [r for r in ctx.artifacts._data if r.endswith("/recovery-plan.md")]
    return ctx.artifacts._data[ref].decode()


def test_root_causes_come_from_the_specialists_when_the_model_cannot_synthesize():
    from kairos_agents.library.planner import PlannerAgent

    ctx, _ = _planner_ctx(PLAN, children=CHILDREN)  # no synthesis reply: the fake returns an empty skeleton, twice
    result = asyncio.run(PlannerAgent().run("Why is Apollo late and over budget?", ctx))
    causes = [rc["cause"] for rc in result.output["root_causes"]]
    assert causes == ["Cloud: dual-run of old and new stacks", "APOLLO-12: backfill failed",
                      "APOLLO-31: vendor SDK v5 certification"]
    md = _plan_md(ctx)
    assert "## Root Causes" in md and "APOLLO-31: vendor SDK v5 certification** — Evidence: /org/engineering/apollo-status" in md
    assert any("simpler schema" in m for _, m, _ in ctx.logs), "the simpler retry ran first"


def test_synthesized_root_causes_keep_only_retrieved_citations():
    from kairos_agents.library.planner import PlannerAgent

    synthesis = {"summary": "s", "recovery_plan": "1. fix", "root_causes": [
        {"cause": "dual-run cost", "evidence": ["/org/decisions/ADR-042", "/org/finance/invented"]},
        {"cause": "made up", "evidence": ["/org/nowhere"]}]}
    ctx, _ = _planner_ctx(PLAN, synthesis=synthesis, children=CHILDREN)
    result = asyncio.run(PlannerAgent().run("Why is Apollo late and over budget?", ctx))
    assert result.output["root_causes"] == [{"cause": "dual-run cost", "evidence": ["/org/decisions/ADR-042"]}]


APOLLO_GOAL = ("Investigate why Project Apollo is over budget and six weeks behind schedule. "
               "Identify root causes, update the tracker, and prepare a recovery plan.")


def test_root_causes_are_capped_at_three_distinct_causes():
    from kairos_agents.library.planner import PlannerAgent

    # The five causes qwen2.5:7b gave in a real run (T-b686e9e866): a restated symptom, two overlapping cost causes.
    causes = [
        {"cause": "Project Apollo is 31% over budget and six weeks late.",
         "evidence": ["/org/projects/apollo", "/org/finance/apollo-budget"]},
        {"cause": "The cloud cost overrun is 6.2 lakh (31%) due to running the old and new reconciliation pipelines "
                  "in parallel for 7 weeks.", "evidence": ["/org/finance/apollo-budget"]},
        {"cause": "The dual-run cloud cost, migration rework, and the PayCo emergency support contract are drivers of "
                  "the budget overrun.", "evidence": ["/org/meetings/steering-2026-09-18", "/org/finance/apollo-budget"]},
        {"cause": "The database migration (APOLLO-12) failed due to duplicate reconciliation IDs and required a full "
                  "backfill.", "evidence": ["/org/engineering/apollo-status-w37", "/org/engineering/apollo-status",
                                            "/org/engineering/postmortem-backfill-failure"]},
        {"cause": "The vendor SDK v5 upgrade (APOLLO-31) is blocked on PayCo, delaying the upgrade by three weeks.",
         "evidence": ["/org/engineering/apollo-status-w37"]},
    ]
    top = PlannerAgent._top_root_causes(APOLLO_GOAL, causes)
    assert [rc["cause"][:20] for rc in top] == ["The dual-run cloud c", "The database migrati", "The vendor SDK v5 up"]

    twins = [{"cause": "Backfill failed on duplicate reconciliation ids", "evidence": ["/org/engineering/apollo-status"]},
             {"cause": "The backfill failed on duplicate reconciliation ids (APOLLO-12)",
              "evidence": ["/org/engineering/apollo-status", "/org/engineering/postmortem-backfill-failure"]}]
    [merged] = PlannerAgent._top_root_causes(APOLLO_GOAL, twins)
    assert merged["cause"].endswith("(APOLLO-12)") and len(merged["evidence"]) == 2
    only_symptom = [{"cause": "Apollo is over budget and six weeks behind schedule", "evidence": ["/org/projects/apollo"]}]
    assert PlannerAgent._top_root_causes(APOLLO_GOAL, only_symptom) == only_symptom, "never left with nothing"


def test_a_broken_recovery_plan_and_heading_summary_fall_back_to_the_root_causes():
    from kairos_agents.library.planner import PlannerAgent

    # What qwen2.5:7b returned in real runs: a plan cut off at ":[" and a heading instead of a summary.
    synthesis = {"summary": "Recovery Plan for Project Apollo", "recovery_plan": ":[", "root_causes": [
        {"cause": "Dual-run of the old and new stacks doubled cloud cost", "evidence": ["/org/decisions/ADR-042"]},
        {"cause": "Backfill failed on duplicate reconciliation ids", "evidence": ["/org/engineering/apollo-status"]}]}
    ctx, _ = _planner_ctx(PLAN, synthesis=synthesis, children=CHILDREN)
    result = asyncio.run(PlannerAgent().run(APOLLO_GOAL, ctx))
    assert result.output["recovery_plan"] == ("1. Address: Dual-run of the old and new stacks doubled cloud cost\n"
                                              "2. Address: Backfill failed on duplicate reconciliation ids")
    assert result.summary.startswith("2 root causes: Dual-run of the old and new stacks")
    md = _plan_md(ctx)
    assert "## Recovery Steps\n\n1. Address: Dual-run" in md and ":[" not in md

    listed = {**synthesis, "summary": "Apollo overran because both reconciliation stacks ran for seven weeks.",
              "recovery_plan": ["Switch off the legacy pipeline", "Re-run the backfill with de-duplicated ids"]}
    ctx, _ = _planner_ctx(PLAN, synthesis=listed, children=CHILDREN)
    result = asyncio.run(PlannerAgent().run(APOLLO_GOAL, ctx))
    assert result.output["recovery_plan"] == "1. Switch off the legacy pipeline\n2. Re-run the backfill with de-duplicated ids"
    assert result.summary == listed["summary"]


def test_research_reads_the_vendor_email_as_untrusted_data_and_never_acts_on_it():
    from kairos_agents.library.research import VENDOR_DOCS_URL, ResearchAgent

    ctx = ctx_for("research-agent")
    result = asyncio.run(ResearchAgent().run("Gather evidence from available documents", ctx))  # a generic goal
    assert "/org/inbox/vendor-email-2026-09-12" in result.evidence
    prompt = ctx.models.calls[-1].messages[-1].content
    assert "(/org/inbox/vendor-email-2026-09-12) [UNTRUSTED: instruction_like" in prompt
    assert [(r.tool, r.operation, r.arguments) for r, _ in ctx.syscalls] == [("browser", "open", {"url": VENDOR_DOCS_URL})]


def test_engineering_slip_is_grounded_in_the_evidence():
    from kairos_agents.library.engineering import grounded_slip, stated_slips

    text = ("Apollo is six weeks behind schedule. The APOLLO-12 backfill slipped a 6-week window.\n"
            "Standups run for 24 weeks a year. The vendor SDK was delayed by three weeks.")
    assert stated_slips(text) == {6: 2, 3: 1}, "only weeks stated in sentences about a slip count"
    assert grounded_slip(24, text) == 6, "a number the evidence never gives for the slip is replaced"
    assert grounded_slip(3, text) == 3, "a slip the evidence does state is kept"
    assert grounded_slip(9, "No schedule information here.") == 9, "without evidence the model's number stands"


def test_nooa_object_agents_run_as_governed_processes():
    from kairos_agents.adapters.nooa import Agent, NooaRunner, skills, wrap
    from kairos_agents.library.finance import FinanceAgent
    from kairos_agents.runtime import Runtime
    from kairos_contracts.schema import AgentResultStatus, SearchQuery

    # finance-agent's manifest says framework: nooa; library agents already implement run(), so they pass through
    assert manifest("finance-agent").runtime.framework.value == "nooa"
    assert isinstance(Runtime()._load(manifest("finance-agent")), FinanceAgent)

    class VendorAgent(Agent):
        """Answers questions about vendor contracts."""

        async def contract_terms(self, ctx, vendor: str) -> dict:
            """Look up the contract terms for a vendor."""
            ev = await ctx.search(SearchQuery(text=f"{vendor} contract", scope=["/org/finance"], top_k=3))
            return {"summary": f"{vendor}: {len(ev.hits)} contract documents", "evidence": [h.path for h in ev.hits]}

        async def _private(self, ctx) -> dict:
            """Not a skill."""
            return {}

    assert list(skills(VendorAgent())) == ["contract_terms"]
    assert skills(VendorAgent())["contract_terms"]["params"] == {"vendor": "string"}, "ctx is supplied, not chosen"
    assert isinstance(wrap(VendorAgent), NooaRunner)

    ctx = ctx_for("finance-agent", {"choose the one skill": {"skill": "contract_terms", "arguments": {"vendor": "PayCo", "x": 1}}})
    result = asyncio.run(wrap(VendorAgent).run("What did we agree with PayCo?", ctx))
    assert result.status == AgentResultStatus.COMPLETED and result.summary.startswith("PayCo:")
    assert any("nooa: finance-agent.contract_terms" in m for _, m, _ in ctx.logs)
    prompt = ctx.models.calls[-1].messages[-1].content
    assert "contract_terms(vendor: string): Look up the contract terms for a vendor." in prompt

    bad = ctx_for("finance-agent", {"choose the one skill": {"skill": "delete_everything", "arguments": {}}})
    assert asyncio.run(wrap(VendorAgent).run("x", bad)).status == AgentResultStatus.FAILED



def test_a_focused_question_gets_only_its_specialist_and_writes_nothing():
    from kairos_agents.library.planner import PlannerAgent

    plan = {"rationale": "r", "steps": [
        {"step_id": "f", "agent": "finance-agent", "goal": "budget", "depends_on": []},
        {"step_id": "e", "agent": "engineering-agent", "goal": "slip", "depends_on": []},
        {"step_id": "r", "agent": "research-agent", "goal": "vendor", "depends_on": []},
        {"step_id": "a", "agent": "action-agent", "goal": "update APOLLO-12", "depends_on": ["f", "e", "r"]},
    ]}
    ctx, spawned = _planner_ctx(plan, children=CHILDREN)
    asyncio.run(PlannerAgent().run("Why is Apollo late?", ctx))
    assert [a for a, _ in spawned] == ["engineering-agent"]  # no finance, no research, no tracker write


def test_routing_questions_investigations_and_data():
    from kairos_agents.library.planner import is_investigation, relevant_specialists

    projects = {"apollo", "zeus", "atlas"}
    assert is_investigation("Investigate why Project Apollo is over budget and six weeks behind schedule.", projects)
    assert is_investigation("Why is Atlas late?", projects)
    assert not is_investigation("what projects has kamal worked on", projects)
    assert not is_investigation("What is our risk policy for vendors?", projects)
    assert relevant_specialists("Why is Apollo over budget?") == ["finance-agent"]
