"""Script to run the Apollo scenario through the P3 Agents & Models implementation."""
import asyncio

from kairos_agents.factory import build_agent_registry, build_agent_runtime
from kairos_contracts.schema import AgentResult
from kairos_contracts.testing.fakes import FakeAgentContext, fake_bundle
from kairos_contracts.wiring import Settings
from kairos_models.factory import build_model_router


async def main():
    settings = Settings.from_env()
    bundle = fake_bundle(settings)
    
    # Overwrite the fakes with real P3 implementations
    print("Building P3 components...")
    bundle.models = build_model_router(settings, bundle)
    bundle.agent_registry = build_agent_registry(settings, bundle)
    bundle.agent_runtime = build_agent_runtime(settings, bundle)
    
    registry = bundle.agent_registry
    runtime = bundle.agent_runtime
    
    try:
        planner_manifest = await registry.get("planner-agent")
    except Exception as e:
        print(f"Failed to load planner manifest: {e}")
        return

    print("Components built successfully.\n")

    # Define the child runner that invokes real runtime
    async def child_runner(agent_name: str, goal: str, inputs: dict) -> AgentResult:
        manifest = await registry.get(agent_name)
        child_ctx = FakeAgentContext(
            task_id="T-apollo",
            manifest=manifest,
            inputs=inputs,
            child_runner=child_runner,
            okf_dir=settings.okf_dir,
            auto_approve=True
        )
        child_ctx.models = bundle.models
        child_ctx.knowledge = bundle.knowledge
        child_ctx.tools = bundle.tools
        return await runtime.run(manifest, goal, child_ctx)

    # Setup the root context for the planner
    root_ctx = FakeAgentContext(
        task_id="T-apollo",
        manifest=planner_manifest,
        child_runner=child_runner,
        okf_dir=settings.okf_dir,
        auto_approve=True
    )
    root_ctx.models = bundle.models
    root_ctx.knowledge = bundle.knowledge
    root_ctx.tools = bundle.tools
    
    goal = (
        "Investigate why Project Apollo is over budget and six weeks behind schedule. "
        "Identify root causes, update the tracker, and prepare a recovery plan."
    )
    
    print(f"Starting E2E P3 Run for Apollo Scenario...\nGoal: {goal}\n")
    print("This will call the local Ollama LLMs to generate a plan, spawn sub-agents, and synthesize.")
    print("Please wait, this might take a minute...\n")
    
    result = await runtime.run(planner_manifest, goal, root_ctx)
    
    print("\n" + "="*50)
    print("--- Final Agent Result ---")
    print(f"Status: {result.status}")
    print(f"Summary: {result.summary}")
    print("\nOutput Data:")
    import json
    print(json.dumps(result.output, indent=2))
    
    print("\n--- Planner Logs ---")
    for log in root_ctx.logs:
        print(f"[{log[0]}] {log[1]}")

if __name__ == "__main__":
    asyncio.run(main())
