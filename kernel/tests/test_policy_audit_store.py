"""Policy rules, audit hash chain, boot recovery, gateway WebSocket replay."""
import asyncio
import json

from kairos_contracts.schema import (
    AgentProcess,
    AgentState,
    Approval,
    ApprovalStatus,
    AuditEntry,
    AuditKind,
    Decision,
    PolicyDecision,
    PrincipalKind,
    Risk,
    SyscallRequest,
    Task,
    TaskStatus,
)
from kairos_contracts.testing.fakes import user_principal
from kairos_contracts.wiring import REPO_ROOT
from kairos_kernel.audit.log import SqliteAuditLog
from kairos_kernel.persistence.store import StateStore
from kairos_kernel.policy.engine import YamlPolicyEngine
from kairos_kernel.testing import done, manifest, run, start_task


def _agent(name, caps):
    return user_principal().model_copy(update={"kind": PrincipalKind.AGENT, "pid": 105, "agent": name, "capabilities": caps})


def _req(cap, tool, op, risk=Risk.LOW):
    return SyscallRequest(syscall_id="SC-1", task_id="T-1", pid=105, capability=cap, tool=tool, operation=op, risk=risk)


def test_repo_policies():
    engine = YamlPolicyEngine(REPO_ROOT / "policies")
    ev = lambda cap, agent, risk=Risk.LOW: asyncio.run(engine.evaluate(_req(cap, cap.split(".")[0], "x", risk),  # noqa: E731
                                                                       _agent(agent, [cap])))
    d = ev("jira.write", "action-agent", Risk.MEDIUM)
    assert d.decision == Decision.REQUIRES_APPROVAL and d.policy == "project-updates-v1"
    assert "mock-jira:8090" in d.constraints["network_allow"]
    assert ev("fs.write", "action-agent").decision == Decision.ALLOW
    assert ev("browser.open", "research-agent").constraints["network_allow"] == ["vendor-docs:80"]
    assert ev("jira.read", "engineering-agent").decision == Decision.ALLOW          # default-v1
    assert ev("database.write", "engineering-agent").decision == Decision.REQUIRES_APPROVAL
    assert ev("sandbox.exec", "engineering-agent").decision == Decision.DENY        # nobody allows it
    assert ev("jira.read", "action-agent", Risk.HIGH).decision == Decision.REQUIRES_APPROVAL
    assert engine.knowledge_allow(_agent("finance-agent", [])) == ["/org/finance/**", "/org/projects/**", "/org/decisions/**",
                                                                  "/org/policies/**"]


def test_deny_wins_and_never(tmp_path):
    (tmp_path / "p.yaml").write_text(
        "policy: strict\npriority: 1\napplies_to: {agents: ['*']}\n"
        "tools: {allow: ['jira.*'], deny: ['jira.delete']}\napproval: {jira.purge: never}\n")
    engine = YamlPolicyEngine(tmp_path)
    caps = ["jira.*"]
    assert asyncio.run(engine.evaluate(_req("jira.delete", "jira", "d"), _agent("a", caps))).decision == Decision.DENY
    assert asyncio.run(engine.evaluate(_req("jira.purge", "jira", "p"), _agent("a", caps))).decision == Decision.DENY
    assert asyncio.run(engine.evaluate(_req("jira.read", "jira", "r"), _agent("a", caps))).decision == Decision.ALLOW


def test_audit_hash_chain(tmp_path):
    log = SqliteAuditLog(tmp_path / "audit.db")
    for i in range(3):
        asyncio.run(log.append(AuditEntry(entry_id=f"A{i}", task_id="T-1", actor="kernel", kind=AuditKind.TASK,
                                          summary=f"e{i}")))
    assert log.verify_chain("T-1")
    assert asyncio.run(log.timeline("T-1")).chain_verified is True
    log.db.execute("UPDATE audit SET data=replace(data, 'e1', 'tampered') WHERE seq=2")
    assert not log.verify_chain("T-1")
    assert asyncio.run(log.timeline("T-1")).chain_verified is False, "the gateway reports the tampering too"


def test_boot_recovery_resumes_interrupted_work(make_kernel, tmp_path):
    store = StateStore(tmp_path / "kernel.db")
    store.put_task(Task(task_id="T-old", org_id="acme", user_id="alice", goal="g", status=TaskStatus.RUNNING, root_pid=101,
                        metadata={"root_agent": "planner-agent"}))
    store.put_task(Task(task_id="T-queued", org_id="acme", user_id="alice", goal="g", status=TaskStatus.QUEUED,
                        metadata={"root_agent": "planner-agent"}))
    store.put_task(Task(task_id="T-crashy", org_id="acme", user_id="alice", goal="g", status=TaskStatus.RUNNING,
                        root_pid=102, metadata={"root_agent": "planner-agent", "restarts": 2}))
    store.put_process(AgentProcess(pid=101, task_id="T-old", owner="alice", agent="planner-agent", state=AgentState.WAITING))
    store.put_process(AgentProcess(pid=102, task_id="T-crashy", owner="alice", agent="planner-agent",
                                   state=AgentState.RUNNING))
    req = _req("jira.write", "jira", "update_issue")
    store.put_approval(Approval(approval_id="APR-1", task_id="T-old", pid=101, agent="planner-agent", syscall=req,
                                decision=PolicyDecision(decision=Decision.REQUIRES_APPROVAL, policy="p", reason="r")))

    async def planner(goal, ctx):
        return done(ctx, "resumed" if "_restored" in ctx.inputs else "fresh run")

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent")])

    async def go():
        await k.boot()
        queued = await k.tasks.wait_terminal("T-queued")
        old = await k.tasks.wait_terminal("T-old")
        await k.shutdown()
        return queued, old

    queued, old = run(go)
    assert k.procs.get(101).state == AgentState.TERMINATED and k.procs.get(101).last_error.message == "kernel restarted"
    assert k.approvals.get("APR-1").status == ApprovalStatus.EXPIRED, "the resumed run asks again"
    assert old.status == TaskStatus.COMPLETED and old.metadata["restarts"] == 1 and old.root_pid > 102
    assert old.result.summary == "fresh run", "no checkpoint existed, so the root started over"
    assert queued.status == TaskStatus.COMPLETED, "queued tasks survive a restart"
    assert k.tasks.get("T-crashy").status == TaskStatus.FAILED, "restart budget exhausted"
    assert "restarted 3 times" in k.tasks.get("T-crashy").error.message


def test_graceful_shutdown_suspends_and_boot_resumes_from_checkpoint(tmp_path):
    """Kernel A is shut down mid-task; kernel B (same data dir) resumes the root from its last checkpoint."""
    import asyncio as aio

    from kairos_kernel.testing import eventually, kernel_factory

    async def planner(goal, ctx):
        if "_restored" in ctx.inputs:
            return done(ctx, f"resumed at stage {ctx.inputs['_restored']['stage']}")
        await ctx.checkpoint({"stage": "evidence-gathered"})
        await aio.sleep(3600)  # long work, interrupted by the shutdown

    scripts, manifests = {"planner-agent": planner}, [manifest("planner-agent")]

    async def first_life():
        k = kernel_factory(tmp_path)(scripts, manifests)
        await k.boot()
        tid = await start_task(k)
        await eventually(lambda: k.tasks.get(tid).root_pid is not None
                         and k.store.latest_checkpoint(k.tasks.get(tid).root_pid) is not None)
        await k.shutdown()
        return tid, k.tasks.get(tid).status

    async def second_life(tid):
        k = kernel_factory(tmp_path)(scripts, manifests)
        await k.boot()
        t = await k.tasks.wait_terminal(tid)
        tl = await k.audit.timeline(tid)
        await k.shutdown()
        return t, tl, k.bus.of_type("agent.log")

    tid, status_after_shutdown = run(first_life)
    assert status_after_shutdown not in (TaskStatus.CANCELLED, TaskStatus.FAILED), "shutdown suspends, it does not kill"
    t, tl, logs = run(lambda: second_life(tid))
    assert t.status == TaskStatus.COMPLETED and t.result.summary == "resumed at stage evidence-gathered"
    assert any("Resumed after kernel restart" in e.summary for e in tl.entries)
    assert any("resuming from checkpoint" in e.payload["message"] for e in logs)


def test_escalation_lets_a_human_grant_another_attempt(make_kernel):
    from kairos_kernel.config import KernelConfig

    attempts = {"n": 0}

    async def flaky(goal, ctx):
        attempts["n"] += 1
        if attempts["n"] <= 3:
            raise RuntimeError(f"boom {attempts['n']}")
        return done(ctx, "fixed on attempt 4")

    k = make_kernel({"planner-agent": flaky}, [manifest("planner-agent")],
                    config=KernelConfig(escalation_timeout_s=5, policy_watch_interval_s=0))

    async def go():
        await k.boot()
        seen = []

        async def approve(ev):
            seen.append(ev.payload)
            await k.approvals.resolve(ev.payload["approval_id"], True, "alice", "try again")

        k.bus.subscribe("approval.requested", approve)
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t, seen

    t, seen = run(go)
    assert t.status == TaskStatus.COMPLETED and t.result.summary == "fixed on attempt 4"
    assert seen[0]["capability"] == "agent.retry" and seen[0]["policy"] == "kernel.escalation"


def test_escalation_rejected_fails_the_task(make_kernel):
    from kairos_kernel.config import KernelConfig

    async def broken(goal, ctx):
        raise RuntimeError("always")

    k = make_kernel({"planner-agent": broken}, [manifest("planner-agent")],
                    config=KernelConfig(escalation_timeout_s=5, policy_watch_interval_s=0))

    async def go():
        await k.boot()
        statuses = []

        async def reject(ev):
            await k.approvals.resolve(ev.payload["approval_id"], False, "alice")

        async def track(ev):
            if ev.payload.get("new") == "waiting_approval":
                statuses.append("seen-waiting")

        k.bus.subscribe("task.status_changed", track)
        k.bus.subscribe("approval.requested", reject)
        t = await k.tasks.wait_terminal(await start_task(k))
        await k.shutdown()
        return t, statuses

    t, statuses = run(go)
    assert t.status == TaskStatus.FAILED and "always" in t.error.message
    assert "seen-waiting" in statuses, "a pending escalation shows up as waiting_approval"


def test_policy_hot_reload(tmp_path):
    import asyncio as aio
    import shutil

    from kairos_contracts.testing.fakes import fake_bundle
    from kairos_contracts.wiring import Settings
    from kairos_kernel.config import KernelConfig
    from kairos_kernel.kernel import Kernel

    policies = tmp_path / "policies"
    shutil.copytree(REPO_ROOT / "policies", policies)
    settings = Settings(data_dir=tmp_path / "data", policies_dir=policies)
    bundle = fake_bundle(settings)
    bundle.policy = YamlPolicyEngine(policies, event_bus=bundle.event_bus)
    k = Kernel(settings, bundle, KernelConfig(policy_watch_interval_s=0.05))
    probe = (_req("sandbox.exec", "sandbox", "exec"), _agent("engineering-agent", ["sandbox.exec"]))
    good = ("policy: sandbox-ok\npriority: 5\napplies_to: {agents: [engineering-agent]}\n"
            "tools: {allow: [sandbox.exec]}\napproval: {sandbox.exec: required}\n")

    async def go():
        await k.boot()
        before = await k.policy.evaluate(*probe)
        (policies / "zz-sandbox.yaml").write_text(good)
        await aio.sleep(0.4)
        after = await k.policy.evaluate(*probe)
        (policies / "zz-sandbox.yaml").write_text("policy: [broken")
        await aio.sleep(0.4)
        still = await k.policy.evaluate(*probe)
        await k.shutdown()
        return before, after, still, bundle.event_bus.of_type("policy.updated")

    before, after, still, events = run(go)
    assert before.decision == Decision.DENY and after.decision == Decision.REQUIRES_APPROVAL
    assert still.decision == Decision.REQUIRES_APPROVAL, "a broken edit keeps the last good policy set"
    assert "sandbox-ok" in events[0].payload["policies"] and events[-1].payload.get("error")


def test_websocket_replays_history_for_late_subscribers(make_kernel):
    from fastapi.testclient import TestClient
    from kairos_kernel.gateway.app import create_app

    async def planner(goal, ctx):
        await ctx.log("hello")
        return done(ctx, "finished")

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent")])
    with TestClient(create_app(k)) as client:
        task = client.post("/tasks", json={"goal": "g", "metadata": {"root_agent": "planner-agent"}}).json()
        asyncio.run(asyncio.sleep(0.3))  # let it finish before we subscribe
        seen = []
        with client.websocket_connect(f"/ws/events?task_id={task['task_id']}&types=task.*,agent.log") as ws:
            while True:
                ev = json.loads(ws.receive_text())
                seen.append(ev["type"])
                if ev["type"] == "task.completed":
                    break
        assert seen[0] == "task.created" and "agent.log" in seen and "process.spawned" not in seen
        assert client.get(f"/tasks/{task['task_id']}").json()["result"]["summary"] == "finished"
        assert client.get("/tasks/T-nope").status_code == 404
        assert client.get("/system/status").json()["ready"] is True


def test_start_task_helper_uses_root_agent(make_kernel):
    async def planner(goal, ctx):
        return done(ctx, goal)

    k = make_kernel({"planner-agent": planner}, [manifest("planner-agent")])

    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await start_task(k, goal="hello"))
        await k.shutdown()
        return t

    assert run(go).result.summary == "hello"
