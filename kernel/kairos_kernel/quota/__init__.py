"""Resource quotas: tokens, tool calls, wall clock, children, GPU share.

Owner: P1 — Kernel & Execution

TODO:
  - [x] charge usage on every ctx.llm / ctx.syscall / ctx.spawn; raise QUOTA_EXCEEDED
  - [x] publish process.usage periodically for ai-top / UI
"""
