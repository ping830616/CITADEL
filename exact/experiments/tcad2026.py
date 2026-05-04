from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from ..causal_corr import build_causal_and_rank_features_for_setup
from ..cintas import FixedPointCINTAS, FixedPointConfig, fit_cintas_from_benign
from ..evaluation import run_exact_eval_for_setup
from ..hardware import estimate_cintas_hardware_cost, format_feature_group_counts
from ..io import load_telemetry_two_setups
from ..preprocessing import clean_and_debias_telemetry, drop_constant_features, get_feature_columns
from ..repro import find_repo_root, write_run_manifest


@dataclass(frozen=True)
class TCAD2026Config:
    scenarios_eval: tuple[str, ...] = ("DROOP", "RH", "SPECTRE")
    feature_budgets: tuple[int, ...] = (8, 15)
    window_sizes: tuple[int, ...] = (50, 100)
    lambda_res_values: tuple[float, ...] = (0.25, 0.5)
    agg_modes: tuple[str, ...] = ("max",)
    weight_modes: tuple[str, ...] = ("uniform",)
    fixed_point_q: tuple[int, ...] = (12, 15)
    n_splits: int = 3
    p_quantile: float = 0.99
    corr_threshold: float = 0.35
    seed: int = 123

    @classmethod
    def from_json(cls, path: Path) -> "TCAD2026Config":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            scenarios_eval=tuple(data.get("scenarios_eval", cls.scenarios_eval)),
            feature_budgets=tuple(int(x) for x in data.get("feature_budgets", cls.feature_budgets)),
            window_sizes=tuple(int(x) for x in data.get("window_sizes", cls.window_sizes)),
            lambda_res_values=tuple(float(x) for x in data.get("lambda_res_values", cls.lambda_res_values)),
            agg_modes=tuple(data.get("agg_modes", cls.agg_modes)),
            weight_modes=tuple(data.get("weight_modes", cls.weight_modes)),
            fixed_point_q=tuple(int(x) for x in data.get("fixed_point_q", cls.fixed_point_q)),
            n_splits=int(data.get("n_splits", cls.n_splits)),
            p_quantile=float(data.get("p_quantile", cls.p_quantile)),
            corr_threshold=float(data.get("corr_threshold", cls.corr_threshold)),
            seed=int(data.get("seed", cls.seed)),
        )


def _selected_features(ranks: pd.DataFrame, k: int, fallback: Iterable[str]) -> list[str]:
    if ranks is not None and not ranks.empty and "feature" in ranks.columns:
        feats = [str(x) for x in ranks.head(int(k))["feature"].tolist()]
        if feats:
            return feats
    return list(fallback)[: int(k)]


def _fixed_point_error(df: pd.DataFrame, model, q: int, *, max_rows: int = 5000) -> dict[str, float]:
    if df.empty:
        return {"fp_mae": 0.0, "fp_max_abs": 0.0}
    subset = df.head(max_rows)
    float_score, _, _ = model.score_dataframe(subset)
    fixed = FixedPointCINTAS.from_float_model(model, FixedPointConfig(q=int(q)))
    fixed_score = fixed.score_dataframe(subset).astype(float) / float(fixed.cfg.scale)
    diff = np.abs(float_score - fixed_score)
    return {
        "fp_mae": float(np.mean(diff)) if diff.size else 0.0,
        "fp_max_abs": float(np.max(diff)) if diff.size else 0.0,
    }


def _summarize_fold_results(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    global_df = df[df["workload"] == "ALL"].copy()
    if global_df.empty:
        global_df = df.copy()
    group_cols = [
        "setup",
        "scenario",
        "window_size",
        "agg_mode",
        "lambda_res",
        "p_quantile",
        "top_k",
        "weight_mode",
        "fixed_point_q",
        "n_selected_features",
    ]
    metric_cols = [
        "auc_roc",
        "auc_pr",
        "f1",
        "bal_acc",
        "mcc",
        "brier",
        "ece",
        "fp_mae",
        "fp_max_abs",
        "hw_frequency_ghz",
        "hw_operator_bit_width",
        "hw_std_area_mm2",
        "hw_agg_area_mm2",
        "hw_area_mm2",
        "hw_power_mw",
        "hw_setup_b_area_overhead_pct",
        "hw_idle_power_overhead_pct",
        "hw_median_workload_power_overhead_pct",
        "hw_add_count",
        "hw_mult_count",
        "hw_estimated_serial_cycles",
        "hw_add_delay_ps",
        "hw_mult_delay_ps",
    ]
    available_metrics = [c for c in metric_cols if c in global_df.columns]
    return (
        global_df.groupby(group_cols, as_index=False)[available_metrics]
        .mean()
        .sort_values(group_cols)
        .reset_index(drop=True)
    )


def run_tcad_ablation(
    *,
    data_root: Path,
    out_root: Path,
    cfg: TCAD2026Config = TCAD2026Config(),
) -> dict[str, Path | pd.DataFrame]:
    """Run the TCAD extension ablation grid.

    This is deliberately a reference orchestration layer. It reuses the ETS
    pipeline components, then varies the journal-specific design axes:
    feature budget, aggregation, decision-block length, lambda, weighting, and
    fixed-point precision.
    """
    data_root = Path(data_root)
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    repo_root = find_repo_root(Path(__file__))

    df_a, df_b = load_telemetry_two_setups(data_root)
    df_by_setup = {
        "A": clean_and_debias_telemetry(df_a),
        "B": clean_and_debias_telemetry(df_b),
    }

    feat_a = drop_constant_features(df_by_setup["A"], get_feature_columns(df_by_setup["A"]))
    feat_b = drop_constant_features(df_by_setup["B"], get_feature_columns(df_by_setup["B"]))
    shared_features = sorted(set(feat_a) & set(feat_b))
    if not shared_features:
        raise RuntimeError("No shared numeric telemetry features between Setup A and Setup B.")

    ranks_by_setup: dict[str, pd.DataFrame] = {}
    for setup, df_setup in df_by_setup.items():
        base_model = fit_cintas_from_benign(
            df_setup,
            shared_features,
            lambda_res=0.5,
            weight_mode="uniform",
        )
        score, _, _ = base_model.score_dataframe(df_setup)
        df_setup["cias_sample_score"] = score
        _, _, ranks = build_causal_and_rank_features_for_setup(
            setup=setup,
            df=df_setup,
            feature_cols=shared_features,
            out_root=out_root,
            corr_threshold=cfg.corr_threshold,
            top_k_plot=max(cfg.feature_budgets),
            score_col="cias_sample_score",
        )
        ranks_by_setup[setup] = ranks

    fold_frames: list[pd.DataFrame] = []
    selected_rows: list[dict] = []

    for setup, df_setup in df_by_setup.items():
        for top_k, lambda_res, agg_mode, weight_mode, q in product(
            cfg.feature_budgets,
            cfg.lambda_res_values,
            cfg.agg_modes,
            cfg.weight_modes,
            cfg.fixed_point_q,
        ):
            feats = _selected_features(ranks_by_setup[setup], int(top_k), shared_features)
            hw_cost = estimate_cintas_hardware_cost(feature_names=feats, frequency_ghz=1.0)
            model = fit_cintas_from_benign(
                df_setup,
                feats,
                lambda_res=float(lambda_res),
                weight_mode=str(weight_mode),
            )
            fp_err = _fixed_point_error(df_setup, model, int(q))
            selected_rows.append({
                "setup": setup,
                "top_k": int(top_k),
                "lambda_res": float(lambda_res),
                "agg_mode": str(agg_mode),
                "weight_mode": str(weight_mode),
                "fixed_point_q": int(q),
                "n_selected_features": int(hw_cost.feature_count),
                "feature_group_counts": format_feature_group_counts(hw_cost.group_feature_counts),
                "features": ",".join(feats),
            })

            eval_df = run_exact_eval_for_setup(
                setup=setup,
                df=df_setup,
                model=model,
                scenarios_eval=cfg.scenarios_eval,
                window_sizes=cfg.window_sizes,
                n_splits_list=(cfg.n_splits,),
                default_p_quantile=cfg.p_quantile,
                agg_mode=str(agg_mode),
                droop_cfg=None,
                seed=cfg.seed,
            )
            if eval_df.empty:
                continue
            eval_df["top_k"] = int(top_k)
            eval_df["n_selected_features"] = int(hw_cost.feature_count)
            eval_df["weight_mode"] = str(weight_mode)
            eval_df["fixed_point_q"] = int(q)
            eval_df["fp_mae"] = fp_err["fp_mae"]
            eval_df["fp_max_abs"] = fp_err["fp_max_abs"]
            for key, value in hw_cost.to_summary_dict().items():
                eval_df[key] = value
            fold_frames.append(eval_df)

    fold_results = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    summary = _summarize_fold_results(fold_results)

    fold_path = out_root / "tcad_ablation_fold_results.csv"
    summary_path = out_root / "tcad_ablation_summary.csv"
    selected_path = out_root / "tcad_selected_features.csv"
    config_path = out_root / "tcad_config_resolved.json"

    fold_results.to_csv(fold_path, index=False)
    summary.to_csv(summary_path, index=False)
    pd.DataFrame(selected_rows).to_csv(selected_path, index=False)
    config_path.write_text(json.dumps(asdict(cfg), indent=2, sort_keys=True), encoding="utf-8")

    manifest_path = write_run_manifest(
        out_root,
        repo_root=repo_root,
        data_root=data_root,
        cfg=cfg,
        seed=cfg.seed,
        artifact_paths=(
            fold_path,
            summary_path,
            selected_path,
            config_path,
            out_root / "causal" / "SETUP_A_feature_ranks.csv",
            out_root / "causal" / "SETUP_B_feature_ranks.csv",
        ),
    )

    return {
        "fold_results": fold_results,
        "summary": summary,
        "fold_path": fold_path,
        "summary_path": summary_path,
        "selected_path": selected_path,
        "manifest_path": manifest_path,
    }
