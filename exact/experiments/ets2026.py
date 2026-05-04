from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from ..io import load_telemetry_two_setups
from ..preprocessing import clean_and_debias_telemetry, get_feature_columns, drop_constant_features
from ..cintas import fit_cintas_from_benign, CINTASModel
from ..evaluation import run_exact_eval_for_setup, save_exact_summaries_for_setup
from ..causal_corr import build_causal_and_rank_features_for_setup, export_edges_for_fig5
from ..plotting import plot_metrics_vs_window_size
from ..fig6 import plot_topk_features_two_panel
from ..repro import find_repo_root, write_run_manifest


@dataclass(frozen=True)
class ETS2026Config:
    scenarios_eval: tuple[str, ...] = ("DROOP", "RH", "SPECTRE")
    window_sizes: tuple[int, ...] = tuple(range(50, 1001, 50))
    n_splits: int = 5
    lambda_res: float = 0.5
    p_quantile: float = 0.99
    agg_mode: str = "max"
    corr_threshold: float = 0.35
    top_k_features: int = 15
    seed: int = 123


def run_ets2026(
    *,
    data_root: Path,
    out_root: Path,
    cfg: ETS2026Config = ETS2026Config(),
) -> dict:
    """Run the (notebook-derived) EXACT pipeline end-to-end.

    Outputs
    -------
    A dictionary with key artifacts:
      - 'setup_A', 'setup_B': loaded telemetry DataFrames
      - 'shared_features': list[str]
      - 'model_A', 'model_B': fitted CINTAS models
      - 'results_A', 'results_B': evaluation fold-level DataFrames
      - 'ranks_A', 'ranks_B': feature rank DataFrames
    """
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    repo_root = find_repo_root(Path(__file__))

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    df_A, df_B = load_telemetry_two_setups(Path(data_root))

    # ------------------------------------------------------------------
    # Clean + debias (matches EXACT.ipynb)
    # ------------------------------------------------------------------
    df_A_z = clean_and_debias_telemetry(df_A)
    df_B_z = clean_and_debias_telemetry(df_B)

    feat_A = drop_constant_features(df_A_z, get_feature_columns(df_A_z))
    feat_B = drop_constant_features(df_B_z, get_feature_columns(df_B_z))
    shared_features = sorted(set(feat_A) & set(feat_B))

    if not shared_features:
        raise RuntimeError("No shared numeric telemetry features between Setup A and Setup B.")

    # ------------------------------------------------------------------
    # Fit CINTAS from BENIGN (same feature list for A and B)
    # ------------------------------------------------------------------
    model_A = fit_cintas_from_benign(df_A_z, shared_features, lambda_res=cfg.lambda_res)
    model_B = fit_cintas_from_benign(df_B_z, shared_features, lambda_res=cfg.lambda_res)

    # Attach per-sample score column for later ranking
    for df_z, model in [(df_A_z, model_A), (df_B_z, model_B)]:
        score, _, _ = model.score_dataframe(df_z)
        df_z["cias_sample_score"] = score

    # ------------------------------------------------------------------
    # Offline causal correlation skeleton + feature ranking
    # ------------------------------------------------------------------
    nodes_A, edges_A, ranks_A = build_causal_and_rank_features_for_setup(
        setup="A",
        df=df_A_z,
        feature_cols=shared_features,
        out_root=out_root,
        corr_threshold=cfg.corr_threshold,
        top_k_plot=20,
        score_col="cias_sample_score",
    )
    nodes_B, edges_B, ranks_B = build_causal_and_rank_features_for_setup(
        setup="B",
        df=df_B_z,
        feature_cols=shared_features,
        out_root=out_root,
        corr_threshold=cfg.corr_threshold,
        top_k_plot=20,
        score_col="cias_sample_score",
    )

    # Export edges in Fig.5-compatible format (optional convenience)
    export_edges_for_fig5(edges_A, out_root / "fig5_inputs" / "setupA_edges.csv")
    export_edges_for_fig5(edges_B, out_root / "fig5_inputs" / "setupB_edges.csv")

    # Fig. 6-style feature importance plot (from rank CSVs)
    plot_topk_features_two_panel(
        ranks_csv_A=out_root / "causal" / "SETUP_A_feature_ranks.csv",
        ranks_csv_B=out_root / "causal" / "SETUP_B_feature_ranks.csv",
        out_png=out_root / "figures" / "fig6_top15_features.png",
        top_k=cfg.top_k_features,
    )

    # ------------------------------------------------------------------
    # Evaluation (fold-level)
    # ------------------------------------------------------------------
    results_A = run_exact_eval_for_setup(
        setup="A",
        df=df_A_z,
        model=model_A,
        scenarios_eval=cfg.scenarios_eval,
        window_sizes=cfg.window_sizes,
        n_splits_list=(cfg.n_splits,),
        default_p_quantile=cfg.p_quantile,
        agg_mode=cfg.agg_mode,
        droop_cfg=None,
        seed=cfg.seed,
    )
    results_B = run_exact_eval_for_setup(
        setup="B",
        df=df_B_z,
        model=model_B,
        scenarios_eval=cfg.scenarios_eval,
        window_sizes=cfg.window_sizes,
        n_splits_list=(cfg.n_splits,),
        default_p_quantile=cfg.p_quantile,
        agg_mode=cfg.agg_mode,
        droop_cfg=None,
        seed=cfg.seed,
    )

    # Save summaries (these CSV names match EXACT.ipynb plots)
    if not results_A.empty:
        save_exact_summaries_for_setup("A", results_A, out_root)
    if not results_B.empty:
        save_exact_summaries_for_setup("B", results_B, out_root)

    # Plot metrics-vs-window-size from the per-workload CSVs
    per_wl_A = out_root / "SETUP_A_EXACT_summary_per_workload.csv"
    per_wl_B = out_root / "SETUP_B_EXACT_summary_per_workload.csv"
    if per_wl_A.exists() and per_wl_B.exists():
        plot_metrics_vs_window_size(
            per_workload_csv_A=per_wl_A,
            per_workload_csv_B=per_wl_B,
            out_png=out_root / "figures" / "fig4_metrics_vs_window_size.png",
            n_splits=cfg.n_splits,
        )

    artifact_paths = (
        out_root / "SETUP_A_EXACT_summary_global.csv",
        out_root / "SETUP_A_EXACT_summary_per_workload.csv",
        out_root / "SETUP_B_EXACT_summary_global.csv",
        out_root / "SETUP_B_EXACT_summary_per_workload.csv",
        out_root / "causal" / "SETUP_A_feature_ranks.csv",
        out_root / "causal" / "SETUP_B_feature_ranks.csv",
        out_root / "fig5_inputs" / "setupA_edges.csv",
        out_root / "fig5_inputs" / "setupB_edges.csv",
        out_root / "figures" / "fig4_metrics_vs_window_size.png",
        out_root / "figures" / "fig6_top15_features.png",
    )
    manifest_path = write_run_manifest(
        out_root,
        repo_root=repo_root,
        data_root=Path(data_root),
        cfg=cfg,
        seed=cfg.seed,
        artifact_paths=artifact_paths,
    )

    return {
        "setup_A": df_A_z,
        "setup_B": df_B_z,
        "shared_features": shared_features,
        "model_A": model_A,
        "model_B": model_B,
        "results_A": results_A,
        "results_B": results_B,
        "ranks_A": ranks_A,
        "ranks_B": ranks_B,
        "run_manifest": manifest_path,
    }
