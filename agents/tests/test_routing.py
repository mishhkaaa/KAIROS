"""The Jev router (local): parsing its answers, and the guards that keep the planner's paths safe."""
import asyncio

from kairos_agents import routing
from kairos_agents.library.planner import PlannerAgent, planned, routed, understood
from kairos_agents.prompts import PlanStep
from kairos_agents.routing import RouteDecision

ALLOWED = ["finance-agent", "engineering-agent", "research-agent", "action-agent", "data-engineer", "writer", "web-researcher"]
PROJECTS = {"apollo", "zeus"}


class FakeLaya:
    def predict(self, state, questions):
        assert set(questions) >= {"goal_type", "wants_change", "wants_web", "role:finance-agent"}
        return {"answers": {"goal_type": {"type": "choice", "choice": "investigation",
                                          "probabilities": {"investigation": 0.9, "question": 0.1}},
                            "wants_change": {"type": "noul", "noul": 0.8},
                            "wants_web": {"type": "noul", "noul": 0.1},
                            "role:finance-agent": {"type": "noul", "noul": 0.91}},
                "routing": {"model": "english"}}


def test_decide_parses_typed_answers(monkeypatch):
    monkeypatch.setattr(routing, "_router", FakeLaya())
    d = routing.decide_sync("Why is Project Apollo over budget?", ["finance-agent"])
    assert (d.goal_type, d.goal_type_p, d.scores, d.wants_change) == ("investigation", 0.9, {"finance-agent": 0.91}, 0.8)
    assert d.model == "jev-local (english)" and d.confident() and d.wanted(["finance-agent"]) == ["finance-agent"]


def test_decide_is_none_when_switched_off(monkeypatch):
    monkeypatch.setenv("KAIROS_JEV", "off")
    assert asyncio.run(routing.decide("anything", ["finance-agent"])) is None


def route(goal_type, p=0.9, **scores):
    return RouteDecision(goal_type=goal_type, goal_type_p=p, scores=scores)


def test_goal_type_follows_a_confident_router_within_the_guards():
    g = PlannerAgent._goal_type
    assert g("Summarize this week's Slack decisions", ALLOWED, PROJECTS, route("question")) == "question"
    # an investigation needs a project to record its findings on
    assert g("Why are our deploys slow?", ALLOWED, PROJECTS, route("investigation")) == "question"
    assert g("Why is Apollo over budget?", ALLOWED, PROJECTS, route("investigation")) == "investigation"
    # a database question named outright stays one; no data-engineer means no data path
    assert g("Which vendors did we overpay? Use the invoices.", ALLOWED, PROJECTS, route("question")) == "data"
    assert g("Total spend per vendor", ["finance-agent"], PROJECTS, route("data")) != "data"


def test_unsure_or_missing_router_leaves_it_to_the_rules():
    g = PlannerAgent._goal_type
    assert g("What do we know about Priya?", ALLOWED, PROJECTS, route("investigation", p=0.45)) == "question"
    assert g("Investigate why Project Apollo is late", ALLOWED, PROJECTS, None) == "investigation"


def test_the_router_can_add_a_write_but_never_remove_an_asked_for_one():
    w = PlannerAgent._wants_change
    assert w("Let the team know on APOLLO-12", RouteDecision("investigation", 0.9, wants_change=0.7))
    assert w("update the tracker", RouteDecision("investigation", 0.9, wants_change=0.1))
    assert not w("why is it late?", RouteDecision("investigation", 0.9, wants_change=0.1))


def test_the_story_carries_the_routing_decision():
    r = route("investigation", **{"finance-agent": 0.91})
    r.ms = 38.0
    u = routed(understood("Why is Apollo over budget?", "Apollo", []), "investigation", r)
    assert (u.router, u.goal_type, u.route_scores, u.route_ms) == ("jev", "investigation", {"finance-agent": 0.91}, 38.0)
    assert routed(u, "question", None).router == "rules"
    assert planned(PlanStep(step_id="s1", agent="finance-agent", goal="x"), r).score == 0.91
