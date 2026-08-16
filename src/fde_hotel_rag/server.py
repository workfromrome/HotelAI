"""Compatibility entry point for the canonical MCP server."""
from mcp_server.server import mcp, search_hotels

if __name__ == "__main__":
    mcp.run()
