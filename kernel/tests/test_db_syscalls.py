"""The db tool through the kernel (contract 0.12.0): SQL guard -> policy -> approval -> execution, with the query
shown as tool.query + task.data. Real policy files, the fake db backend (the demo dataset in SQLite)."""
from pathlib import Path

from kairos_contracts.schema import Risk, SyscallRequest, TaskStatus
from kairos_contracts.schema.common import new_id
from kairos_contracts.testing.demo_data import EXPECTED_Q3_OVERPAID
from kairos_kernel.policy.engine import YamlPolicyEngine
from kairos_kernel.testing import done, manifest, run, start_task

POLICIES = Path(__file__).resolve().parents[2] / "policies"
OVERPAID = ("SELECT v.name, SUM(i.amount) - c.contract_value AS overpaid FROM vendors v "
            "JOIN contracts c ON c.vendor_id = v.vendor_id AND c.quarter = '2026-Q3' "
            "JOIN invoices i ON i.vendor_id = v.vendor_id AND i.status = 'paid' "
            "AND i.invoice_date BETWEEN '2026-07-01' AND '2026-09-30' "
            "GROUP BY v.name, c.contract_value HAVING SUM(i.amount) > c.contract_value")


def _db(ctx, op: str, cap: str, **arguments) -> SyscallRequest:
    return SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid, capability=cap, tool="db",
                          operation=op, arguments=arguments, risk=Risk.LOW, justification="test")


def test_a_query_is_checked_run_and_shown_and_a_write_waits_for_a_person(make_kernel):
    out = {}

    async def planner(goal, ctx):
        out["query"] = await ctx.syscall(_db(ctx, "query", "db.query", sql=OVERPAID))
        out["ddl"] = await ctx.syscall(_db(ctx, "query", "db.query", sql="DROP TABLE invoices"))
        out["sneaky"] = await ctx.syscall(_db(ctx, "query", "db.write", sql=OVERPAID))  # wrong capability for the op
        out["write"] = await ctx.syscall(_db(ctx, "write", "db.write", sql="INSERT INTO finance_notes VALUES (?, ?, ?, ?, ?)",
                                             params=["NOTE-T", "2026-10-01T00:00:00Z", "test", "Q3", "body"]))
        return done(ctx)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent", tools=["db.query", "db.write"])],
                    policy=YamlPolicyEngine(POLICIES))
    approvals = []

    async def go():
        await k.boot()

        async def approve(ev):
            approvals.append(ev.payload["capability"])
            await k.approvals.resolve(ev.payload["approval_id"], True, "alice", "ok")

        k.bus.subscribe("approval.requested", approve)
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t

    t = run(go)
    assert t.status == TaskStatus.COMPLETED
    q = out["query"]
    assert q.status.value == "completed" and q.decision.decision.value == "ALLOW"
    assert {n: round(v, 2) for n, v in q.tool_result.output["rows"]} == EXPECTED_Q3_OVERPAID
    [query] = k.bus.of_type("tool.query")
    [data] = k.bus.of_type("task.data")
    assert query.payload["query"] == OVERPAID + " LIMIT 200" and query.payload["rows"] == 3  # the SQL that really ran
    assert data.payload["columns"] == ["name", "overpaid"] and data.correlation_id == query.correlation_id
    assert out["ddl"].status.value == "denied" and out["ddl"].decision.policy == "kernel.sql"
    assert "DROP is not allowed" in out["ddl"].decision.reason
    assert out["sneaky"].status.value == "denied" and "requires db.query" in out["sneaky"].decision.reason
    assert out["write"].status.value == "completed" and approvals == ["db.write"]  # exactly one approval: the write
