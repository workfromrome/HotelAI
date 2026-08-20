"""Compatibility entry point for the canonical MCP server.

Not the documented way to start the server anymore (README/AGENTS.md both point to
`python -m mcp_server.server`) — kept only in case something still imports this path.
"""
from mcp_server.server import mcp, search_hotels

if __name__ == "__main__":
    mcp.run()
