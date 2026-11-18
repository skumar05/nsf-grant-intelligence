"""Upload a dataset from datasets.yaml to Phoenix.

python create_dataset.py --list
python create_dataset.py --dataset-name nsf-eval-0 --dry-run     validate only
python create_dataset.py --dataset-name nsf-eval-0               upload
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

HERE = Path(__file__).parent


def load_registry() -> dict:
    return yaml.safe_load((HERE / "datasets.yaml").read_text())["datasets"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dataset-name")
    ap.add_argument("--phoenix-name", help="Name to use in Phoenix (default: the dataset name)")
    ap.add_argument("--csv-path", help="Override the CSV path from datasets.yaml")
    ap.add_argument("--phoenix-endpoint", default="http://localhost:6006")
    ap.add_argument("--dry-run", action="store_true", help="Validate the CSV without uploading")
    args = ap.parse_args()
    registry = load_registry()

    if args.list:
        for name, spec in registry.items():
            print(f"{name}: {spec['description']}")
        return
    if args.dataset_name not in registry:
        ap.error(f"--dataset-name must be one of {sorted(registry)}")
    spec = registry[args.dataset_name]
    csv_path = Path(args.csv_path) if args.csv_path else HERE / spec["csv_path"]
    df = pd.read_csv(csv_path)
    missing = [c for c in spec["input_keys"] + spec["output_keys"] if c not in df.columns]
    if missing:
        raise SystemExit(f"{csv_path} is missing columns: {missing}")
    print(f"{csv_path}: {len(df)} rows, columns {list(df.columns)}")
    if args.dry_run:
        print("dry run: nothing uploaded")
        return

    from phoenix.client import Client

    client = Client(base_url=args.phoenix_endpoint)
    dataset = client.datasets.create_dataset(
        name=args.phoenix_name or args.dataset_name,
        dataframe=df,
        input_keys=spec["input_keys"],
        output_keys=spec["output_keys"],
        dataset_description=spec["description"],
    )
    print(f"uploaded dataset {dataset.name!r} ({len(df)} examples)")


if __name__ == "__main__":
    main()
