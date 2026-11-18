"""One file per tool; each exposes register(mcp)."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import (
    analyze_topic,
    compare_funding_by_program,
    extract_themes,
    funding_trends,
    get_award,
    institution_profile,
    pi_track_record,
    sample_winning_abstracts,
    search_awards,
)


def register_tools(mcp: MCPServer) -> None:
    search_awards.register(mcp)
    get_award.register(mcp)
    institution_profile.register(mcp)
    funding_trends.register(mcp)
    analyze_topic.register(mcp)
    sample_winning_abstracts.register(mcp)
    compare_funding_by_program.register(mcp)
    pi_track_record.register(mcp)
    extract_themes.register(mcp)
