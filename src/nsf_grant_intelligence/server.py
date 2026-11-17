"""
NSF Grant Intelligence MCP server: tool definitions.

Wraps the public, keyless NSF Award API (https://api.nsf.gov/services/v1)
so an AI assistant can search 500k+ NSF awards, profile PIs and
institutions, analyze funding trends, and mine what actually gets funded.

Layout: api.py (HTTP + errors), sampling.py (per-year sampling),
transform.py (pure helpers), models.py (Pydantic inputs/outputs), this file (tools).

Run (stdio transport; point your MCP client at this command):
    .venv/bin/python -m nsf_grant_intelligence
"""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import api, sampling
from .models import (
    AwardDetail,
    AwardSearchResult,
    AwardSummary,
    DateMMDDYYYY,
    FirstName,
    FromYear,
    FundingTrends,
    InstitutionProfile,
    Keyword,
    LastName,
    NamedCount,
    Page,
    PerPage,
    PITrackRecord,
    ProgramComparison,
    ProgramFunding,
    ProgramName,
    StateCode,
    Themes,
    TopicAnalysis,
    WinningAbstract,
    WinningAbstracts,
    YearFunding,
)
from .transform import STOPWORDS, award_stats, pi_name, to_int, trim_award, year_of

PI_PAGES = 4  # pi_track_record scans up to this many pages of 25

mcp = MCPServer("nsf-grant-intelligence")

# Every tool only reads from a public third-party API.
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Liveness probe for load balancers and container platforms (HTTP transport only)."""
    return JSONResponse({"status": "ok"})


def _counts(pairs: list[tuple[str, int]]) -> list[NamedCount]:
    return [NamedCount(name=n, count=c) for n, c in pairs]


@mcp.tool(annotations=READ_ONLY)
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


@mcp.tool(annotations=READ_ONLY)
async def get_award(
    award_id: Annotated[str, Field(min_length=1, description='NSF award ID, e.g. "1753742".')],
) -> AwardDetail:
    """Full detail for one NSF award: complete abstract, directorate and award type."""
    resp = await api.request({"id": award_id, "printFields": api.DETAIL_FIELDS})
    awards = resp.get("award", [])
    if not awards:
        raise api.NSFAPIError(f"No award found with ID {award_id}")
    a = awards[0]
    return AwardDetail(
        **trim_award(a, abstract_len=0),
        abstract=a.get("abstractText"),
        program_detail=a.get("program"),
        nsf_directorate=a.get("orgLongName"),
        award_type=a.get("transType"),
    )


@mcp.tool(annotations=READ_ONLY)
async def institution_profile(
    name: Annotated[str, Field(min_length=1, description='Institution name, e.g. "Carnegie Mellon".')],
    keyword: Annotated[
        str, Field(description="Optional topic to focus on, e.g. 'robotics'.")
    ] = "",
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
        institution_names_matched=_counts(s["top_institutions"]),
        top_programs=_counts(s["top_programs"]),
        top_pis=_counts(s["top_pis"]),
        awards_by_start_year=s["awards_by_start_year"],
    )


@mcp.tool(annotations=READ_ONLY)
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


@mcp.tool(annotations=READ_ONLY)
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
        top_programs=_counts(s["top_programs"]),
        top_institutions=_counts(s["top_institutions"]),
        top_pis=_counts(s["top_pis"]),
        awards_by_start_year=s["awards_by_start_year"],
    )


@mcp.tool(annotations=READ_ONLY)
async def sample_winning_abstracts(
    keyword: Annotated[str, Field(min_length=1, description="Topic to sample abstracts for.")],
    fund_program_name: ProgramName = "",
    from_year: FromYear = 2020,
    n: Annotated[int, Field(ge=1, le=20, description="How many abstracts to return.")] = 5,
) -> WinningAbstracts:
    """Full abstracts, PIs and amounts of the largest recent awards on a topic,
    to study how funded proposals are written."""
    awards = await sampling.collect(
        keyword, fund_program_name, from_year, max_awards=max(n * 3, 25)
    )
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


@mcp.tool(annotations=READ_ONLY)
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
    ranked = sorted(
        by_prog.items(), key=lambda kv: kv[1]["funds_obligated_usd"], reverse=True
    )
    return ProgramComparison(
        keyword=keyword,
        from_year=from_year,
        awards_scanned=len(awards),
        programs=[ProgramFunding(program=p, **v) for p, v in ranked[:10]],
    )


@mcp.tool(annotations=READ_ONLY)
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
        pi_names_matched=_counts(Counter(pi_name(a) for a in awards).most_common(5)),
        programs=_counts(
            Counter(a.get("fundProgramName") or "Unknown" for a in awards).most_common(5)
        ),
        institutions=_counts(
            Counter(a.get("awardeeName") or "Unknown" for a in awards).most_common(3)
        ),
        year_span=[years[0], years[-1]] if years else None,
        recent_awards=[AwardSummary(**trim_award(a, abstract_len=0)) for a in awards[:5]],
    )


@mcp.tool(annotations=READ_ONLY)
async def extract_themes(
    keyword: Annotated[str, Field(min_length=1, description="Topic to mine abstracts for.")],
    fund_program_name: ProgramName = "",
    from_year: FromYear = 2020,
    n: Annotated[int, Field(ge=1, le=100, description="Number of abstracts to scan.")] = 40,
) -> Themes:
    """Most frequent substantive terms across funded abstracts on a topic:
    the vocabulary successful proposals share."""
    awards = await sampling.collect(keyword, fund_program_name, from_year, max_awards=n)
    counts: Counter = Counter()
    for a in awards:
        text = (a.get("abstractText") or "").lower()
        for tok in re.findall(r"[a-z]{3,}", text):
            if tok not in STOPWORDS:
                counts[tok] += 1
    return Themes(
        keyword=keyword,
        abstracts_scanned=len(awards),
        top_terms=_counts(counts.most_common(25)),
    )


def main() -> None:
    """Run over stdio by default; set MCP_TRANSPORT=streamable-http to host it.

    Hosted config (all optional): HOST (default 0.0.0.0), PORT (default 8000).
    The MCP endpoint is served at /mcp, stateless so it scales horizontally.
    """
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
    else:
        mcp.run(
            transport,
            host=os.environ.get("HOST", "0.0.0.0"),
            port=int(os.environ.get("PORT", "8000")),
            stateless_http=True,
        )


if __name__ == "__main__":
    main()
