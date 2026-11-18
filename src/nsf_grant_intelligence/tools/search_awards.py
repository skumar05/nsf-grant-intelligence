"""Tool: Search NSF awards."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .. import api
from ..models import (
    AwardSearchResult,
    AwardSummary,
    DateMMDDYYYY,
    FirstName,
    Keyword,
    Page,
    PerPage,
    ProgramName,
    StateCode,
)
from ..transform import trim_award
from ._common import read_only


async def search_awards(
    keyword: Keyword = "",
    pi_first_name: FirstName = "",
    pi_last_name: Annotated[str, Field(description="PI last name. Optional.")] = "",
    awardee_name: Annotated[str, Field(description="Institution name, e.g. 'Carnegie Mellon'.")] = "",
    awardee_city: Annotated[
        str, Field(description="Institution city. Matching is loose (any word of the city).")
    ] = "",
    awardee_state_code: StateCode = "",
    fund_program_name: ProgramName = "",
    active_only: Annotated[bool, Field(description="Only currently active awards.")] = False,
    start_date_start: DateMMDDYYYY = "",
    start_date_end: DateMMDDYYYY = "",
    page: Page = 1,
    per_page: PerPage = 10,
) -> AwardSearchResult:
    """Search NSF awards with any combination of filters; returns a page of award summaries.

    Use this to list individual awards (open-ended lookups, one institution's awards,
    one PI's awards). For one known award ID use get_award; for a researcher's totals
    use pi_track_record; for an institution's totals use institution_profile.
    Results are newest start date first, not ranked by relevance.
    """
    params = {"printFields": api.LIST_FIELDS, **api.page_params(page, per_page)}
    filters = {
        "keyword": keyword,
        "piFirstName": pi_first_name,
        "piLastName": pi_last_name,
        "awardeeName": api.phrase(awardee_name) if awardee_name else "",
        "awardeeCity": awardee_city,
        "awardeeStateCode": awardee_state_code,
        "fundProgramName": fund_program_name,
        "startDateStart": start_date_start,
        "startDateEnd": start_date_end,
    }
    params.update({k: v for k, v in filters.items() if v})
    if active_only:
        params["ActiveAwards"] = "true"  # API ignores lowercase "activeAwards"

    resp = await api.request(params)
    awards = resp.get("award", [])
    return AwardSearchResult(
        page=page,
        per_page=per_page,
        total_count=api.total_count(resp),
        results_on_page=len(awards),
        awards=[AwardSummary(**trim_award(a)) for a in awards],
    )


def register(mcp: MCPServer) -> None:
    mcp.tool(annotations=read_only("Search NSF awards"))(search_awards)
