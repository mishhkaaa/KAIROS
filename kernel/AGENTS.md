# kernel/ — owner P1 (Kernel & Execution). Brief: shared/services/P1-kernel-execution.md
- Implements: EventBus, PolicyEngine, AuditLog, KernelAgentContext (the AgentContext ABI), lifecycle, syscalls, approvals, transactions, persistence, the gateway (must match shared/api/openapi.json), and the ai-* CLI.
- Consume other splits ONLY via `services: ServiceBundle` (see kairos_contracts.wiring). Develop on `kairos_contracts.testing.fakes.fake_bundle()`.
- The process state machine is `kairos_contracts.schema.ALLOWED_TRANSITIONS`. Never bypass it.
- Tests: `uv run pytest kernel/tests tests/integration -rs`.
