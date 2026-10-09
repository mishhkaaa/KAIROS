"""MCP client adapter: MCP servers -> ToolSpec + execution (blueprint §26). MCP is transport, not the security boundary.

Owner: P1 — Kernel & Execution

TODO:
  - [x] discover tools from configured MCP servers (stdio/http) -> ToolSpec(transport=mcp)
  - [x] invoke with invocation.constraints enforced; map errors to ToolResult(status=error)
"""
