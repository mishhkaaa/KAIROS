"""Dynamic agents (contract 0.11.0): every child is generated from its role template, bounded by the template, the
request, the user's permissions and org policy; sub-agents never get wider; generated manifests and policies go when
the task ends (and at boot)."""
import asyncio
import textwrap

import yaml
from kairos_contracts.schema import (
    AgentManifest,
    ManifestMemory,
    Risk,
    SyscallRequest,
    TaskStatus,
    UserPermissions,
)
from kairos_contracts.schema.common import new_id
from kairos_contracts.testing.fakes import FakePermissionsProvider
from kairos_kernel.permissions import RolePermissions
from kairos_kernel.policy.engine import YamlPolicyEngine
from kairos_kernel.testing import done, manifest, run, start_task

BOB = UserPermissions(user_id="alice", org_id="acme", roles=["viewer"], capabilities=["knowledge.*", "agent.spawn"],
                      data_scopes=["/org/projects/**"])


def _mounted(name: str, mounts: list[str], **kw) -> AgentManifest:
    m = manifest(name, **kw)
    return AgentManifest.model_validate(m.model_copy(update={"memory": ManifestMemory(mounts=mounts)}).model_dump())


def _policies(tmp_path, text: str):
    d = tmp_path / "policies"
    d.mkdir(exist_ok=True)
    (d / "org.yaml").write_text(textwrap.dedent(text), encoding="utf-8")
    return YamlPolicyEngine(d)


def _go(k):
    async def go():
        await k.boot()
        t = await k.tasks.wait_terminal(await start_task(k))
        await asyncio.sleep(0)
        await k.shutdown()
        return t

    return run(go)


def _narrowed(k, tid):
    return [e for e in asyncio.run(k.audit.timeline(tid)).entries if e.kind == "policy" and e.summary.startswith("Narrowed")]


def test_generated_capabilities_never_exceed_the_users(make_kernel):
    seen = {}

    async def planner(goal, ctx):
        await ctx.wait(await ctx.spawn("finance-agent", "budget", why="explain the variance"))
        return done(ctx)

    async def finance(goal, ctx):
        seen["caps"], seen["scopes"] = list(ctx.principal.capabilities), list(ctx.principal.data_scopes)
        seen["manifest"] = ctx.manifest
        return done(ctx)

    k = make_kernel({"planner-agent": planner, "finance-agent": finance},
                    [manifest("planner-agent", agents=["finance-agent"]),
                     _mounted("finance-agent", ["/org/finance", "/org/projects"], tools=["jira.read"])],
                    permissions=FakePermissionsProvider({"alice": BOB}))
    t = _go(k)
    assert t.status == TaskStatus.COMPLETED
    assert "jira.read" not in seen["caps"] and seen["scopes"] == ["/org/projects/**"]
    m = seen["manifest"]
    assert (m.name, m.template, m.generated, m.task_id) == (f"finance-agent@{t.task_id}", "finance-agent", True, t.task_id)
    [entry] = _narrowed(k, t.task_id)
    assert entry.data["dropped"]["jira.read"] == "not granted to alice (roles: viewer)"
    assert "outside alice's data scopes" in entry.data["dropped"]["/org/finance/**"]
    assert entry.data["why"] == "explain the variance"


def test_an_over_broad_request_is_narrowed_and_the_audit_says_why(make_kernel):
    seen = {}

    async def planner(goal, ctx):
        await ctx.wait(await ctx.spawn("finance-agent", "budget", capabilities=["knowledge.search", "jira.write", "db.write"],
                                       scope=["/org/**"]))
        return done(ctx)

    async def finance(goal, ctx):
        seen["caps"] = list(ctx.principal.capabilities)
        return done(ctx)

    k = make_kernel({"planner-agent": planner, "finance-agent": finance},
                    [manifest("planner-agent", agents=["finance-agent"]), manifest("finance-agent", tools=["jira.read"])])
    t = _go(k)
    assert seen["caps"] == ["knowledge.search"]  # the request narrowed the template; its extras were refused
    [entry] = _narrowed(k, t.task_id)
    assert entry.data["dropped"]["jira.write"] == entry.data["dropped"]["db.write"] == "not in the finance-agent template"
    assert "jira.write (not in the finance-agent template)" in entry.summary


def test_org_policy_applies_through_the_template_and_generated_policies_only_tighten(make_kernel, tmp_path):
    engine = _policies(tmp_path, """
        policy: org-v1
        priority: 10
        applies_to: {agents: [action-agent]}
        tools: {allow: ["jira.read", "jira.write", "fs.write"]}
        approval: {jira.write: auto, fs.write: auto}
    """)
    out = {}

    async def planner(goal, ctx):
        await ctx.wait(await ctx.spawn("action-agent", "update the tracker"))
        return done(ctx)

    async def action(goal, ctx):
        out["caps"] = list(ctx.principal.capabilities)
        for cap, op in (("fs.write", "write"), ("jira.write", "update_issue")):
            tool = cap.split(".")[0]
            req = SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid, capability=cap, tool=tool,
                                 operation=op, arguments={"key": "APOLLO-12", "fields": {}, "path": "reports/x.md", "content": "x"},
                                 risk=Risk.LOW, justification="test")
            out[cap] = await engine.evaluate(req, ctx.principal)
        return done(ctx)

    k = make_kernel({"planner-agent": planner, "action-agent": action},
                    [manifest("planner-agent", agents=["action-agent"]),
                     manifest("action-agent", tools=["jira.read", "jira.write", "fs.write", "sandbox.exec"])], policy=engine)
    t = _go(k)
    assert "sandbox.exec" not in out["caps"]  # no org document allows it: dropped at generation, not granted-then-denied
    assert _narrowed(k, t.task_id)[0].data["dropped"]["sandbox.exec"].startswith("org policy:")
    assert out["fs.write"].decision.value == "ALLOW" and out["fs.write"].policy == "org-v1"  # matched via the template
    assert out["jira.write"].decision.value == "REQUIRES_APPROVAL"  # the org said auto; a write still needs a person
    assert out["jira.write"].policy == f"gen-action-agent@{t.task_id}"


def test_sub_agents_inherit_the_bounds_never_wider(make_kernel):
    seen = {}

    async def planner(goal, ctx):
        await ctx.wait(await ctx.spawn("analyst", "look into it", capabilities=["knowledge.read", "knowledge.search", "agent.spawn"],
                                       scope=["/org/projects/**"]))
        return done(ctx)

    async def analyst(goal, ctx):
        seen["analyst"] = list(ctx.principal.capabilities)
        await ctx.wait(await ctx.spawn("writer", "draft", scope=["/org/**"]))
        return done(ctx)

    async def writer(goal, ctx):
        seen["writer"], seen["writer_scopes"] = list(ctx.principal.capabilities), list(ctx.principal.data_scopes)
        return done(ctx)

    k = make_kernel({"planner-agent": planner, "analyst": analyst, "writer": writer},
                    [manifest("planner-agent", agents=["analyst"]),
                     _mounted("analyst", ["/org"], tools=["jira.read"], agents=["writer"]),
                     _mounted("writer", ["/org"], tools=["fs.write"])])
    t = _go(k)
    assert t.status == TaskStatus.COMPLETED
    assert "jira.read" not in seen["analyst"] and "agent.spawn" in seen["analyst"]
    assert "fs.write" not in seen["writer"]  # the writer template has it, its generated parent does not
    assert set(seen["writer"]) <= set(seen["analyst"]) and seen["writer_scopes"] == ["/org/projects/**"]
    dropped = {e.data["agent"]: e.data["dropped"] for e in _narrowed(k, t.task_id)}
    assert dropped[f"writer@{t.task_id}"]["fs.write"] == f"wider than the parent analyst@{t.task_id}"


def _cleanup_kernel(make_kernel, child):
    async def planner(goal, ctx):
        pid = await ctx.spawn("worker", "part")
        return (await ctx.wait(pid)).model_copy(update={"pid": ctx.pid, "agent": ctx.manifest.name})

    return make_kernel({"planner-agent": planner, "worker": child}, [manifest("planner-agent", agents=["worker"]), manifest("worker")])


def test_generated_manifests_and_policies_are_removed_when_the_task_ends(make_kernel, tmp_path):
    during = {}

    async def ok(goal, ctx):
        during["files"] = sorted(p.name for p in (tmp_path / "ephemeral" / ctx.task_id).rglob("*.yaml"))
        return done(ctx)

    async def boom(goal, ctx):
        raise RuntimeError("worker crashed")

    async def hang(goal, ctx):
        await asyncio.sleep(30)
        return done(ctx)

    k = _cleanup_kernel(make_kernel, ok)
    t = _go(k)
    assert during["files"] == [f"gen-worker_{t.task_id}.yaml", f"worker_{t.task_id}.yaml"]  # manifest + policy, while running
    assert k.ephemeral.names(t.task_id) == [] and not (tmp_path / "ephemeral" / t.task_id).exists()

    k = _cleanup_kernel(make_kernel, boom)
    t = _go(k)
    assert t.status == TaskStatus.FAILED and k.ephemeral.names(t.task_id) == []
    assert not (tmp_path / "ephemeral" / t.task_id).exists()

    k = _cleanup_kernel(make_kernel, hang)

    async def cancelled():
        await k.boot()
        tid = await start_task(k)
        for _ in range(100):
            if k.ephemeral.names(tid):
                break
            await asyncio.sleep(0.02)
        assert k.ephemeral.names(tid)
        await k.tasks.cancel(tid)
        t = k.tasks.get(tid)
        await k.shutdown()
        return t

    t = run(cancelled)
    assert t.status == TaskStatus.CANCELLED and k.ephemeral.names(t.task_id) == []
    assert not (tmp_path / "ephemeral" / t.task_id).exists()


def test_boot_sweeps_what_a_restart_left_behind(make_kernel, tmp_path):
    stale = tmp_path / "ephemeral" / "T-dead" / "manifests"
    stale.mkdir(parents=True)
    (stale / "worker_T-dead.yaml").write_text("name: worker@T-dead\n", encoding="utf-8")
    k = make_kernel({"planner-agent": lambda g, c: asyncio.sleep(0, done(c))}, [manifest("planner-agent")])

    async def go():
        await k.boot()
        await k.shutdown()

    run(go)
    assert not (tmp_path / "ephemeral" / "T-dead").exists()


def test_the_role_stub(tmp_path):
    (tmp_path / "rbac").mkdir()
    (tmp_path / "rbac" / "role-capabilities.yaml").write_text(yaml.safe_dump({
        "default_role": "member", "users": {"alice": ["owner"]},
        "roles": {"owner": {"capabilities": ["jira.*", "knowledge.*"], "data_scopes": ["/org/**"]},
                  "member": {"capabilities": ["knowledge.*"], "data_scopes": ["/org/projects/**"]}}}), encoding="utf-8")
    stub = RolePermissions.from_dir(tmp_path)
    alice, bob = asyncio.run(stub.resolve("alice", "acme")), asyncio.run(stub.resolve("bob", "acme"))
    assert (alice.roles, alice.capabilities) == (["owner"], ["jira.*", "knowledge.*"])
    assert (bob.roles, bob.capabilities, bob.data_scopes) == (["member"], ["knowledge.*"], ["/org/projects/**"])
    assert asyncio.run(stub.resolve("bob", "acme", ["owner"])).roles == ["owner"]  # roles from the session win
    unbounded = asyncio.run(RolePermissions.from_dir(tmp_path / "nowhere").resolve("carol", "acme"))
    assert "jira.*" in unbounded.capabilities and unbounded.data_scopes == ["/org/**"]


def test_the_repo_role_table_keeps_alice_able_to_run_the_demo():
    from pathlib import Path

    from kairos_contracts.util import has_capability

    stub = RolePermissions.from_dir(Path(__file__).resolve().parents[2] / "policies")
    alice = asyncio.run(stub.resolve("alice", "acme"))
    for cap in ("knowledge.read", "knowledge.search", "agent.spawn", "jira.read", "jira.write", "fs.write", "browser.open"):
        assert has_capability(cap, alice.capabilities), cap
    assert alice.data_scopes == ["/org/**"]
