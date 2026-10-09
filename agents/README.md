# agents/ — P3 Agents (`kairos_agents`); `adapters/` (NOOA, stretch) is P2's
Agent SDK, runtime, registry (`manifests/*.yaml`), A2A helpers, prompts, and the agents: planner, finance, engineering, research, action.

- **Brief (with code skeletons):** [shared/services/P3-agents-models.md](../shared/services/P3-agents-models.md)
- Unit-test agents with `FakeAgentContext`; agent code imports only `kairos_contracts` and `kairos_agents.sdk`.

```bash
uv run pytest agents/tests -rs
```
