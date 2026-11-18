"""Run the agent over a Phoenix dataset and score it with the two judges.

python run_experiment.py --dataset-name nsf-eval-0
python run_experiment.py --dataset-name nsf-eval-0 --system-prompt-version v2
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from agent import NSFAgent
from judges import check_answer_scope, match_expected_response
from llm import agent_model_name, judge_model_name

HERE = Path(__file__).parent
PROMPT_VERSIONS = sorted(
    p.stem.removeprefix("system_prompt_") for p in (HERE / "prompts").glob("system_prompt_*.txt")
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-name", required=True)
    ap.add_argument("--system-prompt-version", default="v1", choices=PROMPT_VERSIONS)
    ap.add_argument("--project-name", default="nsf-grant-intelligence")
    ap.add_argument("--phoenix-endpoint", default="http://localhost:6006")
    ap.add_argument("--experiment-description", default="")
    ap.add_argument("--timeout", type=int, default=600, help="Seconds allowed per task")
    args = ap.parse_args()

    from phoenix.client import Client

    client = Client(base_url=args.phoenix_endpoint)
    dataset = client.datasets.get_dataset(dataset=args.dataset_name)
    agent = NSFAgent(args.system_prompt_version, args.project_name, args.phoenix_endpoint)
    name = f"{args.dataset_name}-prompt-{args.system_prompt_version}-{time.strftime('%Y%m%d-%H%M%S')}"
    experiment = client.experiments.run_experiment(
        dataset=dataset,
        task=agent.create_experiment_task(),
        evaluators=[check_answer_scope, match_expected_response],
        experiment_name=name,
        experiment_description=args.experiment_description
        or f"agent {agent_model_name()}, judge {judge_model_name()}, prompt {args.system_prompt_version}",
        timeout=args.timeout,
    )
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / f"{name}.json").write_text(
        json.dumps(_summarize(experiment, dataset, args, name), indent=2, default=str)
    )
    print(f"saved {out / (name + '.json')}")


def _summarize(experiment, dataset, args, name: str) -> dict:
    """Flatten a RanExperiment into per-question rows plus label counts."""
    examples = {e["id"]: e for e in dataset.examples}
    runs = {r["id"]: r for r in experiment["task_runs"]}
    rows = []
    for ev in experiment["evaluation_runs"]:
        run = runs.get(ev.experiment_run_id, {})
        result = ev.result if isinstance(ev.result, dict) else (ev.result[0] if ev.result else {})
        example = examples.get(run.get("dataset_example_id"), {})
        rows.append(
            {
                "question": (example.get("input") or {}).get("query"),
                "reference": (example.get("output") or {}).get("responses"),
                "evaluator": ev.name,
                "label": result.get("label"),
                "explanation": result.get("explanation"),
                "agent_answer": str(run.get("output"))[:600],
                "error": ev.error or run.get("error"),
            }
        )
    counts: dict[str, dict[str, int]] = {}
    for r in rows:
        counts.setdefault(r["evaluator"], {}).setdefault(r["label"], 0)
        counts[r["evaluator"]][r["label"]] += 1
    return {
        "experiment": name,
        "dataset": args.dataset_name,
        "prompt_version": args.system_prompt_version,
        "agent_model": agent_model_name(),
        "judge_model": judge_model_name(),
        "label_counts": counts,
        "rows": rows,
    }


if __name__ == "__main__":
    main()
