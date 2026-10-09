"""The real planner and action agent on a real kernel (fake models, knowledge and tools): when a specialist fails, the
tracker is not touched, a partial plan is written and the task fails naming the specialist."""
from kairos_agents.library.action import ActionAgent
from kairos_agents.library.planner import PlannerAgent
from kairos_contracts.errors import KairosError
from kairos_contracts.schema import TaskCreate, TaskStatus
from kairos_contracts.testing.fakes import user_principal
from kairos_kernel.config import KernelConfig
from kairos_kernel.testing import done, kernel_factory, manifest, run

SPECIALISTS = ["finance-agent", "engineering-agent", "research-agent"]
GOAL = ("Investigate why Project Apollo is over budget and six weeks behind schedule. "
        "Identify root causes, update the tracker, and prepare a recovery plan.")


def test_a_failed_specialist_fails_the_task_without_touching_the_tracker(tmp_path):
    action_runs = []

    async def finance(goal, ctx):
        raise KairosError("MODEL_UNAVAILABLE", "ollama qwen2.5:7b-instruct: cannot reach Ollama at http://127.0.0.1:11434 (ConnectError)")

    async def engineering(goal, ctx):
        return done(ctx, "slip", blockers=[{"issue": "APOLLO-12", "cause": "backfill failed", "evidence": []}])

    async def research(goal, ctx):
        return done(ctx, "vendor", findings=[], urls_opened=["http://vendor-docs/sdk-v5.html"])

    async def action(goal, ctx):
        action_runs.append(goal)
        return await ActionAgent().run(goal, ctx)

    manifests = [manifest("planner-agent", agents=[*SPECIALISTS, "action-agent"]), *(manifest(a) for a in SPECIALISTS),
                 manifest("action-agent", tools=["jira.write", "fs.write"])]
    make = kernel_factory(tmp_path, KernelConfig(policy_watch_interval_s=0, retry_backoff_s=0))
    k = make({"planner-agent": lambda g, ctx: PlannerAgent().run(g, ctx), "finance-agent": finance,
              "engineering-agent": engineering, "research-agent": research, "action-agent": action}, manifests)

    async def go():
        await k.boot()
        task = await k.tasks.create(TaskCreate(goal=GOAL, metadata={"root_agent": "planner-agent"}), user_principal())
        t = await k.tasks.wait_terminal(task.task_id)
        [ref] = [r for r in k.store.result(t.root_pid).artifacts if r.endswith("recovery-plan.md")]
        plan = (await k.services.artifacts.get(ref)).decode()
        timeline = await k.services.audit.timeline(t.task_id)
        approvals = k.approvals.list(task_id=t.task_id)
        await k.shutdown()
        return t, plan, timeline.entries, approvals

    t, plan, entries, approvals = run(go, timeout=60)
    assert action_runs == [], "the action agent never ran"
    assert t.status == TaskStatus.FAILED
    assert t.error.code == "MODEL_UNAVAILABLE" and t.error.message.startswith("incomplete findings from finance-agent")
    assert plan.splitlines()[2] == "**Partial: finance-agent failed; tracker not updated.**"
    assert [e for e in entries if e.kind.value == "spawn" and "finance-agent" in e.summary], "the audit is really there"
    assert not [e for e in entries if e.kind.value == "syscall" and "jira.write" in e.summary], "no jira.write"
    assert not [e for e in entries if e.kind.value == "approval"], "no approval requested"
    assert approvals == []
