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

Example prompts: "What does NSF fund in quantum sensing since 2023?", "Show me
abstracts of recent funded AI-for-geoscience awards", "Which programs fund
cybersecurity education?"

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

## Deploy to AWS App Runner

`deploy/apprunner.sh` builds the image (`linux/amd64`), pushes it to ECR, creates the IAM role App Runner
needs to pull it, and creates or updates the service with an HTTP health check on `/health`. It needs the
`aws` CLI with credentials, and a running Docker daemon.

```bash
DRY_RUN=1 deploy/apprunner.sh   # print every command without running anything
deploy/apprunner.sh             # deploy; prints the MCP endpoint, https://<service-url>/mcp
```

Optional variables: `AWS_REGION` (default `us-east-1`), `SERVICE_NAME`, `CPU`, `MEMORY`. The service is
public with no authentication, so anyone with the URL can call the tools.

## Test

```bash
.venv/bin/python -m pytest
```

Tests mock the NSF API and run offline.

## Evaluation

`eval/run_eval.py` runs three layers and writes `eval/RESULTS.md` and `eval/results.json`:

- **live**: 21 cases that call every tool through the MCP layer against the real NSF API
  (known-fact lookups, analysis invariants, error handling, invalid arguments), repeated
  3 times for consistency and latency.
- **selection**: 15 prompts (11 in-scope, 4 out-of-scope or injection) checking that a Claude
  model picks the right tool, or none. Needs `ANTHROPIC_API_KEY` (set it in a git-ignored `.env`; see `.env.example`) and `pip install -e ".[eval]"`.
- **answer**: 12 questions an agent answers end to end, scored by two LLM judges (correctness against reference
  answers taken from raw NSF API calls, and scope adherence), run with the tools and again with no tools as a
  baseline. `eval/answer_eval.py`.

```bash
.venv/bin/python eval/run_eval.py --repeats 3
```

Cases live in `eval/dataset.json`. Latest results: [eval/RESULTS.md](eval/RESULTS.md).

## Caveats

- The API returns at most 25 results per page and reports match counts up to 10,000.
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
