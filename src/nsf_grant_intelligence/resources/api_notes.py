"""Resource: what the NSF data covers and its limits, so a model can caveat answers."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

NOTES = """# NSF Award API: coverage and limits

Source: the public NSF Award API (https://api.nsf.gov/services/v1/awards.json). No key needed.
It covers NSF awards only (not NIH, DOE or other agencies), including awards with future start dates.

- Search results are ordered newest start date first, not by relevance.
- Keyword search is loose: it matches text anywhere in the record, so counts for broad
  terms are inflated. Filtering by program is more precise.
- Match counts cap at 10,000. A page holds at most 25 awards.
- Institution names are matched as a phrase; city matching is loose.
- Program names come back truncated by the API (for example "CSCS: Circuits and Systems for").
- The analysis tools (analyze_topic, institution_profile, compare_funding_by_program, extract_themes,
  sample_winning_abstracts) work on a sample spread evenly across start years, not a census.
  funding_trends reports exact award counts per year but sampled dollar totals.
- Dates are MM/DD/YYYY. Amounts are US dollars obligated to date.
"""


def api_notes() -> str:
    """Coverage, ordering and sampling caveats for the NSF Award API."""
    return NOTES


def register(mcp: MCPServer) -> None:
    mcp.resource(
        "nsf://api-notes", name="api-notes", title="NSF data coverage and limits", mime_type="text/markdown"
    )(api_notes)
