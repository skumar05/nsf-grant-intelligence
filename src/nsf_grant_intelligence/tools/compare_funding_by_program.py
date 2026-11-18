"""Tool: Compare funding by program."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .. import sampling
from ..models import FromYear, ProgramComparison, ProgramFunding
from ..transform import to_int
from ._common import read_only


async def compare_funding_by_program(
    keyword: Annotated[str, Field(min_length=1, description="Topic to find funding programs for.")],
    from_year: FromYear = 2020,
    max_awards: Annotated[
        int, Field(ge=1, le=300, description="Sample size, spread evenly across start years.")
    ] = 150,
) -> ProgramComparison:
    """Which NSF programs fund a topic, ranked by dollars: where to submit a proposal."""
    awards = await sampling.collect(keyword, "", from_year, max_awards)
    by_prog: dict[str, dict] = {}
    for a in awards:
        p = a.get("fundProgramName") or "Unknown"
        amt = to_int(a.get("fundsObligatedAmt")) or 0
        b = by_prog.setdefault(p, {"awards": 0, "funds_obligated_usd": 0})
        b["awards"] += 1
        b["funds_obligated_usd"] += amt
    ranked = sorted(by_prog.items(), key=lambda kv: kv[1]["funds_obligated_usd"], reverse=True)
    return ProgramComparison(
        keyword=keyword,
        from_year=from_year,
        awards_scanned=len(awards),
        programs=[ProgramFunding(program=p, **v) for p, v in ranked[:10]],
    )


def register(mcp: MCPServer) -> None:
    mcp.tool(annotations=read_only("Compare funding by program"))(compare_funding_by_program)
