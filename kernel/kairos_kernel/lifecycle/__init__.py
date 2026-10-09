"""Agent lifecycle: spawn / run / pause / resume / kill / retry / checkpoint.

Owner: P1 — Kernel & Execution

TODO:
  - [x] spawn(SpawnRequest) -> AgentProcess: capabilities = child manifest ∩ policy (parent may only spawn agents in ITS manifest.capabilities.agents); start asyncio.Task running AgentRuntime.run
  - [x] kill = cancel the asyncio.Task (+ children) -> TERMINATED; pause/resume via ctx gate
  - [x] failure -> FAILED -> RETRYING (retry policy, attempt_count); resumes from the last checkpoint on retry
  - [x] human escalation after retries are exhausted (approval center: agent.retry); no separate fallback agent
  - [x] checkpoint(pid): ask agent via ctx.checkpoint state, persist Checkpoint; resume via AgentRuntime.restore
"""
