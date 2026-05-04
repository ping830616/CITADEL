from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_tcad_ablation_smoke_is_reproducible(tmp_path: Path) -> None:
    from exact.experiments.tcad2026 import TCAD2026Config, run_tcad_ablation
    from exact.sample_data import create_sample_dataset

    data_root = tmp_path / "data"
    create_sample_dataset(data_root, seed=123, n_rows=600)

    cfg = TCAD2026Config(
        feature_budgets=(8,),
        window_sizes=(50,),
        lambda_res_values=(0.5,),
        agg_modes=("max",),
        weight_modes=("uniform",),
        fixed_point_q=(12,),
        n_splits=3,
        seed=123,
    )

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    res_a = run_tcad_ablation(data_root=data_root, out_root=out_a, cfg=cfg)
    res_b = run_tcad_ablation(data_root=data_root, out_root=out_b, cfg=cfg)

    summary_a = res_a["summary"]
    summary_b = res_b["summary"]
    assert not summary_a.empty
    assert summary_a.equals(summary_b)
    assert (out_a / "run_manifest.json").exists()
