"""Tool: Sample winning abstracts."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .. import sampling
from ..models import FromYear, ProgramName, WinningAbstract, WinningAbstracts
from ..transform import pi_name, to_int
from ._common import read_only


async def sample_winning_abstracts(
    keyword: Annotated[str, Field(min_length=1, description="Topic to sample abstracts for.")],
    fund_program_name: ProgramName = "",
    from_year: FromYear = 2020,
    n: Annotated[int, Field(ge=1, le=20, description="How many abstracts to return.")] = 5,
) -> WinningAbstracts:
    """Full abstracts, PIs and amounts of the largest recent awards on a topic,
    to study how funded proposals are written."""
    awards = await sampling.collect(keyword, fund_program_name, from_year, max_awards=max(n * 3, 25))
    # prefer the largest awards — they passed the toughest review
    awards.sort(key=lambda a: to_int(a.get("fundsObligatedAmt")) or 0, reverse=True)
    return WinningAbstracts(
        keyword=keyword,
        samples=[
            WinningAbstract(
                award_id=a.get("id"),
                title=a.get("title"),
                pi=pi_name(a),
                institution=a.get("awardeeName"),
                funds_obligated_usd=to_int(a.get("fundsObligatedAmt")),
                program=a.get("fundProgramName"),
                start_date=a.get("startDate"),
                abstract=(a.get("abstractText") or "").strip(),
            )
            for a in awards[:n]
        ],
    )


def register(mcp: MCPServer) -> None:
    mcp.tool(annotations=read_only("Sample winning abstracts"))(sample_winning_abstracts)
