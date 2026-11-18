"""Reusable conversation starters; each module exposes register(mcp)."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import funding_landscape


def register_prompts(mcp: MCPServer) -> None:
    funding_landscape.register(mcp)
