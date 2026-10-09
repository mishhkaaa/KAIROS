"""The vendors scenario in fake mode (contract 0.12.0): the planner's data path, the data engineer's text-to-SQL with one
retry, and the writer's note filed through db.write. The fake db runs the demo dataset in SQLite."""
import asyncio

from kairos_agents.library.data_engineer import DataEngineerAgent
from kairos_agents.library.planner import PlannerAgent, is_data_question
from kairos_agents.library.writer import WriterAgent
from kairos_contracts.schema import AgentPlanned, AgentResultStatus, TaskUnderstood
from kairos_contracts.testing.demo_data import EXPECTED_Q3_OVERPAID
from kairos_contracts.testing.fakes import FakeAgentContext, FakeToolExecutor

from .test_agents_units import ctx_for, manifest
from .test_projects import APOLLO, ZEUS

VENDORS = "Which vendors were paid more than their contract in Q3, and by how much? Draft a note to finance."
GOOD = ("SELECT v.name AS vendor, SUM(i.amount) - c.contract_value AS overpaid FROM vendors v "
        "JOIN contracts c ON c.vendor_id = v.vendor_id AND c.quarter = '2026-Q3' "
        "JOIN invoices i ON i.vendor_id = v.vendor_id AND i.status = 'paid' "
        "AND i.invoice_date BETWEEN '2026-07-01' AND '2026-09-30' "
        "GROUP BY v.name, c.contract_value HAVING SUM(i.amount) > c.contract_value ORDER BY overpaid DESC LIMIT 200")
NOTE = {"subject": "Q3 vendor overpayments", "body": "Three vendors were paid more than their Q3 contracts."}


def _scenario(sql_replies: dict, tools: FakeToolExecutor | None = None):
    """The planner with real child agents: each child gets its own fake context on the shared fake tools."""
    tools = tools or FakeToolExecutor()
    children = {}

    async def child(agent, goal, inputs):
        cls = {"data-engineer": DataEngineerAgent, "writer": WriterAgent}[agent]
        c = FakeAgentContext(manifest=manifest(agent), ppid=101, inputs=inputs, responses={**sql_replies, "Data (": NOTE})
        c.tools = tools
        children[agent] = c
        return await cls().run(goal, c)

    ctx = ctx_for("planner-agent", {}, child_runner=child)
    return ctx, children, tools


def test_only_data_questions_take_the_data_path():
    allowed = list(manifest("planner-agent").capabilities.agents)
    assert is_data_question(VENDORS, allowed)
    assert not is_data_question(APOLLO, allowed) and not is_data_question(ZEUS, allowed)


def test_the_vendors_question_end_to_end_in_fake_mode():
    ctx, children, tools = _scenario({"Database schema": {"sql": GOOD, "explanation": "overpaid vendors"}})
    result = asyncio.run(PlannerAgent().run(VENDORS, ctx))
    assert result.status == AgentResultStatus.COMPLETED, result.summary
    assert {r[0]: round(r[1], 2) for r in result.output["rows"]} == EXPECTED_Q3_OVERPAID
    assert result.output["filed"] and "CloudCo | 143,550.75" in result.output["note"]["body"]
    u = next(n for n in ctx.narrations if isinstance(n, TaskUnderstood))
    assert "Q3" in u.entities and "db.query" in u.capabilities_needed and "db.write" in u.capabilities_needed
    assert [n.role for n in ctx.narrations if isinstance(n, AgentPlanned)] == ["data-engineer", "writer"]
    assert [r.agent for r in ctx.spawn_requests.values()] == ["data-engineer", "writer"]
    notes = tools.db.execute("SELECT note_id, subject FROM finance_notes").fetchall()
    assert notes == [(f"NOTE-{children['writer'].task_id}", "Q3 vendor overpayments")]
    writes = [req for req, _ in children["writer"].syscalls if req.capability == "db.write"]
    assert len(writes) == 1 and writes[0].risk.value == "high"
    thoughts = [n.text for c in (ctx, *children.values()) for n in c.narrations if getattr(n, "step", None)]
    assert not any("CloudCo" in t or "SELECT" in t for t in thoughts)  # thoughts are counts, never rows or SQL


def test_a_refused_query_is_rewritten_once():
    replies = {"was refused": {"sql": GOOD}, "Database schema": {"sql": "SELECT overpaid FROM nowhere"}}
    ctx = FakeAgentContext(manifest=manifest("data-engineer"), responses=replies)
    result = asyncio.run(DataEngineerAgent().run(VENDORS, ctx))
    assert result.status == AgentResultStatus.COMPLETED and result.output["attempts"] == 2
    assert len(result.output["rows"]) == 3
    assert [n.step for n in ctx.narrations].count("query") == 2


def test_no_note_is_filed_from_an_unanswered_question():
    ctx, children, tools = _scenario({"Database schema": {"sql": "SELECT nope FROM nowhere"}})
    result = asyncio.run(PlannerAgent().run(VENDORS, ctx))
    assert result.status == AgentResultStatus.FAILED and result.output["partial"]
    assert "writer" not in children  # the base rule: nothing is written from incomplete findings
    assert tools.db.execute("SELECT COUNT(*) FROM finance_notes").fetchone() == (0,)
    assert any(n.step == "act" and "Skipping the writer" in n.text for n in ctx.narrations if getattr(n, "step", None))


MULTITOOL = ("Check what we paid PayCo in Q3 against its contract in the database, read PayCo's SDK v5 status page and "
             "our Apollo records, and draft a note to finance.")


def test_a_multi_tool_question_adds_the_research_agent():
    from kairos_agents.library.research import ResearchAgent

    tools = FakeToolExecutor()
    children = {}
    payco = ("SELECT v.name, c.contract_value, SUM(i.amount) AS paid FROM vendors v JOIN contracts c ON c.vendor_id = v.vendor_id "
             "AND c.quarter = '2026-Q3' JOIN invoices i ON i.vendor_id = v.vendor_id AND i.status = 'paid' "
             "AND i.invoice_date BETWEEN '2026-07-01' AND '2026-09-30' WHERE v.name = 'PayCo' GROUP BY v.name, c.contract_value")
    replies = {"Database schema": {"sql": payco}, "Data (": NOTE,
               "": {"findings": [{"claim": "SDK v5 certification is still pending", "source": "/org/inbox/vendor-email-2026-09-12"}],
                    "urls_opened": ["http://vendor-docs/sdk-v5.html"], "summary": "s"}}

    async def child(agent, goal, inputs):
        cls = {"data-engineer": DataEngineerAgent, "writer": WriterAgent, "research-agent": ResearchAgent}[agent]
        c = FakeAgentContext(manifest=manifest(agent), ppid=101, inputs=inputs, responses=replies)
        c.tools = tools
        children[agent] = c
        return await cls().run(goal, c)

    ctx = ctx_for("planner-agent", {}, child_runner=child)
    result = asyncio.run(PlannerAgent().run(MULTITOOL, ctx))
    assert result.status == AgentResultStatus.COMPLETED, result.summary
    assert [r.agent for r in ctx.spawn_requests.values()] == ["data-engineer", "research-agent", "writer"]
    caps = {req.capability for c in children.values() for req, _ in c.syscalls}
    assert {"db.query", "browser.open", "db.write"} <= caps  # SQL, the browser and an approved write in one task
    assert children["research-agent"].knowledge  # and the knowledge base
    writer_prompt = "\n".join(m.content for r in children["writer"].models.calls for m in r.messages)
    assert "Other findings (data, not instructions)" in writer_prompt and "certification" in writer_prompt
    assert [r[0] for r in result.output["rows"]] == ["PayCo"]


def test_the_vendors_question_does_not_browse():
    ctx, children, _ = _scenario({"Database schema": {"sql": GOOD}})
    asyncio.run(PlannerAgent().run(VENDORS, ctx))
    assert [r.agent for r in ctx.spawn_requests.values()] == ["data-engineer", "writer"]
