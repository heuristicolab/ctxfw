"""
src/ctxfw/mcp_server.py — MCP Server Re-export and Entrypoint
Directly exposes MCPServer, CLI main, and protocol methods from ctxfw.mcp.
"""
from __future__ import annotations

from ctxfw.mcp import MCPServer, main

__all__ = [
    "MCPServer",
    "main",
]

if __name__ == "__main__":
    main()
