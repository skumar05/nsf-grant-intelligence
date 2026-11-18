"""Tool: Analyze a funding topic."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .. import sampling
from ..models import FromYear, ProgramName, TopicAnalysis
from ..transform import award_stats
from ._common import counts, read_only


async def analyze_topic(
    keyword: Annotated[str, Field(min_length=1, description='Topic, e.g. "quantum sensing".')],
    fund_program_name: ProgramName = "",
    from_year: FromYear = 2020,
    max_awards: Annotated[
        int, Field(ge=1, le=300, description="Sample size, spread evenly across start years.")
    ] = 100,
) -> TopicAnalysis:
    """What NSF funds for a topic: total and median funding, top programs,
    institutions and PIs, and awards per start year (sampled, not a census)."""
    awards = await sampling.collect(keyword, fund_program_name, from_year, max_awards)
    s = award_stats(awards)
    return TopicAnalysis(
        keyword=keyword,
        fund_program_name=fund_program_name or None,
        from_year=from_year,
        awards_analyzed=s["awards_analyzed"],
        total_funds_obligated_usd=s["total_funds_obligated_usd"],
        median_award_usd=s["median_award_usd"],
        top_programs=counts(s["top_programs"]),
        top_institutions=counts(s["top_institutions"]),
        top_pis=counts(s["top_pis"]),
        awards_by_start_year=s["awards_by_start_year"],
    )


def register(mcp: MCPServer) -> None:
    mcp.tool(annotations=read_only("Analyze a funding topic"))(analyze_topic)
