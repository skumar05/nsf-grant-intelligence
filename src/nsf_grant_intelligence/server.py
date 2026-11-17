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

import httpx
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("nsf-grant-intelligence")

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
    if a.get("abstractText"):
        out["abstract_snippet"] = a["abstractText"][:abstract_len].strip()
    return out


async def _api(params: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(f"{BASE_URL}/awards.json", params=params)
            r.raise_for_status()
            return r.json().get("response", {})
    except httpx.HTTPError as e:
        return {"_error": f"NSF API request failed: {e}"}


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
) -> list[dict] | dict:
    """Collect up to max_awards awards, spread evenly across start years.

    The API returns newest start date first, so a plain capped scan would
    fill up with the latest (often future-dated) awards. Instead each year in
    from_year..to_year gets its own quota and its own date-restricted query.
    to_year defaults to next year (NSF lists awards with future start dates).

    Returns a list of awards, or {"error": ...} on API failure.
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
            if "_error" in resp:
                return {"error": resp["_error"]}
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


@mcp.tool()
async def search_awards(
    keyword: str = "",
    pi_first_name: str = "",
    pi_last_name: str = "",
    awardee_name: str = "",
    awardee_city: str = "",
    awardee_state_code: str = "",
    fund_program_name: str = "",
    active_only: bool = False,
    start_date_start: str = "",
    start_date_end: str = "",
    page: int = 1,
    per_page: int = 10,
) -> dict:
    """Search NSF awards by keyword, PI, institution, program, dates, etc.

    Dates use MM/DD/YYYY. Set active_only=True for currently active awards.
    """
    params = {"printFields": LIST_FIELDS, **_page_params(page, per_page)}
    if keyword:
        params["keyword"] = keyword
    if pi_first_name:
        params["piFirstName"] = pi_first_name
    if pi_last_name:
        params["piLastName"] = pi_last_name
    if awardee_name:
        params["awardeeName"] = awardee_name
    if awardee_city:
        params["awardeeCity"] = awardee_city
    if awardee_state_code:
        params["awardeeStateCode"] = awardee_state_code
    if fund_program_name:
        params["fundProgramName"] = fund_program_name
    if active_only:
        params["ActiveAwards"] = "true"  # API ignores lowercase "activeAwards"
    if start_date_start:
        params["startDateStart"] = start_date_start
    if start_date_end:
        params["startDateEnd"] = start_date_end

    resp = await _api(params)
    if "_error" in resp:
        return {"error": resp["_error"]}
    awards = resp.get("award", [])
    return {
        "page": page,
        "per_page": per_page,
        "total_count": _total_count(resp),
        "results_on_page": len(awards),
        "awards": [_trim(a) for a in awards],
    }


@mcp.tool()
async def get_award(award_id: str) -> dict:
    """Full detail for one NSF award by its award ID (e.g. "2345678")."""
    resp = await _api({"id": award_id, "printFields": DETAIL_FIELDS})
    if "_error" in resp:
        return {"error": resp["_error"]}
    awards = resp.get("award", [])
    if not awards:
        return {"error": f"No award found with ID {award_id}"}
    a = awards[0]
    out = _trim(a, abstract_len=4000)
    out["abstract"] = a.get("abstractText")
    out.pop("abstract_snippet", None)
    out["program_detail"] = a.get("program")
    out["nsf_directorate"] = a.get("orgLongName")
    out["award_type"] = a.get("transType")
    return out


@mcp.tool()
async def awards_by_pi(
    last_name: str, first_name: str = "", page: int = 1, per_page: int = 10
) -> dict:
    """All NSF awards for a principal investigator (funding history of a researcher)."""
    return await search_awards(
        pi_first_name=first_name,
        pi_last_name=last_name,
        page=page,
        per_page=per_page,
    )


@mcp.tool()
async def awards_by_institution(
    name: str,
    state_code: str = "",
    active_only: bool = False,
    page: int = 1,
    per_page: int = 10,
) -> dict:
    """NSF awards to an institution (e.g. name="Carnegie Mellon", state_code="PA")."""
    return await search_awards(
        awardee_name=name,
        awardee_state_code=state_code,
        active_only=active_only,
        page=page,
        per_page=per_page,
    )


@mcp.tool()
async def funding_trends(
    keyword: str = "",
    fund_program_name: str = "",
    from_year: int = 2015,
    to_year: int = 2026,
    max_pages: int = 8,
) -> dict:
    """Aggregate NSF funding by start year for a keyword/program.

    Pages through up to max_pages x 25 awards (API limit) — treat totals as a
    strong sample, not an exhaustive census, for broad keywords.
    """
    by_year: dict[int, dict] = {}
    scanned = 0
    total = None
    for page in range(1, max_pages + 1):
        params = {
            "printFields": "id,startDate,fundsObligatedAmt",
            # Restrict server-side so the sample is drawn from the requested years
            "startDateStart": f"01/01/{from_year}",
            "startDateEnd": f"12/31/{to_year}",
            **_page_params(page, 25),
        }
        if keyword:
            params["keyword"] = keyword
        if fund_program_name:
            params["fundProgramName"] = fund_program_name
        resp = await _api(params)
        if "_error" in resp:
            return {"error": resp["_error"]}
        if total is None:
            total = _total_count(resp)
        awards = resp.get("award", [])
        if not awards:
            break
        scanned += len(awards)
        for a in awards:
            y = _year(a.get("startDate"))
            if y is None or not (from_year <= y <= to_year):
                continue
            amt = _to_int(a.get("fundsObligatedAmt")) or 0
            b = by_year.setdefault(y, {"awards": 0, "funds_obligated_usd": 0})
            b["awards"] += 1
            b["funds_obligated_usd"] += amt
        if len(awards) < 25:
            break
    return {
        "keyword": keyword or None,
        "fund_program_name": fund_program_name or None,
        "years": dict(sorted(by_year.items())),
        "awards_scanned": scanned,
        "total_matching_awards": total,
        "note": "Sampled aggregation (API pages max 25 results); broad keywords undercount.",
    }


@mcp.tool()
async def analyze_topic(
    keyword: str,
    fund_program_name: str = "",
    from_year: int = 2020,
    max_awards: int = 100,
) -> dict:
    """What gets funded for a topic: award stats, top programs, institutions,
    PIs, and year distribution. E.g. keyword="artificial intelligence"."""
    awards = await _collect(keyword, fund_program_name, from_year, max_awards)
    if isinstance(awards, dict):
        return awards
    s = _stats(awards)
    s.update(
        {
            "keyword": keyword,
            "fund_program_name": fund_program_name or None,
            "from_year": from_year,
        }
    )
    return s


@mcp.tool()
async def sample_winning_abstracts(
    keyword: str, fund_program_name: str = "", from_year: int = 2020, n: int = 5
) -> dict:
    """Full abstracts (plus amounts, PI, program) of recent funded awards —
    study what winning proposals sound like."""
    awards = await _collect(
        keyword, fund_program_name, from_year, max_awards=max(n * 3, 25)
    )
    if isinstance(awards, dict):
        return awards
    # prefer the largest awards — they passed the toughest review
    awards.sort(key=lambda a: _to_int(a.get("fundsObligatedAmt")) or 0, reverse=True)
    return {
        "keyword": keyword,
        "samples": [
            {
                "award_id": a.get("id"),
                "title": a.get("title"),
                "pi": _pi_name(a),
                "institution": a.get("awardeeName"),
                "funds_obligated_usd": _to_int(a.get("fundsObligatedAmt")),
                "program": a.get("fundProgramName"),
                "start_date": a.get("startDate"),
                "abstract": (a.get("abstractText") or "").strip(),
            }
            for a in awards[:n]
        ],
    }


@mcp.tool()
async def compare_funding_by_program(
    keyword: str, from_year: int = 2020, max_awards: int = 150
) -> dict:
    """Which NSF programs/directorates fund a topic, ranked by dollars —
    tells a proposer where to submit."""
    awards = await _collect(keyword, "", from_year, max_awards)
    if isinstance(awards, dict):
        return awards
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
    return {
        "keyword": keyword,
        "from_year": from_year,
        "awards_scanned": len(awards),
        "programs": [{"program": p, **v} for p, v in ranked[:10]],
    }


@mcp.tool()
async def pi_track_record(last_name: str, first_name: str = "") -> dict:
    """A PI's NSF win history: awards, total funding, programs, span —
    find repeat winners to emulate (or collaborate with)."""
    params = {"printFields": LIST_FIELDS, "piLastName": last_name, **_page_params(1, RPP)}
    if first_name:
        params["piFirstName"] = first_name
    resp = await _api(params)
    if "_error" in resp:
        return {"error": resp["_error"]}
    awards = resp.get("award", [])
    # NOTE: first page only (25); enough for a track-record sketch
    amts = [x for x in (_to_int(a.get("fundsObligatedAmt")) for a in awards) if x]
    years = sorted(y for y in (_year(a.get("startDate")) for a in awards) if y)
    return {
        "pi": f"{first_name} {last_name}".strip(),
        "awards_found": len(awards),
        "total_matching_awards": _total_count(resp),
        "total_funds_obligated_usd": sum(amts),
        "programs": Counter(
            a.get("fundProgramName") or "Unknown" for a in awards
        ).most_common(5),
        "institutions": Counter(
            a.get("awardeeName") or "Unknown" for a in awards
        ).most_common(3),
        "year_span": [years[0], years[-1]] if years else None,
        "recent_titles": [a.get("title") for a in awards[:5]],
    }


@mcp.tool()
async def extract_themes(
    keyword: str, fund_program_name: str = "", from_year: int = 2020, n: int = 40
) -> dict:
    """Most frequent substantive terms across funded abstracts for a topic —
    the vocabulary winning proposals share."""
    awards = await _collect(keyword, fund_program_name, from_year, max_awards=n)
    if isinstance(awards, dict):
        return awards
    counts: Counter = Counter()
    for a in awards:
        text = (a.get("abstractText") or "").lower()
        for tok in re.findall(r"[a-z]{3,}", text):
            if tok not in STOPWORDS:
                counts[tok] += 1
    return {
        "keyword": keyword,
        "abstracts_scanned": len(awards),
        "top_terms": counts.most_common(25),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
