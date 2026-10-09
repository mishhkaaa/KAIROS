"""Dynamic agents on the agents side (contract 0.11.0): role templates, what the planner offers the model, and the
bounds it spawns each role with. Fake context only, no Ollama."""
import asyncio

from kairos_agents.library.planner import EXTRA_HANDLES, LIBRARY_ROLES, SPECIALIST_ROLES, PlannerAgent, offered_roles
from kairos_agents.library.template import TemplateAgent
from kairos_agents.sdk import remember_finding, role_of
from kairos_contracts.schema import AgentPlanned

from .test_agents_units import _planner_ctx, ctx_for, manifest
from .test_projects import APOLLO, GENERIC_PLAN, WITH_FINDINGS, ZEUS
from .test_thoughts import SYNTHESIS

VENDORS = "Which vendors were paid more than their contract in Q3, and by how much? Draft a note to finance."
FOUR = "Available agents:\n- finance-agent\n- engineering-agent\n- research-agent\n- action-agent\n\nProduce a plan"


def _planning_prompt(ctx) -> str:
    return next(m.content for r in ctx.models.calls for m in r.messages if "Produce a plan" in m.content)


def test_apollo_and_zeus_are_offered_exactly_the_four_library_roles():
    for goal in (APOLLO, ZEUS):
        ctx, _ = _planner_ctx(GENERIC_PLAN, SYNTHESIS, children=WITH_FINDINGS)
        asyncio.run(PlannerAgent().run(goal, ctx))
        prompt = _planning_prompt(ctx)
        assert FOUR in prompt and "Also available" not in prompt  # the planning prompt is what it was before B2


def test_a_goal_that_asks_for_them_is_offered_the_new_templates():
    allowed = list(manifest("planner-agent").capabilities.agents)
    assert offered_roles(VENDORS, allowed) == [*LIBRARY_ROLES, "data-engineer", "writer"]
    assert offered_roles(APOLLO, allowed) == offered_roles(ZEUS, allowed) == list(LIBRARY_ROLES)
    memo = "Investigate why Project Apollo is over budget and draft a memo for the CFO."
    assert offered_roles(memo, allowed) == [*LIBRARY_ROLES, "writer"]
    ctx, _ = _planner_ctx(GENERIC_PLAN, SYNTHESIS, children=WITH_FINDINGS)
    asyncio.run(PlannerAgent().run(memo, ctx))
    assert "- writer: Drafts the note" in _planning_prompt(ctx)


def test_every_role_is_spawned_with_the_bounds_it_was_announced_with():
    ctx, _ = _planner_ctx(GENERIC_PLAN, SYNTHESIS, children=WITH_FINDINGS)
    asyncio.run(PlannerAgent().run(APOLLO, ctx))
    announced = [n for n in ctx.narrations if isinstance(n, AgentPlanned)]
    requests = list(ctx.spawn_requests.values())
    assert [r.agent for r in requests] == [a.role for a in announced]
    for a, r in zip(announced, requests, strict=True):
        assert r.capabilities == a.capabilities and r.why == a.why
        assert r.scope == [f"{s}/**" for s in a.scope]


def test_the_role_tables_match_the_templates():
    for role, handles in EXTRA_HANDLES.items():
        assert set(handles) == set(manifest(role).handles), role
        assert manifest(role).system_prompt and manifest(role).runtime.entrypoint.startswith("kairos_agents.library.")
    assert set(SPECIALIST_ROLES) == set(manifest("planner-agent").capabilities.agents)


def test_a_template_agent_answers_with_cited_findings():
    reply = {"findings": [{"claim": "Cloud spend doubled during the dual run", "evidence": ["/org/finance/apollo-budget"]},
                          {"claim": "Made up", "evidence": ["/org/nowhere"]}], "summary": "One cited finding."}
    ctx = ctx_for("data-engineer", {"": reply})
    result = asyncio.run(TemplateAgent().run("Project Apollo cloud cost by month", ctx))
    assert result.output["findings"] == [{"claim": "Cloud spend doubled during the dual run",
                                          "evidence": ["/org/finance/apollo-budget"]}]
    assert [n.step for n in ctx.narrations] [0] == "search" and ctx.narrations[-1].text == "Found 1 cited finding."


def test_memories_belong_to_the_role_not_the_generated_name():
    m = manifest("finance-agent")
    gen = m.model_copy(update={"name": "finance-agent@T-1", "template": "finance-agent", "generated": True, "task_id": "T-1"})
    ctx = ctx_for("finance-agent")
    ctx.manifest = gen
    assert role_of(ctx) == "finance-agent"
    asyncio.run(remember_finding(ctx, "finding", ["/org/finance/apollo-budget"]))
    assert [r.owner for r in ctx.memory.records.values()] == ["finance-agent"]
