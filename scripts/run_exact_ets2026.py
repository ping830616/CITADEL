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
    p = argparse.ArgumentParser(description="Run the notebook-derived EXACT pipeline (ETS 2026 draft).")
    p.add_argument(
        "--data-root",
        type=Path,
        default=Path("./data/telemetry"),
        help="Folder containing telemetry CSVs (DDR4_*.csv and DDR5_*.csv).",
    )
    p.add_argument("--out-root", type=Path, default=Path("./results"), help="Output folder for CSVs and figures.")
    p.add_argument("--lambda-res", type=float, default=0.5, help="lambda mixing coefficient in CINTAS score.")
    p.add_argument("--agg-mode", type=str, default="max", choices=["max", "mean", "median"], help="Decision-block aggregation mode.")
    p.add_argument("--p-quantile", type=float, default=0.99, help="Benign quantile for threshold tau.")
    p.add_argument("--corr-threshold", type=float, default=0.35, help="Spearman |rho| threshold for benign correlation skeleton.")
    p.add_argument("--seed", type=int, default=123, help="Random seed used for folds and synthetic fallbacks.")
    p.add_argument("--threads", type=int, default=1, help="Thread cap for deterministic numerical kernels.")
    args = p.parse_args()

    configure_reproducibility(seed=int(args.seed), threads=int(args.threads), matplotlib_backend="Agg")

    from exact.experiments.ets2026 import ETS2026Config, run_ets2026

    cfg = ETS2026Config(
        lambda_res=float(args.lambda_res),
        agg_mode=str(args.agg_mode),
        p_quantile=float(args.p_quantile),
        corr_threshold=float(args.corr_threshold),
        seed=int(args.seed),
    )

    run_ets2026(data_root=args.data_root, out_root=args.out_root, cfg=cfg)


if __name__ == "__main__":
    main()
