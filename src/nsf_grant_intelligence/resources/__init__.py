"""Data the client can read directly; each module exposes register(mcp)."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import api_notes


def register_resources(mcp: MCPServer) -> None:
    api_notes.register(mcp)
