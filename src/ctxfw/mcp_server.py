# manifest_hash_v422_burst_guard: f1329ba99a93db6abeaa6f185ce40327ce2260c53f29ef770477ff1bf22a2546
"""
src/ctxfw/mcp_server.py — MCP Server Re-export and Entrypoint
Directly exposes MCPServer, CLI main, and protocol methods from ctxfw.mcp.
"""
from __future__ import annotations

from typing import Any

from ctxfw.mcp import MCPServer, main

__all__ = [
    "MCPServer",
    "main",
]


def __getattr__(name: str) -> Any:
    if name in ("McpBurstRateLimiter", "McpRateLimitPolicyDTO"):
        import ctxfw.mcp_guard as guard_pkg

        return getattr(guard_pkg, name)
    raise AttributeError(f"module 'ctxfw.mcp_server' has no attribute {name!r}")


if __name__ == "__main__":
    main()
