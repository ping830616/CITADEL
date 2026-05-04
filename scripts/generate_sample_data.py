#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from exact.repro import configure_reproducibility


def main() -> None:
    p = argparse.ArgumentParser(description="Generate a deterministic sample telemetry dataset.")
    p.add_argument("--out-root", type=Path, default=Path("./data/sample"), help="Where to write the synthetic CSV files.")
    p.add_argument("--seed", type=int, default=123, help="Seed for deterministic synthetic data generation.")
    p.add_argument("--rows", type=int, default=2000, help="Rows per telemetry CSV.")
    p.add_argument(
        "--workloads",
        nargs="+",
        default=["dft", "dj", "mm", "tr"],
        help="Workload tags to synthesize.",
    )
    args = p.parse_args()

    configure_reproducibility(seed=int(args.seed), threads=1, matplotlib_backend=None)

    from exact.sample_data import create_sample_dataset

    created = create_sample_dataset(
        args.out_root,
        seed=int(args.seed),
        workloads=tuple(args.workloads),
        n_rows=int(args.rows),
    )
    print(f"Wrote {len(created)} files to {args.out_root}")


if __name__ == "__main__":
    main()
