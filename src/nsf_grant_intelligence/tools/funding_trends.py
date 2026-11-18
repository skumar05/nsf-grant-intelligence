"""Tool: Funding trends by year."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .. import api, sampling
from ..models import FromYear, FundingTrends, Keyword, ProgramName, YearFunding
from ..transform import to_int
from ._common import read_only


async def funding_trends(
    keyword: Keyword = "",
    fund_program_name: ProgramName = "",
    from_year: FromYear = 2015,
    to_year: Annotated[
        int | None,
        Field(ge=1950, le=2100, description="Last start year; defaults to next year."),
    ] = None,
    max_pages: Annotated[
        int, Field(ge=1, le=20, description="Sampling budget: pages of 25 awards across all years.")
    ] = 8,
) -> FundingTrends:
    """Award count and funding per start year for a topic or program.

    Queries each year separately, so every year in the range is represented.
    "awards" is the exact count the API reports for that year (capped at
    10,000); the dollar figures come from a sample of up to
    max_pages x 25 awards shared across the years, so treat them as indicative.
    """
    years = sampling.year_range(from_year, to_year)
    pages_per_year = max(1, max_pages // len(years))
    by_year: dict[int, YearFunding] = {}
    scanned = 0
    for year in years:
        sampled = funds = 0
        total = None
        for page in range(1, pages_per_year + 1):
            params = {
                "printFields": "id,startDate,fundsObligatedAmt",
                "startDateStart": f"01/01/{year}",
                "startDateEnd": f"12/31/{year}",
                **api.page_params(page, api.RPP),
                **api.text_filters(keyword, fund_program_name),
            }
            resp = await api.request(params)
            if total is None:
                total = api.total_count(resp)
            awards = resp.get("award", [])
            sampled += len(awards)
            funds += sum(to_int(a.get("fundsObligatedAmt")) or 0 for a in awards)
            if len(awards) < api.RPP:
                break
        scanned += sampled
        if total or sampled:
            by_year[year] = YearFunding(
                awards=total if total is not None else sampled,
                sampled_awards=sampled,
                sampled_funds_obligated_usd=funds,
            )
    return FundingTrends(
        keyword=keyword or None,
        fund_program_name=fund_program_name or None,
        years=by_year,
        awards_scanned=scanned,
        note="Award counts are exact per year (max 10,000); dollar totals are sampled.",
    )


def register(mcp: MCPServer) -> None:
    mcp.tool(annotations=read_only("Funding trends by year"))(funding_trends)
