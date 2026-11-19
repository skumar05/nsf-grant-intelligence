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

Example prompts: "How much NSF funding has Carnegie Mellon won for robotics since 2021, and which programs fund it?", "Show me 3 abstracts of recent funded wildfire awards so I can see how winning proposals read", "What vocabulary do funded CRISPR abstracts share?"

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
├── eval/                         evaluation
│   ├── run_eval.py, answer_eval.py, dataset.json   live, tool-selection and answer layers
│   ├── RESULTS.md, JUDGE_REVIEW.md, JUDGE_AUDIT.md, EVALUATION.docx   results, review sheet, its audit, write-up
│   └── phoenix/                  Arize Phoenix harness: agent, judges, prompts, gold questions
├── Dockerfile                    container image (serves HTTP on port 8080)
├── pyproject.toml                package metadata, dependencies, ruff config
├── requirements.txt              runtime dependencies for platforms that expect one
├── manifest.yaml                 cloud.gov manifest (untested)
├── server.json                   MCP Registry manifest
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

## Hosted instance

A live instance runs on AWS Lightsail Containers at
`https://nsf-grant-intelligence.svyw8btrxggzc.us-east-1.cs.amazonlightsail.com/mcp`
(last redeployed 2026-11-18). It is open to anyone and may be taken down at any time. It is built from the
repo's `Dockerfile`, with an HTTP health check on `/health`, and has no authentication, so anyone with the URL can
call the tools.

## Test

```bash
.venv/bin/python -m pytest
```

Tests mock the NSF API and run offline. CI (`.github/workflows/ci.yml`) also runs `ruff check` and
`ruff format --check`; run them locally with `.venv/bin/python -m ruff check .`.

## Evaluation

`eval/run_eval.py` runs three layers and writes `eval/RESULTS.md` and `eval/results.json`:

- **live**: 21 cases that call every tool through the MCP layer against the real NSF API
  (known-fact lookups, analysis invariants, error handling, invalid arguments), repeated
  3 times for consistency and latency.
- **selection**: 25 prompts (18 in-scope, 7 out-of-scope or injection) checking that a Claude
  model picks the right tool, or none, and passes the right arguments on 14 of them. Needs `ANTHROPIC_API_KEY` (set it in a git-ignored `.env`; see `.env.example`) and `pip install -e ".[eval]"`.
- **answer**: 20 questions an agent answers end to end, scored by two LLM judges (correctness against reference
  answers taken from raw NSF API calls, and scope adherence), run with the tools and again with no tools as a
  baseline. A second model (claude-opus-5-5) re-grades every answer, and `eval/JUDGE_REVIEW.md` lists items for a
  human to audit. `eval/answer_eval.py`. Claude rechecked the 20 first-run answers on that sheet against the live API
  and found all verdicts correct ([eval/JUDGE_AUDIT.md](eval/JUDGE_AUDIT.md)); that is not a human review.

```bash
.venv/bin/python eval/run_eval.py --repeats 3
```

Cases live in `eval/dataset.json`. Latest results: [eval/RESULTS.md](eval/RESULTS.md).

A second harness in [`eval/phoenix/`](eval/phoenix/README.md) follows the hackathon template's Arize Phoenix layout: a
LangChain agent over stdio, 10 multi-step gold questions (`evaluation.xml`), and `match_expected_response` and
`check_answer_scope` judges with a separate judge model. It needs its own virtual environment. Latest results:
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
