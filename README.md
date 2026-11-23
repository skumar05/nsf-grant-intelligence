# NSF Grant Intelligence MCP

An [MCP](https://modelcontextprotocol.io) server that puts 500k+ National Science Foundation
awards at an AI assistant's fingertips: search awards, profile PIs and institutions, analyze
funding trends, and study what winning proposals look like, all through natural-language
tool calls. It uses the public, keyless
[NSF Award API](https://www.research.gov/common/webapi/awardapisearch-v1.htm), so no API key is needed.

## Tools

### Grant intelligence

| Tool | What it does |
|---|---|
| `search_awards` | Search by keyword, PI, institution, city/state, program, start-date range, active status |
| `get_award` | Full detail (abstract, directorate, award type) for one award ID |
| `funding_trends` | Exact award count per start year, plus sampled dollars, for a keyword or program |
| `institution_profile` | How an institution does at NSF: totals, top programs and PIs, awards per year, optionally for one topic |

### Winning-proposal analysis

These mine what actually gets funded. Each samples awards from `from_year` onward
(default 2020), spread evenly across start years.

| Tool | What it does |
|---|---|
| `analyze_topic` | Award stats for a topic: total and median funding, top programs, institutions and PIs, awards per start year |
| `sample_winning_abstracts` | Full abstracts, PIs and amounts of the largest recent awards, to study how winning proposals read |
| `compare_funding_by_program` | Which NSF programs fund a topic, ranked by dollars, to see where to submit |
| `pi_track_record` | A PI's NSF history: award count, total funding, programs, institutions, year span, recent awards, and which distinct names matched |
| `extract_themes` | Most frequent substantive terms across funded abstracts for a topic |

## Sample prompts

Ask in plain language; the assistant picks the tool. One prompt for each tool:

| Goal | Sample prompt | Tool |
|---|---|---|
| Look up one award | What is the full abstract of NSF award 1753742? | `get_award` |
| Search awards | Find NSF awards about CRISPR that started in 2018. | `search_awards` |
| Profile a PI | What NSF grants has Keith Nehrke received? | `pi_track_record` |
| Profile an institution | How much NSF funding has Carnegie Mellon won for robotics since 2021, and which programs fund it? | `institution_profile` |
| See a trend | How has NSF funding for microplastics research changed year by year since 2019? | `funding_trends` |
| Analyze a topic | What does NSF fund in quantum sensing since 2023? Who are the top institutions? | `analyze_topic` |
| Study winning proposals | Show me 3 abstracts of recent funded wildfire awards so I can see how winning proposals read | `sample_winning_abstracts` |
| Decide where to submit | Which NSF programs fund cybersecurity education, and where should I submit? | `compare_funding_by_program` |
| Find shared vocabulary | What vocabulary do funded CRISPR abstracts share? | `extract_themes` |

The tool column shows the tool each prompt is expected to call. Some prompts may call more than one.

## Repository structure

```
.
├── src/nsf_grant_intelligence/   the server
│   ├── app.py                    entry point: builds the MCP server, registers everything, picks the transport
│   ├── tools/                    one module per tool (nine), plus _common.py helpers
│   ├── prompts/                  the funding_landscape prompt
│   ├── resources/                the nsf://api-notes resource
│   ├── routes.py                 landing page, /health and /version (HTTP only)
│   ├── config.py                 settings from env or .env (MCP_TRANSPORT, MCP_HOST, MCP_PORT)
│   ├── api.py                    NSF API client: retries, errors, paging helpers
│   ├── sampling.py               per-year sampling used by the analysis tools
│   ├── transform.py              pure helpers over raw award records
│   └── models.py                 Pydantic input types and structured outputs
├── main.py                       root entry point for local runs (same server)
├── tests/                        offline tests; the NSF API is mocked
├── eval/phoenix/                 Arize Phoenix evaluation: agent, judges, prompts, gold questions, results
├── Dockerfile                    container image (serves HTTP on port 8080)
├── pyproject.toml                package metadata, dependencies, ruff config
├── requirements.txt              runtime dependencies for platforms that expect one
├── manifest.yaml                 cloud.gov manifest (untested)
├── .mcp.json, .vscode/mcp.json   client registrations for Claude Code and VS Code
├── .github/workflows/ci.yml      CI: ruff and pytest
├── .env.example                  environment variables for the evals
└── README.md, QUICKSTART.md, DEPLOYMENT.md, SECURITY.md, CLAUDE.md, LICENSE
```

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

To serve it over HTTP, set `PORT` (any value) or `MCP_TRANSPORT=streamable-http`; see [QUICKSTART.md](QUICKSTART.md).
For any other host, see [DEPLOYMENT.md](DEPLOYMENT.md): build context, runtime contract, health check and verification steps.


## Test

```bash
.venv/bin/python -m pytest
```

Tests mock the NSF API and run offline. CI (`.github/workflows/ci.yml`) also runs `ruff check` and
`ruff format --check`; run them locally with `.venv/bin/python -m ruff check .`.

## Evaluation

[`eval/phoenix/`](eval/phoenix/README.md) follows the hackathon template's Arize Phoenix layout: a LangChain agent
connects to the server over stdio and answers 10 multi-step gold questions (`evaluation.xml`), and two LLM judges,
`match_expected_response` and `check_answer_scope`, score each answer with a separate judge model. Two system
prompts were compared. Both scored 10/10 correct and 10/10 in scope, from one run each; the agent is not
deterministic, and the dataset is small and written by the people who built the server. It needs its own virtual
environment; see the harness README for the run commands. Latest results:
[eval/phoenix/RESULTS.md](eval/phoenix/RESULTS.md).

## Caveats

- The API returns at most 25 results per page and reports match counts up to 10,000.
- Offset paging over a long result list is not reliable: it can repeat some awards and skip others (110 awards
  came back as 108 distinct ones). `totalCount` is exact; for a complete list of one query, split it into date windows.
- `funding_trends` aggregates a sample (up to `max_pages` × 25 awards), drawn from the
  most recent start dates first. Treat totals as indicative for broad keywords.
- The API returns results newest start date first, and NSF lists awards with future start
  dates (next year's included). The analysis tools therefore query one year at a time,
  `from_year` through next year, with an equal quota per year. A capped scan without this
  would fill up with only the latest awards.
- The analysis tools are samples (default 100 to 150 awards), not censuses, and a year with
  more awards is not weighted more heavily. Raise `max_awards` (or `n`) for a larger sample.
- `fundProgramName` comes back truncated by the API (for example "CSCS: Circuits and Systems
  for"), so program names in the results can be cut off.
- Keyword matching is loose: it can match any text in the record, so counts for broad
  terms like "artificial intelligence" are inflated. Filtering by program is more precise.
