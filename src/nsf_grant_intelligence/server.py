"""
NSF Grant Intelligence MCP server.

Wraps the public, keyless NSF Award API (https://api.nsf.gov/services/v1)
so an AI assistant can search 500k+ NSF awards, profile PIs and
institutions, analyze funding trends, and mine what actually gets funded:
funding stats per topic, which programs back it, who wins repeatedly,
full abstracts of recent winners, and recurring themes in funded abstracts.

Run (stdio transport — point your MCP client at this command):
    .venv/bin/python -m nsf_grant_intelligence
"""

from __future__ import annotations

import os
import re
from collections import Counter
from datetime import date
from statistics import median

# Some environments put bracketed IPv6 literals (e.g. "[::1]") in no_proxy,
# which httpx fails to parse. Strip just those entries; proxying itself is
# otherwise left exactly as the environment configures it.
for _var in ("no_proxy", "NO_PROXY"):
    _val = os.environ.get(_var)
    if _val and "[" in _val:
        os.environ[_var] = ",".join(p for p in _val.split(",") if "[" not in p)

from typing import Annotated

import httpx
from pydantic import Field
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .models import (
    AwardDetail,
    AwardSearchResult,
    AwardSummary,
    DateMMDDYYYY,
    FirstName,
    FromYear,
    FundingTrends,
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

mcp = MCPServer("nsf-grant-intelligence")

# Every tool only reads from a public third-party API.
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)


class NSFAPIError(ToolError):
    """The NSF API failed or had nothing for the request.

    A ToolError, so its message reaches the model (other exceptions are hidden from it).
    """


BASE_URL = "https://api.nsf.gov/services/v1"
TIMEOUT = 30.0
RPP = 25  # API page-size cap

LIST_FIELDS = (
    "id,title,piFirstName,piLastName,pdPIName,awardeeName,awardeeCity,"
    "awardeeStateCode,fundsObligatedAmt,estimatedTotalAmt,startDate,expDate,"
    "fundProgramName,primaryProgram"
)
DETAIL_FIELDS = LIST_FIELDS + ",abstractText,program,orgLongName,transType"
ABSTRACT_FIELDS = LIST_FIELDS + ",abstractText"

STOPWORDS = set(
    """
    a an the and or of to in for on with as by at from into through during
    between out over under within without about than then so such
    no nor not only own same these those this that will shall may can could
    would should must have has had having are was were been being is it its
    we our us they their them he she his her you your i me my
    also which who whom whose what when where why how all any both each few
    more most other some too very one two three first new using used use
    based upon across high low large small major key core main primary
    research project study program proposal award grant funded funding science
    scientific nsf foundation national develop developed development provide
    provides support supported including include includes significant advance
    advances novel innovative address addresses aim aims goal goals objective
    objectives impact broader merit intellectual work activities outcomes
    """.split()
)


def _to_int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _year(d: str | None) -> int | None:
    # API dates look like "03/15/2027"
    try:
        return int(d.split("/")[-1])
    except (AttributeError, ValueError, IndexError):
        return None


def _pi_name(a: dict) -> str:
    pi = f"{a.get('piFirstName') or ''} {a.get('piLastName') or ''}".strip()
    return pi or (a.get("pdPIName") or "Unknown")


def _trim(a: dict, abstract_len: int = 280) -> dict:
    """Compact one award for list views (keeps context small)."""
    pi = f"{a.get('piFirstName') or ''} {a.get('piLastName') or ''}".strip()
    out = {
        "award_id": a.get("id"),
        "title": a.get("title"),
        "pi": pi or a.get("pdPIName"),
        "institution": a.get("awardeeName"),
        "location": ", ".join(
            x for x in (a.get("awardeeCity"), a.get("awardeeStateCode")) if x
        ),
        "funds_obligated_usd": _to_int(a.get("fundsObligatedAmt")),
        "estimated_total_usd": _to_int(a.get("estimatedTotalAmt")),
        "start_date": a.get("startDate"),
        "end_date": a.get("expDate"),
        "program": a.get("fundProgramName"),
    }
    if abstract_len and a.get("abstractText"):
        out["abstract_snippet"] = a["abstractText"][:abstract_len].strip()
    return out


async def _api(params: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(f"{BASE_URL}/awards.json", params=params)
            r.raise_for_status()
            return r.json().get("response", {})
    except httpx.HTTPError as e:
        raise NSFAPIError(f"NSF API request failed: {e}") from e


def _page_params(page: int, per_page: int) -> dict:
    per_page = max(1, min(per_page, 25))  # API caps rpp at 25
    page = max(1, page)
    return {"rpp": per_page, "offset": (page - 1) * per_page}  # offset is 0-based


def _total_count(resp: dict) -> int | None:
    # API reports the full match count in response.metadata (caps at 10,000)
    return _to_int((resp.get("metadata") or {}).get("totalCount"))


async def _collect(
    keyword: str = "",
    fund_program_name: str = "",
    from_year: int = 2000,
    max_awards: int = 100,
    to_year: int | None = None,
) -> list[dict]:
    """Collect up to max_awards awards, spread evenly across start years.

    The API returns newest start date first, so a plain capped scan would
    fill up with the latest (often future-dated) awards. Instead each year in
    from_year..to_year gets its own quota and its own date-restricted query.
    to_year defaults to next year (NSF lists awards with future start dates).

    Raises NSFAPIError on API failure.
    """
    if to_year is None:
        to_year = date.today().year + 1
    years = list(range(from_year, max(from_year, to_year) + 1))
    quota = -(-max_awards // len(years))  # ceil: per-year share
    out: list[dict] = []
    for year in years:
        got = 0
        page = 0
        while got < quota:
            page += 1
            params = {
                "printFields": ABSTRACT_FIELDS,
                "startDateStart": f"01/01/{year}",
                "startDateEnd": f"12/31/{year}",
                **_page_params(page, RPP),
            }
            if keyword:
                params["keyword"] = keyword
            if fund_program_name:
                params["fundProgramName"] = fund_program_name
            resp = await _api(params)
            awards = resp.get("award", [])
            out.extend(awards[: quota - got])
            got += len(awards)
            if len(awards) < RPP:
                break
    return out[:max_awards]


def _stats(awards: list[dict]) -> dict:
    amts = [x for x in (_to_int(a.get("fundsObligatedAmt")) for a in awards) if x]
    years = Counter(_year(a.get("startDate")) for a in awards)
    years.pop(None, None)
    return {
        "awards_analyzed": len(awards),
        "total_funds_obligated_usd": sum(amts),
        "median_award_usd": int(median(amts)) if amts else None,
        "top_programs": Counter(
            a.get("fundProgramName") or "Unknown" for a in awards
        ).most_common(5),
        "top_institutions": Counter(
            a.get("awardeeName") or "Unknown" for a in awards
        ).most_common(5),
        "top_pis": Counter(_pi_name(a) for a in awards).most_common(5),
        "awards_by_start_year": dict(sorted(years.items())),
    }


def _counts(pairs: list[tuple[str, int]]) -> list[NamedCount]:
    return [NamedCount(name=n, count=c) for n, c in pairs]


@mcp.tool(annotations=READ_ONLY)
async def search_awards(
    keyword: Keyword = "",
    pi_first_name: FirstName = "",
    pi_last_name: Annotated[str, Field(description="PI last name. Optional.")] = "",
    awardee_name: Annotated[str, Field(description="Institution name, e.g. 'Carnegie Mellon'.")] = "",
    awardee_city: Annotated[str, Field(description="Institution city.")] = "",
    awardee_state_code: StateCode = "",
    fund_program_name: ProgramName = "",
    active_only: Annotated[bool, Field(description="Only currently active awards.")] = False,
    start_date_start: DateMMDDYYYY = "",
    start_date_end: DateMMDDYYYY = "",
    page: Page = 1,
    per_page: PerPage = 10,
) -> AwardSearchResult:
    """Search NSF awards with any combination of filters; returns a page of award summaries.

    Use this for open-ended lookups. For one PI's history use awards_by_pi; for one
    institution use awards_by_institution; for one known award ID use get_award.
    Results are newest start date first, not ranked by relevance.
    """
    params = {"printFields": LIST_FIELDS, **_page_params(page, per_page)}
    filters = {
        "keyword": keyword,
        "piFirstName": pi_first_name,
        "piLastName": pi_last_name,
        "awardeeName": awardee_name,
        "awardeeCity": awardee_city,
        "awardeeStateCode": awardee_state_code,
        "fundProgramName": fund_program_name,
        "startDateStart": start_date_start,
        "startDateEnd": start_date_end,
    }
    params.update({k: v for k, v in filters.items() if v})
    if active_only:
        params["ActiveAwards"] = "true"  # API ignores lowercase "activeAwards"

    resp = await _api(params)
    awards = resp.get("award", [])
    return AwardSearchResult(
        page=page,
        per_page=per_page,
        total_count=_total_count(resp),
        results_on_page=len(awards),
        awards=[AwardSummary(**_trim(a)) for a in awards],
    )


@mcp.tool(annotations=READ_ONLY)
async def get_award(
    award_id: Annotated[str, Field(min_length=1, description='NSF award ID, e.g. "1753742".')],
) -> AwardDetail:
    """Full detail for one NSF award: complete abstract, directorate and award type."""
    resp = await _api({"id": award_id, "printFields": DETAIL_FIELDS})
    awards = resp.get("award", [])
    if not awards:
        raise NSFAPIError(f"No award found with ID {award_id}")
    a = awards[0]
    return AwardDetail(
        **_trim(a, abstract_len=0),
        abstract=a.get("abstractText"),
        program_detail=a.get("program"),
        nsf_directorate=a.get("orgLongName"),
        award_type=a.get("transType"),
    )


@mcp.tool(annotations=READ_ONLY)
async def awards_by_pi(
    last_name: LastName, first_name: FirstName = "", page: Page = 1, per_page: PerPage = 10
) -> AwardSearchResult:
    """List awards for a principal investigator, newest first (paged).

    For a summary of totals, programs and span, use pi_track_record instead.
    """
    return await search_awards(
        pi_first_name=first_name, pi_last_name=last_name, page=page, per_page=per_page
    )


@mcp.tool(annotations=READ_ONLY)
async def awards_by_institution(
    name: Annotated[str, Field(min_length=1, description='Institution name, e.g. "Carnegie Mellon".')],
    state_code: StateCode = "",
    active_only: Annotated[bool, Field(description="Only currently active awards.")] = False,
    page: Page = 1,
    per_page: PerPage = 10,
) -> AwardSearchResult:
    """List NSF awards to an institution, newest first (paged)."""
    return await search_awards(
        awardee_name=name,
        awardee_state_code=state_code,
        active_only=active_only,
        page=page,
        per_page=per_page,
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
    if to_year is None:
        to_year = date.today().year + 1
    years = list(range(from_year, max(from_year, to_year) + 1))
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
                **_page_params(page, RPP),
            }
            if keyword:
                params["keyword"] = keyword
            if fund_program_name:
                params["fundProgramName"] = fund_program_name
            resp = await _api(params)
            if total is None:
                total = _total_count(resp)
            awards = resp.get("award", [])
            sampled += len(awards)
            funds += sum(_to_int(a.get("fundsObligatedAmt")) or 0 for a in awards)
            if len(awards) < RPP:
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
    awards = await _collect(keyword, fund_program_name, from_year, max_awards)
    s = _stats(awards)
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
    awards = await _collect(
        keyword, fund_program_name, from_year, max_awards=max(n * 3, 25)
    )
    # prefer the largest awards — they passed the toughest review
    awards.sort(key=lambda a: _to_int(a.get("fundsObligatedAmt")) or 0, reverse=True)
    return WinningAbstracts(
        keyword=keyword,
        samples=[
            WinningAbstract(
                award_id=a.get("id"),
                title=a.get("title"),
                pi=_pi_name(a),
                institution=a.get("awardeeName"),
                funds_obligated_usd=_to_int(a.get("fundsObligatedAmt")),
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
    awards = await _collect(keyword, "", from_year, max_awards)
    by_prog: dict[str, dict] = {}
    for a in awards:
        p = a.get("fundProgramName") or "Unknown"
        amt = _to_int(a.get("fundsObligatedAmt")) or 0
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
    institutions and year span. Uses the 25 most recent matches only."""
    params = {"printFields": LIST_FIELDS, "piLastName": last_name, **_page_params(1, RPP)}
    if first_name:
        params["piFirstName"] = first_name
    resp = await _api(params)
    awards = resp.get("award", [])
    amts = [x for x in (_to_int(a.get("fundsObligatedAmt")) for a in awards) if x]
    years = sorted(y for y in (_year(a.get("startDate")) for a in awards) if y)
    return PITrackRecord(
        pi=f"{first_name} {last_name}".strip(),
        awards_found=len(awards),
        total_matching_awards=_total_count(resp),
        total_funds_obligated_usd=sum(amts),
        programs=_counts(
            Counter(a.get("fundProgramName") or "Unknown" for a in awards).most_common(5)
        ),
        institutions=_counts(
            Counter(a.get("awardeeName") or "Unknown" for a in awards).most_common(3)
        ),
        year_span=[years[0], years[-1]] if years else None,
        recent_titles=[a.get("title") for a in awards[:5]],
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
    awards = await _collect(keyword, fund_program_name, from_year, max_awards=n)
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
