"""HTTP access to the NSF Award API: pooled client, retries, error mapping, paging helpers."""

from __future__ import annotations

import asyncio
import os

# Some environments put bracketed IPv6 literals (e.g. "[::1]") in no_proxy,
# which httpx fails to parse. Strip just those entries; proxying itself is
# otherwise left exactly as the environment configures it.
for _var in ("no_proxy", "NO_PROXY"):
    _val = os.environ.get(_var)
    if _val and "[" in _val:
        os.environ[_var] = ",".join(p for p in _val.split(",") if "[" not in p)

import httpx  # noqa: E402  (must come after the no_proxy cleanup above)
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from .transform import to_int  # noqa: E402

BASE_URL = "https://api.nsf.gov/services/v1"
TIMEOUT = 30.0
MAX_ATTEMPTS = 3  # total tries per request for transient failures
RETRY_BASE_DELAY = 0.5  # seconds; doubles each retry (tests set this to 0)
RETRY_STATUSES = {429, 500, 502, 503, 504}
RPP = 25  # API page-size cap


LIST_FIELDS = (
    "id,title,piFirstName,piLastName,pdPIName,awardeeName,awardeeCity,"
    "awardeeStateCode,fundsObligatedAmt,estimatedTotalAmt,startDate,expDate,"
    "fundProgramName,primaryProgram"
)

DETAIL_FIELDS = LIST_FIELDS + ",abstractText,program,orgLongName,transType"

ABSTRACT_FIELDS = LIST_FIELDS + ",abstractText"


class NSFAPIError(ToolError):
    """The NSF API failed or had nothing for the request.

    A ToolError, so its message reaches the model (other exceptions are hidden from it).
    """


_client_state: dict = {"client": None, "loop": None}


def _get_client() -> httpx.AsyncClient:
    """One pooled client per event loop, so repeated calls reuse connections."""
    loop = asyncio.get_running_loop()
    client = _client_state["client"]
    if client is None or client.is_closed or _client_state["loop"] is not loop:
        client = httpx.AsyncClient(timeout=TIMEOUT)
        _client_state.update(client=client, loop=loop)
    return client


def _retry_delay(attempt: int, response: httpx.Response | None) -> float:
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), 10.0)
    return RETRY_BASE_DELAY * 2**attempt


async def request(params: dict) -> dict:
    """GET /awards.json and return its "response" object.

    Retries timeouts, connection errors and 429/5xx with exponential backoff.
    Raises NSFAPIError for anything else that goes wrong, including NSF's
    habit of reporting bad requests as HTTP 200 with a serviceNotification.
    """
    for attempt in range(MAX_ATTEMPTS):
        last_try = attempt == MAX_ATTEMPTS - 1
        response = None
        try:
            response = await _get_client().get(f"{BASE_URL}/awards.json", params=params)
            response.raise_for_status()
            body = response.json().get("response", {})
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in RETRY_STATUSES or last_try:
                raise NSFAPIError(f"NSF API returned HTTP {e.response.status_code}") from e
        except httpx.TransportError as e:  # timeouts, connection resets, DNS
            if last_try:
                raise NSFAPIError(f"NSF API unreachable: {type(e).__name__}") from e
        except ValueError as e:  # body was not JSON
            raise NSFAPIError("NSF API returned a response that was not valid JSON") from e
        else:
            if notes := body.get("serviceNotification"):
                raise NSFAPIError(
                    f"NSF API rejected the request ({notes[0].get('notificationCode')}): "
                    "check dates and filters."
                )
            return body
        await asyncio.sleep(_retry_delay(attempt, response))
    raise AssertionError("unreachable")  # pragma: no cover


def page_params(page: int, per_page: int) -> dict:
    per_page = max(1, min(per_page, 25))  # API caps rpp at 25
    page = max(1, page)
    return {"rpp": per_page, "offset": (page - 1) * per_page}  # offset is 0-based


def total_count(resp: dict) -> int | None:
    # API reports the full match count in response.metadata (caps at 10,000)
    return to_int((resp.get("metadata") or {}).get("totalCount"))


def text_filters(keyword: str, fund_program_name: str) -> dict:
    """Query params for the optional keyword / program filters shared by the sampling tools."""
    filters = {"keyword": keyword, "fundProgramName": fund_program_name}
    return {k: v for k, v in filters.items() if v}


def phrase(text: str) -> str:
    """Quote a name so the API matches it as one phrase.

    Unquoted multi-word awardeeName values are matched word by word, so
    "Carnegie Mellon University" returns every institution with "University" in its name.
    """
    return f'"{text.strip().strip(chr(34))}"'
