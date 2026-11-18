"""Pure helpers that turn raw NSF award records into tidy values and summaries."""

from __future__ import annotations

from collections import Counter
from statistics import median

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


def to_int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def year_of(d: str | None) -> int | None:
    # API dates look like "03/15/2027"
    try:
        return int(d.split("/")[-1])
    except (AttributeError, ValueError, IndexError):
        return None


def pi_name(a: dict) -> str:
    pi = f"{a.get('piFirstName') or ''} {a.get('piLastName') or ''}".strip()
    return pi or (a.get("pdPIName") or "Unknown")


def trim_award(a: dict, abstract_len: int = 280) -> dict:
    """Compact one award for list views (keeps context small)."""
    pi = f"{a.get('piFirstName') or ''} {a.get('piLastName') or ''}".strip()
    out = {
        "award_id": a.get("id"),
        "title": a.get("title"),
        "pi": pi or a.get("pdPIName"),
        "institution": a.get("awardeeName"),
        "location": ", ".join(x for x in (a.get("awardeeCity"), a.get("awardeeStateCode")) if x),
        "funds_obligated_usd": to_int(a.get("fundsObligatedAmt")),
        "estimated_total_usd": to_int(a.get("estimatedTotalAmt")),
        "start_date": a.get("startDate"),
        "end_date": a.get("expDate"),
        "program": a.get("fundProgramName"),
    }
    if abstract_len and a.get("abstractText"):
        out["abstract_snippet"] = a["abstractText"][:abstract_len].strip()
    return out


def award_stats(awards: list[dict]) -> dict:
    amts = [x for x in (to_int(a.get("fundsObligatedAmt")) for a in awards) if x]
    years = Counter(year_of(a.get("startDate")) for a in awards)
    years.pop(None, None)
    return {
        "awards_analyzed": len(awards),
        "total_funds_obligated_usd": sum(amts),
        "median_award_usd": int(median(amts)) if amts else None,
        "top_programs": Counter(a.get("fundProgramName") or "Unknown" for a in awards).most_common(5),
        "top_institutions": Counter(a.get("awardeeName") or "Unknown" for a in awards).most_common(5),
        "top_pis": Counter(pi_name(a) for a in awards).most_common(5),
        "awards_by_start_year": dict(sorted(years.items())),
    }
