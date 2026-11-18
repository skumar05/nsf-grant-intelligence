"""Write RESULTS.md from the latest results/*.json of each prompt version."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent


def latest_by_version() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted((HERE / "results").glob("*.json")):  # names end in a timestamp, so later wins
        d = json.loads(f.read_text())
        out[d["prompt_version"]] = d
    return out


def main() -> None:
    runs = latest_by_version()
    versions = sorted(runs)
    any_run = runs[versions[0]]
    lines = [
        "# Phoenix experiment results",
        "",
        f"Dataset `{any_run['dataset']}` (10 multi-step questions). Agent {any_run['agent_model']}, "
        f"judge {any_run['judge_model']}. One run per prompt version; the agent is not deterministic.",
        "",
        "| Prompt | Correct (match_expected_response) | In scope (check_answer_scope) |",
        "|---|---|---|",
    ]
    for v in versions:
        c = runs[v]["label_counts"]
        ok = c["match_expected_response"].get("correct", 0)
        sc = c["check_answer_scope"].get("within_scope", 0)
        total = sum(c["match_expected_response"].values())
        lines.append(f"| {v} | {ok}/{total} | {sc}/{total} |")
    lines += [
        "",
        "| Question | Gold answer | " + " | ".join(f"{v}: label" for v in versions) + " |",
        "|---|---|" + "---|" * len(versions),
    ]
    by_q: dict[str, dict] = {}
    for v in versions:
        for r in runs[v]["rows"]:
            if r["evaluator"] == "match_expected_response":
                by_q.setdefault(r["question"], {"ref": r["reference"]})[v] = r["label"]
    for q, d in by_q.items():
        lines.append(f"| {q[:95]} | {d['ref'][:50]} | " + " | ".join(d.get(v, "-") for v in versions) + " |")
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    print("wrote RESULTS.md")


if __name__ == "__main__":
    main()
