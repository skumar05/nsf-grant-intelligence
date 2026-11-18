"""match_expected_response: does the agent's answer contain the reference answer?"""

from __future__ import annotations

from llm import make_judge_llm
from phoenix.evals import ClassificationEvaluator

TEMPLATE = """You are grading an answer about National Science Foundation (NSF) awards against a reference.

Question: {input}
Reference answer: {reference}
Agent answer: {output}

Mark "correct" only if the agent answer contains the key information of the reference (same numbers, names and
choices) and does not contradict it. Differences in formatting, units, thousands separators, extra explanation
or surrounding prose are fine ("$13,755,019" matches 13755019; "MIT" matches "Massachusetts Institute of
Technology"). If the question has two parts, both must match. Otherwise mark "incorrect"."""

_evaluator = None


def _get() -> ClassificationEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = ClassificationEvaluator(
            name="match_expected_response",
            llm=make_judge_llm(),
            prompt_template=TEMPLATE,
            choices={"correct": 1, "incorrect": 0},
        )
    return _evaluator


def match_expected_response(input, output, expected) -> dict:
    """Phoenix experiment evaluator. input/output/expected come from the dataset example and task."""
    result = _get().evaluate(
        {"input": input["query"], "output": str(output), "reference": expected["responses"]}
    )[0]
    return {"label": result.label, "score": result.score, "explanation": result.explanation}
