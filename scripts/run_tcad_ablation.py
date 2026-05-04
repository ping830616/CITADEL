#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from exact.repro import configure_reproducibility


def _config_from_args(args):
    from exact.experiments.tcad2026 import TCAD2026Config

    if args.config is not None:
        return TCAD2026Config.from_json(args.config)
    if args.preset == "full":
        return TCAD2026Config.from_json(REPO_ROOT / "configs" / "tcad_grid_full.json")
    return TCAD2026Config.from_json(REPO_ROOT / "configs" / "tcad_grid_smoke.json")


def main() -> None:
    p = argparse.ArgumentParser(description="Run EXACT-TCAD design-space ablations.")
    p.add_argument("--data-root", type=Path, default=Path("./data/telemetry"), help="Telemetry CSV directory.")
    p.add_argument("--out-root", type=Path, default=Path("./results/tcad_ablation"), help="Output directory.")
    p.add_argument("--config", type=Path, default=None, help="JSON config file. Overrides --preset.")
    p.add_argument("--preset", choices=["smoke", "full"], default="smoke", help="Built-in config preset.")
    p.add_argument("--seed", type=int, default=None, help="Optional seed override.")
    p.add_argument("--threads", type=int, default=1, help="Thread cap for deterministic kernels.")
    p.add_argument(
        "--generate-sample-if-missing",
        action="store_true",
        help="Generate deterministic sample data when --data-root does not contain CSV files.",
    )
    args = p.parse_args()

    configure_reproducibility(seed=int(args.seed or 123), threads=int(args.threads), matplotlib_backend="Agg")

    if args.generate_sample_if_missing and not list(args.data_root.glob("*.csv")):
        from exact.sample_data import create_sample_dataset

        create_sample_dataset(args.data_root, seed=int(args.seed or 123), n_rows=600)

    from exact.experiments.tcad2026 import TCAD2026Config, run_tcad_ablation

    cfg = _config_from_args(args)
    if args.seed is not None:
        cfg = TCAD2026Config(
            scenarios_eval=cfg.scenarios_eval,
            feature_budgets=cfg.feature_budgets,
            window_sizes=cfg.window_sizes,
            lambda_res_values=cfg.lambda_res_values,
            agg_modes=cfg.agg_modes,
            weight_modes=cfg.weight_modes,
            fixed_point_q=cfg.fixed_point_q,
            n_splits=cfg.n_splits,
            p_quantile=cfg.p_quantile,
            corr_threshold=cfg.corr_threshold,
            seed=int(args.seed),
        )

    artifacts = run_tcad_ablation(data_root=args.data_root, out_root=args.out_root, cfg=cfg)
    print(f"Wrote summary: {artifacts['summary_path']}")
    print(f"Wrote manifest: {artifacts['manifest_path']}")


if __name__ == "__main__":
    main()
