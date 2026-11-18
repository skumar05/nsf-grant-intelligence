"""Tool: PI track record."""

from __future__ import annotations

from collections import Counter

from mcp.server.mcpserver import MCPServer

from .. import api
from ..models import AwardSummary, FirstName, LastName, PITrackRecord
from ..transform import pi_name, to_int, trim_award, year_of
from ._common import counts, read_only

PI_PAGES = 4  # scans up to this many pages of 25


async def pi_track_record(last_name: LastName, first_name: FirstName = "") -> PITrackRecord:
    """Summary of a PI's NSF history: award count, total funding, programs,
    institutions and year span, from the 100 most recent matching awards.

    Use this for any "who is / how funded is researcher X" question; it also lists
    their 5 most recent awards. Give first_name when you can: a last name alone can
    match several people, which pi_names_matched makes visible.
    """
    awards: list[dict] = []
    total = None
    for page in range(1, PI_PAGES + 1):
        params = {
            "printFields": api.LIST_FIELDS,
            "piLastName": last_name,
            **api.page_params(page, api.RPP),
        }
        if first_name:
            params["piFirstName"] = first_name
        resp = await api.request(params)
        if total is None:
            total = api.total_count(resp)
        batch = resp.get("award", [])
        awards += batch
        if len(batch) < api.RPP:
            break
    amts = [x for x in (to_int(a.get("fundsObligatedAmt")) for a in awards) if x]
    years = sorted(y for y in (year_of(a.get("startDate")) for a in awards) if y)
    return PITrackRecord(
        pi=f"{first_name} {last_name}".strip(),
        awards_found=len(awards),
        total_matching_awards=total,
        total_funds_obligated_usd=sum(amts),
        pi_names_matched=counts(Counter(pi_name(a) for a in awards).most_common(5)),
        programs=counts(Counter(a.get("fundProgramName") or "Unknown" for a in awards).most_common(5)),
        institutions=counts(Counter(a.get("awardeeName") or "Unknown" for a in awards).most_common(3)),
        year_span=[years[0], years[-1]] if years else None,
        recent_awards=[AwardSummary(**trim_award(a, abstract_len=0)) for a in awards[:5]],
    )


def register(mcp: MCPServer) -> None:
    mcp.tool(annotations=read_only("PI track record"))(pi_track_record)
