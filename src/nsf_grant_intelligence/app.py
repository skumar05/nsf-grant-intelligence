"""MCP server entry point. Keep this file thin.

It creates the server, registers everything from the submodules, and picks a transport:
  tools/      one file per tool (each exposes register(mcp))
  prompts/    reusable conversation starters
  resources/  data the client can read directly
  routes.py   HTTP-only routes (landing page, /health, /version)
  config.py   settings from environment variables or .env
  models.py   Pydantic input types and structured outputs
  api.py, sampling.py, transform.py   NSF API client, per-year sampling, pure helpers

Run (stdio; point an MCP client at this command):
    .venv/bin/python -m nsf_grant_intelligence
"""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

from . import __version__
from .config import Settings, settings
from .prompts import register_prompts
from .resources import register_resources
from .routes import register_routes
from .tools import register_tools

mcp = MCPServer(
    "nsf-grant-intelligence",
    version=__version__,
    instructions=(
        "Search and analyze National Science Foundation (NSF) awards via the public NSF Award API. "
        "Use get_award for one award ID, search_awards to list awards, pi_track_record and "
        "institution_profile for a researcher or institution, and the analysis tools for topics. "
        "Only NSF awards are covered. The analysis tools work on samples; read the "
        "nsf://api-notes resource for coverage and limits."
    ),
)

register_tools(mcp)
register_prompts(mcp)
register_resources(mcp)
register_routes(mcp)


def run_args(env: dict[str, str], config: Settings) -> tuple[str, dict]:
    """Choose the transport. A platform-injected port wins, then MCP_TRANSPORT, else stdio."""
    platform_port = env.get("DATABRICKS_APP_PORT") or env.get("PORT")
    if platform_port:
        return "streamable-http", {"host": "0.0.0.0", "port": int(platform_port), "stateless_http": True}
    if config.mcp_transport == "streamable-http":
        return "streamable-http", {"host": config.mcp_host, "port": config.mcp_port, "stateless_http": True}
    return "stdio", {}


def main() -> None:
    transport, kwargs = run_args(dict(os.environ), settings)
    mcp.run(transport, **kwargs)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
