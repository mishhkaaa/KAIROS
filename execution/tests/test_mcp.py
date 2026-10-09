"""MCP adapter against a real MCP server subprocess (execution/tests/mcp_server_sample.py)."""
import asyncio
import sys
from pathlib import Path

from kairos_contracts.schema import ToolInvocation, ToolResultStatus, ToolTransport
from kairos_contracts.schema.common import new_id
from kairos_execution.mcp.backend import McpBackend, McpServerConfig, load_mcp_config
from kairos_execution.tools.executor import Executor

SERVER = Path(__file__).with_name("mcp_server_sample.py")


def config(**kw) -> McpServerConfig:
    return McpServerConfig(name="notes", command=sys.executable, args=[str(SERVER)], timeout_s=30, **kw)


def inv(op: str, **args) -> ToolInvocation:
    return ToolInvocation(invocation_id=new_id("INV"), syscall_id=new_id("SC"), task_id="T-mcp", pid=105, tool="notes",
                          operation=op, arguments=args)


def test_mcp_tools_are_discovered_and_callable():
    backend = McpBackend(config())
    executor = Executor([backend])

    async def go():
        try:
            specs = await executor.list_tools()
            added = await executor.execute(inv("add", a=2, b=3))
            saved = [await executor.execute(inv("save_note", text=f"n{i}")) for i in range(2)]
            failed = await executor.execute(inv("explode"))
            missing = await executor.execute(inv("nope"))
            return specs, added, saved, failed, missing
        finally:
            await executor.aclose()

    specs, added, saved, failed, missing = asyncio.run(go())
    spec = specs[0]
    assert spec.name == "notes" and spec.transport == ToolTransport.MCP
    assert {o.name for o in spec.operations} == {"add", "save_note", "explode"}
    assert all(o.capability == "mcp.call" for o in spec.operations)
    assert spec.operations[0].input_schema.get("properties")
    assert added.status == ToolResultStatus.SUCCESS and added.output["content"] == ["5"]
    assert saved[1].output["content"] == ["2 notes"], "one persistent session keeps server state"
    assert failed.status == ToolResultStatus.ERROR and failed.error.code == "TOOL_FAILED"
    assert "explode" in failed.error.message  # MCP 2.x hides internal exception details from clients
    assert missing.error.code == "NOT_FOUND"


def test_broken_server_does_not_break_list_tools():
    broken = McpBackend(McpServerConfig(name="broken", command=sys.executable, args=["-c", "import sys; sys.exit(3)"]))
    ok = McpBackend(config())
    executor = Executor([broken, ok])

    async def go():
        try:
            return await executor.list_tools()
        finally:
            await executor.aclose()

    assert [s.name for s in asyncio.run(go())] == ["notes"]


def test_config_file(tmp_path, monkeypatch):
    f = tmp_path / "mcp.yaml"
    f.write_text("servers:\n  - {name: notes, command: python, args: [server.py], capability: notes.call, risk: high}\n")
    monkeypatch.setenv("KAIROS_MCP_CONFIG", str(f))
    [cfg] = load_mcp_config()
    assert cfg.capability == "notes.call" and cfg.risk.value == "high" and cfg.args == ["server.py"]
    monkeypatch.delenv("KAIROS_MCP_CONFIG")
    assert load_mcp_config() == []


def test_mcp_through_the_kernel_with_approval(tmp_path):
    """Agent → ctx.syscall(notes.add) → YAML policy (approval required) → approve → MCP call → commit."""
    from kairos_contracts.schema import SyscallRequest, SyscallStatus
    from kairos_contracts.testing.fakes import FakeAgentRegistry, fake_bundle
    from kairos_contracts.wiring import Settings
    from kairos_kernel.config import KernelConfig
    from kairos_kernel.kernel import Kernel
    from kairos_kernel.policy.engine import YamlPolicyEngine
    from kairos_kernel.testing import ScriptedRuntime, done, manifest, start_task

    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "mcp.yaml").write_text("policy: mcp-v1\npriority: 1\napplies_to: {agents: ['*']}\n"
                                       "tools: {allow: [mcp.call]}\napproval: {mcp.call: required}\n")
    results = []

    async def agent(goal, ctx):
        res = await ctx.syscall(SyscallRequest(syscall_id=new_id("SC"), task_id=ctx.task_id, pid=ctx.pid,
                                               capability="mcp.call", tool="notes", operation="add",
                                               arguments={"a": 20, "b": 22}))
        results.append(res)
        return done(ctx, res.tool_result.output["content"][0] if res.tool_result else res.status.value)

    settings = Settings(data_dir=tmp_path / "data", policies_dir=policies)
    bundle = fake_bundle(settings)
    bundle.policy = YamlPolicyEngine(policies)
    bundle.tools = Executor([McpBackend(config())])
    bundle.agent_runtime = ScriptedRuntime({"planner-agent": agent})
    bundle.agent_registry = FakeAgentRegistry(manifests=[manifest("planner-agent", tools=["mcp.call"])])
    k = Kernel(settings, bundle, KernelConfig(policy_watch_interval_s=0))

    async def go():
        await k.boot()

        async def approve(ev):
            await k.approvals.resolve(ev.payload["approval_id"], True, "alice")

        k.bus.subscribe("approval.requested", approve)
        t = await k.tasks.wait_terminal(await start_task(k), timeout=60)
        await k.shutdown()
        return t

    t = asyncio.run(go())
    assert results[0].status == SyscallStatus.COMPLETED and t.result.summary == "42"
