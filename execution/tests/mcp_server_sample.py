"""Tiny MCP server used by the MCP adapter tests (stdio transport)."""
from mcp.server.mcpserver import MCPServer

server = MCPServer("notes")
NOTES: list[str] = []


@server.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@server.tool()
def save_note(text: str) -> str:
    """Store a note and return how many notes exist."""
    NOTES.append(text)
    return f"{len(NOTES)} notes"


@server.tool()
def explode() -> str:
    """Always fails."""
    raise ValueError("kaboom")


if __name__ == "__main__":
    server.run("stdio")
