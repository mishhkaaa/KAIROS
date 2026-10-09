"""ToolExecutor: dispatches invocations to native / mcp / browser / sandbox backends.

Owner: P1 — Kernel & Execution

TODO:
  - [x] list_tools aggregates all backends; execute/verify/rollback per operation
  - [x] enforce invocation.constraints (network_allow, timeout); publish tool.started/tool.completed
"""
