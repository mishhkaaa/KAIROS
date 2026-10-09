"""The thought-process story (contract 0.10.0) the agents tell through ctx.narrate. Fake context only, no Ollama."""
import asyncio

from kairos_agents.library.engineering import EngineeringAgent
from kairos_agents.library.finance import FinanceAgent
from kairos_agents.library.planner import SPECIALIST_ROLES, PlannerAgent
from kairos_agents.library.research import ResearchAgent
from kairos_agents.sdk import think
from kairos_contracts.schema import AgentPlanned, AgentThought, SearchQuery, TaskUnderstood

from .test_agents_units import ENG_REPLY, FINANCE_REPLY, _planner_ctx, ctx_for, manifest
from .test_projects import APOLLO, GENERIC_PLAN, WITH_FINDINGS, ZEUS

SYNTHESIS = {"root_causes": [{"cause": "Dual-run cloud cost caused the overrun", "evidence": ["/org/finance/apollo-budget"]}],
             "recovery_plan": ["Retire the legacy pipeline"], "summary": "One cited cause behind the overrun and the slip."}


def _story(ctx) -> list[tuple[str, object]]:
    kinds = {TaskUnderstood: "understood", AgentPlanned: "planned", AgentThought: "thought"}
    return [(kinds[type(n)], n) for n in ctx.narrations]


def test_the_planner_tells_the_story_in_order():
    ctx, _ = _planner_ctx(GENERIC_PLAN, SYNTHESIS, children=WITH_FINDINGS)
    asyncio.run(PlannerAgent().run(APOLLO, ctx))
    story = _story(ctx)
    kinds = [k for k, _ in story]
    assert kinds[0] == "thought" and story[0][1].step == "search"
    first = kinds.index("understood")
    assert kinds[first + 1:first + 5] == ["planned"] * 4 and kinds.count("understood") == 1
    assert [n.role for k, n in story if k == "planned"] == ["finance-agent", "engineering-agent", "research-agent", "action-agent"]
    assert story[-1][1].step == "synthesize" and "1 cited root cause" in story[-1][1].text
    u = story[first][1]
    assert u.intent == "Investigate why Project Apollo is over budget and six weeks behind schedule."
    assert u.entities == ["Project Apollo", "APOLLO-12"]
    assert {"jira.write", "browser.open", "knowledge.search"} <= set(u.capabilities_needed)
    assert "APOLLO-12" in u.plan_summary
    assert all(n.pid == ctx.pid for k, n in story if k == "thought")


def test_the_planner_announces_zeus_with_its_own_tracker():
    ctx, _ = _planner_ctx(GENERIC_PLAN, SYNTHESIS, children=WITH_FINDINGS)
    asyncio.run(PlannerAgent().run(ZEUS, ctx))
    u = next(n for n in ctx.narrations if isinstance(n, TaskUnderstood))
    assert u.entities[0] == "Project Zeus" and u.entities[1] != "APOLLO-12"


def test_the_planner_says_why_it_skips_the_tracker_update():
    children = {**WITH_FINDINGS, "engineering-agent": ({}, [])}  # no findings: incomplete
    ctx, spawned = _planner_ctx(GENERIC_PLAN, SYNTHESIS, children=children)
    asyncio.run(PlannerAgent().run(APOLLO, ctx))
    assert "action-agent" not in [a for a, _ in spawned]
    assert any(isinstance(n, AgentThought) and n.step == "act" and "engineering-agent" in n.text for n in ctx.narrations)


def test_the_planners_role_table_matches_the_manifests():
    for role, (why, scope, caps) in SPECIALIST_ROLES.items():
        m = manifest(role)
        assert scope == list(m.memory.mounts) and caps == m.all_capabilities(), role
        assert why and len(why) <= 240


def _thoughts(agent, name, reply):
    ctx = ctx_for(name, {"": reply})
    asyncio.run(agent.run(APOLLO, ctx))
    return ctx, [n for n in ctx.narrations if isinstance(n, AgentThought)]


def test_specialists_think_in_counts_never_in_retrieved_text():
    for agent, name, reply in [(FinanceAgent(), "finance-agent", FINANCE_REPLY), (EngineeringAgent(), "engineering-agent", ENG_REPLY),
                               (ResearchAgent(), "research-agent", {"findings": [], "urls_opened": []})]:
        ctx, thoughts = _thoughts(agent, name, reply)
        assert thoughts and thoughts[0].step == "search" and thoughts[-1].step == "analyze", name
        snippets = [h.snippet[:30] for h in asyncio.run(ctx.search(SearchQuery(text=APOLLO, top_k=20))).hits if h.snippet]
        assert snippets
        for t in thoughts:
            assert t.pid == ctx.pid and not any(sn in t.text for sn in snippets), (name, t.text)
    _, finance = _thoughts(FinanceAgent(), "finance-agent", FINANCE_REPLY)
    assert "lakh" not in finance[-1].text and finance[-1].text.endswith("with cited evidence.")  # counts, not model figures


def test_the_firewall_thought_counts_flagged_documents():
    # The fixture bundle's vendor email is flagged; the thought gives a count, not the document's text or the reason.
    _, thoughts = _thoughts(ResearchAgent(), "research-agent", {"findings": [], "urls_opened": []})
    assert [t.text for t in thoughts if t.step == "firewall"] == ["Treating 1 flagged document as data, not instructions."]


def test_think_never_fails_a_run():
    class OldStub:  # a context from before 0.10.0
        pid = 1

    asyncio.run(think(OldStub(), "plan", "fine"))
    ctx = ctx_for("finance-agent")
    asyncio.run(think(ctx, "a-very-long-step-label-that-goes-past-forty-chars", "x" * 500))
    assert ctx.narrations[0].text == "x" * 240 and len(ctx.narrations[0].step) == 40


def test_agents_are_announced_in_the_order_they_are_created():
    # What qwen2.5:7b planned for Zeus: research twice, the action step in the middle of the list.
    plan = {"rationale": "r", "steps": [
        {"step_id": "s1", "agent": "research-agent", "goal": "vendor"},
        {"step_id": "s2", "agent": "finance-agent", "goal": "budget"},
        {"step_id": "s3", "agent": "engineering-agent", "goal": "slip", "depends_on": ["s2"]},
        {"step_id": "s4", "agent": "action-agent", "goal": "tracker"},
        {"step_id": "s5", "agent": "research-agent", "goal": "more vendor"},
    ]}
    ctx, spawned = _planner_ctx(plan, SYNTHESIS, children=WITH_FINDINGS)
    asyncio.run(PlannerAgent().run(ZEUS, ctx))
    roles = [n.role for n in ctx.narrations if isinstance(n, AgentPlanned)]
    assert roles == [a for a, _ in spawned] == ["research-agent", "finance-agent", "research-agent", "engineering-agent",
                                                  "action-agent"]
