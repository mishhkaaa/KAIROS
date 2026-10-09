"""AI syscall gateway: SyscallRequest -> policy -> approval -> transaction.

Owner: P1 — Kernel & Execution

TODO:
  - [x] validate tool/operation exists (ToolExecutor.list_tools) and capability matches the operation
  - [x] PolicyEngine.evaluate; ALLOW -> transactions; REQUIRES_APPROVAL -> approvals (pid WAITING); DENY -> SyscallResult(DENIED)
  - [x] publish syscall.requested / syscall.decided / syscall.completed
"""
