# NSF Grant Intelligence

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant search and analyze
500k+ National Science Foundation awards through the public, keyless
[NSF Award API](https://www.research.gov/common/webapi/awardapisearch-v1.htm).

## Tools

| Tool | What it does |
|---|---|
| `search_awards` | Search by keyword, PI, institution, city/state, program, start-date range, active status |
| `get_award` | Full detail (abstract, directorate, award type) for one award ID |
| `awards_by_pi` | Funding history of a principal investigator |
| `awards_by_institution` | Awards to an institution, optionally active only |
| `funding_trends` | Award count and obligated dollars per start year for a keyword or program (sampled) |

## Setup

Requires Python 3.13+.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

## Run

The server speaks MCP over stdio:

```bash
.venv/bin/python -m nsf_grant_intelligence
# or the installed script:
.venv/bin/nsf-grant-intelligence
```

It's already registered for Claude Code (`.mcp.json`) and VS Code (`.vscode/mcp.json`).
For other clients, use the venv's Python as the command with args `-m nsf_grant_intelligence`.

## Test

```bash
.venv/bin/python -m pytest
```

Tests mock the NSF API and run offline.

## Caveats

- The API returns at most 25 results per page and reports match counts up to 10,000.
- `funding_trends` aggregates a sample (up to `max_pages` × 25 awards), drawn from the
  most recent start dates first. Treat totals as indicative for broad keywords.
- Keyword matching is loose: it can match any text in the record, so counts for broad
  terms like "artificial intelligence" are inflated. Filtering by program is more precise.
