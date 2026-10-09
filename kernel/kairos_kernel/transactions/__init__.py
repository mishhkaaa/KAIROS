"""Transactional actions: execute -> verify -> commit | rollback (blueprint §31).

Owner: P1 — Kernel & Execution

TODO:
  - [x] build ToolInvocation from the approved SyscallRequest + decision constraints
  - [x] ToolExecutor.execute -> verify -> commit (transaction.committed) or rollback (transaction.rolled_back)
  - [x] idempotency_key dedupe; audit TOOL/VERIFY/COMMIT/ROLLBACK entries
"""
