"""Even-handed sampling of awards across start years.

The NSF API returns newest start dates first, so a plain capped scan fills up with
the latest awards. Everything that samples goes through here instead.
"""

from __future__ import annotations

from datetime import date

from . import api

MAX_YEAR_SPAN = 30  # per-year queries cost one API call each at minimum


def year_range(from_year: int, to_year: int | None) -> list[int]:
    """Inclusive start-year range; to_year defaults to next year (NSF lists future awards)."""
    if to_year is None:
        to_year = date.today().year + 1
    if to_year < from_year:
        raise api.NSFAPIError(f"to_year ({to_year}) is before from_year ({from_year}).")
    if to_year - from_year + 1 > MAX_YEAR_SPAN:
        raise api.NSFAPIError(
            f"Year range too wide ({to_year - from_year + 1} years, max {MAX_YEAR_SPAN}): "
            "raise from_year."
        )
    return list(range(from_year, to_year + 1))


async def collect(
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
    years = year_range(from_year, to_year)
    quota = -(-max_awards // len(years))  # ceil: per-year share
    out: list[dict] = []
    for year in years:
        got = 0
        page = 0
        while got < quota:
            page += 1
            params = {
                "printFields": api.ABSTRACT_FIELDS,
                "startDateStart": f"01/01/{year}",
                "startDateEnd": f"12/31/{year}",
                **api.page_params(page, api.RPP),
                **api.text_filters(keyword, fund_program_name),
            }
            resp = await api.request(params)
            awards = resp.get("award", [])
            out.extend(awards[: quota - got])
            got += len(awards)
            if len(awards) < api.RPP:
                break
    return out[:max_awards]
