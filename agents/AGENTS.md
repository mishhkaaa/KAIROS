# agents/ — owner P3, EXCEPT `kairos_agents/adapters/` (NOOA adapter, owner P2, stretch)
- Agent code imports ONLY `kairos_contracts` and `kairos_agents.sdk`. All effects go through `ctx: AgentContext`.
- Unit-test every agent with `kairos_contracts.testing.fakes.FakeAgentContext` (no kernel, no GPU needed).
- Agents must survive garbage LLM output (the fake model returns placeholders): never raise, return AgentResult(status=failed) instead.
- Brief: shared/services/P3-agents-models.md
