# Phoenix evaluation harness

An [Arize Phoenix](https://docs.arize.com/phoenix) harness in the layout the hackathon template's `mcp-eval`
skill describes. A LangChain agent connects to this MCP server over stdio, answers a dataset of multi-step
questions with known answers, and two LLM judges score each answer. Traces and experiments are browsable in
the Phoenix UI. It complements the self-contained harness in `eval/run_eval.py` (live, selection and
answer layers), which needs no Phoenix.

## Layout

```
eval/phoenix/
├── agent.py            NSFAgent: launches the server over stdio, builds the LangChain agent, traces to Phoenix
├── llm.py              model wiring (agent and judge models are separate settings)
├── create_dataset.py   upload a dataset from datasets.yaml to Phoenix (--list, --dry-run)
├── run_experiment.py   run agent + judges over a dataset (--system-prompt-version v1|v2)
├── build_csv.py        evaluation.xml -> examples/<name>.csv
├── datasets.yaml       dataset registry
├── judges/             match_expected_response (correctness), check_answer_scope
├── prompts/            system_prompt_v1.txt (basic analyst), system_prompt_v2.txt (adds scope boundaries)
├── datasets/nsf-eval-1/  evaluation.xml (10 gold questions) and examples/nsf-eval-1.csv
└── results/            one JSON per experiment run (per-question labels and judge explanations)
```

## Three environments (and why)

| Environment | Holds | Why separate |
|---|---|---|
| `.venv` | the server (`mcp>=2.3`) | the project itself |
| `.venv-eval` | this harness: Phoenix client, evals, otel, LangChain (`mcp<2`) | `langchain-mcp-adapters` does not work with `mcp` 2.x |
| `.venv-phoenix` | the Phoenix server (`arize-phoenix`) | it pulls in `mcp` 2.x libraries that clash with the adapter |

The agent launches the server with `.venv/bin/python -m nsf_grant_intelligence` (override with
`NSF_SERVER_PYTHON`), so the harness environment never imports the server.

## Setup

```bash
# from the repo root
python3 -m venv .venv-eval  && .venv-eval/bin/python -m pip install -r eval/phoenix/requirements.txt
python3 -m venv .venv-phoenix && .venv-phoenix/bin/python -m pip install arize-phoenix
cp .env.example .env        # then set ANTHROPIC_API_KEY (or USAI_API_KEY and USAI_BASE_URL)
```

`.env` settings: `ANTHROPIC_API_KEY` for Anthropic directly, or `USAI_API_KEY` and `USAI_BASE_URL` for an
OpenAI-compatible gateway. `AGENT_MODEL` (default `claude-sonnet-5-5`) and `JUDGE_MODEL` (default
`claude-opus-5-5`) are separate so the judge is a different model from the agent.

## Run

```bash
.venv-phoenix/bin/phoenix serve                      # terminal 1: UI at http://localhost:6006
cd eval/phoenix                                      # terminal 2
../../.venv-eval/bin/python create_dataset.py --dataset-name nsf-eval-1
../../.venv-eval/bin/python run_experiment.py --dataset-name nsf-eval-1
../../.venv-eval/bin/python run_experiment.py --dataset-name nsf-eval-1 --system-prompt-version v2
```

Check without uploading: `create_dataset.py --dataset-name nsf-eval-1 --dry-run`. Try one question:
`agent.py "What is the title of NSF award 1753742?"`.

## The dataset

`datasets/nsf-eval-1/evaluation.xml` holds 10 questions. Each needs several tool calls (paging through
results, summing across lookups, comparing years or institutions) and has one checkable answer, computed from
raw NSF API calls made outside this server (start-date filter, quoted institution and program names). They are
read-only, independent of one another, and use past years so the answers are stable, though the NSF can still
revise records. Edit the XML, then run `build_csv.py`, then re-create the dataset in Phoenix.

## A pitfall found while building the gold answers

The NSF API's offset paging is not reliable over a long result list. Paging all 110 Carnegie Mellon awards
that started in 2020 returned only 108 distinct awards, so two were missing, including the largest one.
Splitting the same query into monthly date windows returned all 110. The first draft of this dataset had a
wrong answer for exactly that reason. Gold answers that need individual awards are now gathered in monthly
windows and checked against `totalCount`; counts that come straight from `totalCount` are unaffected. The
server pages by offset too, so its tools can repeat or skip awards on long result lists.

## Limits

- Ten questions written by the server's authors is a small sample.
- The agent and judge are LLMs; temperature is not set because `claude-sonnet-5-5` rejects it, so runs vary.
- Results depend on the NSF data on the run date.
