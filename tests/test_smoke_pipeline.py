from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _run_pipeline(data_root: Path, out_root: Path) -> dict:
    from exact.repro import configure_reproducibility

    configure_reproducibility(seed=123, threads=1, matplotlib_backend="Agg")

    from exact.experiments.ets2026 import ETS2026Config, run_ets2026

    cfg = ETS2026Config(
        window_sizes=(50, 100, 200),
        n_splits=3,
        lambda_res=0.5,
        agg_mode="max",
        seed=123,
    )
    return run_ets2026(data_root=data_root, out_root=out_root, cfg=cfg)


def test_loader_drops_unnamed_index_column(tmp_path: Path) -> None:
    import pandas as pd
    from exact.io import load_telemetry_for_setup

    data_root = tmp_path / "telemetry"
    data_root.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame({"Unnamed: 0": [0, 1, 2], "core_ipc": [1.0, 1.1, 1.2]})
    frame.to_csv(data_root / "DDR4_benign_dft.csv", index=False)
    frame.to_csv(data_root / "DDR4_DROOP_dft.csv", index=False)

    loaded = load_telemetry_for_setup("A", data_root)
    assert "Unnamed: 0" not in loaded.columns


def test_sample_pipeline_runs(tmp_path: Path) -> None:
    from exact.sample_data import create_sample_dataset

    data_root = tmp_path / "data"
    out_root = tmp_path / "out"
    create_sample_dataset(data_root, seed=123, n_rows=600)

    artifacts = _run_pipeline(data_root, out_root)

    assert "shared_features" in artifacts
    assert len(artifacts["shared_features"]) > 0
    assert (out_root / "SETUP_A_EXACT_summary_per_workload.csv").exists()
    assert (out_root / "SETUP_B_EXACT_summary_per_workload.csv").exists()
    assert (out_root / "figures" / "fig4_metrics_vs_window_size.png").exists()
    assert (out_root / "run_manifest.json").exists()


def test_sample_pipeline_is_reproducible(tmp_path: Path) -> None:
    from exact.sample_data import create_sample_dataset

    data_root = tmp_path / "data"
    create_sample_dataset(data_root, seed=123, n_rows=600)

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    _run_pipeline(data_root, out_a)
    _run_pipeline(data_root, out_b)

    checked = [
        "SETUP_A_EXACT_summary_global.csv",
        "SETUP_A_EXACT_summary_per_workload.csv",
        "SETUP_B_EXACT_summary_global.csv",
        "SETUP_B_EXACT_summary_per_workload.csv",
        "causal/SETUP_A_feature_ranks.csv",
        "causal/SETUP_B_feature_ranks.csv",
        "fig5_inputs/setupA_edges.csv",
        "fig5_inputs/setupB_edges.csv",
    ]

    for rel in checked:
        assert _sha256(out_a / rel) == _sha256(out_b / rel)
