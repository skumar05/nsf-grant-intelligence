"""Tool: Institution funding profile."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .. import api, sampling
from ..models import FromYear, InstitutionProfile
from ..transform import award_stats
from ._common import counts, read_only


async def institution_profile(
    name: Annotated[str, Field(min_length=1, description='Institution name, e.g. "Carnegie Mellon".')],
    keyword: Annotated[str, Field(description="Optional topic to focus on, e.g. 'robotics'.")] = "",
    from_year: FromYear = 2020,
    max_awards: Annotated[
        int, Field(ge=1, le=300, description="Sample size, spread evenly across start years.")
    ] = 100,
) -> InstitutionProfile:
    """How an institution does at NSF: funding totals, top programs, most-funded
    PIs and awards per year, optionally for one topic (sampled, not a census).

    To list that institution's individual awards, use search_awards with awardee_name.
    """
    awards = await sampling.collect(
        keyword, "", from_year, max_awards, extra_filters={"awardeeName": api.phrase(name)}
    )
    s = award_stats(awards)
    return InstitutionProfile(
        institution=name,
        keyword=keyword or None,
        from_year=from_year,
        awards_analyzed=s["awards_analyzed"],
        total_funds_obligated_usd=s["total_funds_obligated_usd"],
        median_award_usd=s["median_award_usd"],
        institution_names_matched=counts(s["top_institutions"]),
        top_programs=counts(s["top_programs"]),
        top_pis=counts(s["top_pis"]),
        awards_by_start_year=s["awards_by_start_year"],
    )


def register(mcp: MCPServer) -> None:
    mcp.tool(annotations=read_only("Institution funding profile"))(institution_profile)
