"""Convert a dataset's evaluation.xml into examples/<name>.csv (columns: query, responses).

Usage: python build_csv.py --dataset-name nsf-eval-0
"""

from __future__ import annotations

import argparse
import csv
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent


def convert(name: str) -> Path:
    root = ET.parse(HERE / "datasets" / name / "evaluation.xml").getroot()
    pairs = [
        (p.findtext("question", "").strip(), p.findtext("answer", "").strip()) for p in root.iter("qa_pair")
    ]
    out = HERE / "datasets" / name / "examples" / f"{name}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["query", "responses"])
        w.writerows(pairs)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-name", required=True)
    print(f"wrote {convert(ap.parse_args().dataset_name)}")
