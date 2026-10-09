"""Process table: PID allocation, AgentProcess records, parent/child tree, state machine.

Owner: P1 — Kernel & Execution

TODO:
  - [x] ProcessTable.create/get/list/tree; PIDs start at 101 and are never reused
  - [x] transition(pid, new_state) enforces kairos_contracts.schema.ALLOWED_TRANSITIONS (else INVALID_STATE_TRANSITION)
  - [x] every transition publishes process.state_changed and writes an AuditKind.STATE entry
"""
