from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

from .metrics import compute_binary_metrics
from .windowing import build_window_dataset
from .cintas import CINTASModel


@dataclass(frozen=True)
class DroopConfig:
    """A small tuning bundle used by the draft notebooks."""
    setup: str
    window_size: int
    n_splits: int
    lambda_res: float
    agg_mode: str
    p_quantile: float


def evaluate_windows_kfold(
    win_df: pd.DataFrame,
    *,
    setup: str,
    scenario_eval: str,
    window_size: int,
    agg_mode: str,
    lambda_res: float,
    p_quantile: float,
    n_splits: int,
    seed: int,
) -> List[dict]:
    """Evaluate window scores with Stratified K-fold CV.

    This mirrors EXACT.ipynb (S6/S7) behavior:
      - Choose threshold τ as p-quantile of BENIGN train scores.
      - Compute predictions on test scores (>= τ).
      - Convert scores to pseudo-probabilities using min-max scaling on train.
      - Report BOTH global (workload='ALL') and per-workload rows.

    Returns a list of row-dicts.
    """
    if win_df.empty:
        return []

    scores = win_df["score_win"].to_numpy(dtype=float)
    labels = win_df["label"].to_numpy(dtype=int)
    workloads = win_df["workload"].astype(str).to_numpy() if "workload" in win_df.columns else np.array(["ALL"] * len(win_df))

    if np.unique(labels).size < 2:
        return []

    kf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    rows: list[dict] = []

    for fold_idx, (train_idx, test_idx) in enumerate(kf.split(scores, labels)):
        train_scores = scores[train_idx]
        train_labels = labels[train_idx]

        ben_train = train_scores[train_labels == 0]
        tau = float(np.quantile(ben_train if ben_train.size else train_scores, p_quantile))

        test_scores = scores[test_idx]
        test_labels = labels[test_idx]
        test_workloads = workloads[test_idx]

        # pseudo-probabilities
        s_min, s_max = float(train_scores.min()), float(train_scores.max())
        denom = (s_max - s_min) if (s_max > s_min) else 1.0
        test_probs = np.clip((test_scores - s_min) / denom, 0.0, 1.0)

        test_pred = (test_scores >= tau).astype(int)

        # Global
        metrics_all = compute_binary_metrics(test_labels, test_pred, test_probs)
        row_all = {
            "setup": setup,
            "scenario": scenario_eval,
            "workload": "ALL",
            "window_size": int(window_size),
            "n_splits": int(n_splits),
            "fold_idx": int(fold_idx),
            "agg_mode": str(agg_mode),
            "lambda_res": float(lambda_res),
            "p_quantile": float(p_quantile),
            "n_test": int(test_labels.size),
            "n_benign": int((test_labels == 0).sum()),
            "n_anom": int((test_labels == 1).sum()),
            "tau": float(tau),
        }
        row_all.update(metrics_all)
        rows.append(row_all)

        # Per-workload
        for wl in np.unique(test_workloads):
            mask = test_workloads == wl
            y_w = test_labels[mask]
            if y_w.size < 2 or np.unique(y_w).size < 2:
                continue
            pred_w = test_pred[mask]
            prob_w = test_probs[mask]
            met_w = compute_binary_metrics(y_w, pred_w, prob_w)
            row_w = dict(row_all)
            row_w["workload"] = str(wl)
            row_w["n_test"] = int(y_w.size)
            row_w["n_benign"] = int((y_w == 0).sum())
            row_w["n_anom"] = int((y_w == 1).sum())
            row_w.update(met_w)
            rows.append(row_w)

    return rows


def run_exact_eval_for_setup(
    *,
    setup: str,
    df: pd.DataFrame,
    model: CINTASModel,
    scenarios_eval: Iterable[str],
    window_sizes: Iterable[int],
    n_splits_list: Iterable[int] = (5,),
    default_p_quantile: float = 0.99,
    agg_mode: str = "max",
    droop_cfg: DroopConfig | None = None,
    seed: int = 123,
) -> pd.DataFrame:
    """Run the draft-style evaluation loop for one setup.

    Parameters
    ----------
    df:
        Single-setup telemetry dataframe (with scenario/workload/time_idx).
    model:
        Fitted CINTASModel.
    droop_cfg:
        If provided, overrides settings for DROOP scenario (used in notebook).
    """
    setup_u = setup.upper()

    rows = []
    for scen in scenarios_eval:
        scen_u = scen.upper()
        for W in window_sizes:
            for n_splits in n_splits_list:
                if droop_cfg is not None and scen_u == "DROOP":
                    lambda_res = droop_cfg.lambda_res
                    p_quantile = droop_cfg.p_quantile
                    agg = droop_cfg.agg_mode
                else:
                    lambda_res = model.lambda_res
                    p_quantile = default_p_quantile
                    agg = agg_mode

                win_df = build_window_dataset(
                    df,
                    model=model,
                    scenario_anom=scen_u,
                    window_size=int(W),
                    agg_mode=agg,
                    balance_per_workload=True,
                    seed=seed,
                )
                if win_df.empty:
                    continue

                fold_rows = evaluate_windows_kfold(
                    win_df,
                    setup=setup_u,
                    scenario_eval=scen_u,
                    window_size=int(W),
                    agg_mode=agg,
                    lambda_res=float(lambda_res),
                    p_quantile=float(p_quantile),
                    n_splits=int(n_splits),
                    seed=seed,
                )
                rows.extend(fold_rows)

    return pd.DataFrame(rows)


def save_exact_summaries_for_setup(setup: str, results_df: pd.DataFrame, out_dir: Path) -> None:
    """Save global + per-workload summaries, similar to EXACT.ipynb."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = results_df.copy()
    setup_u = setup.upper()

    # Global summary (workload=ALL), averaged over folds
    global_df = df[df["workload"] == "ALL"].copy()
    if not global_df.empty:
        g = (
            global_df.groupby(["scenario", "window_size"], as_index=False)
            .agg(
                auc_roc=("auc_roc", "mean"),
                auc_pr=("auc_pr", "mean"),
                f1=("f1", "mean"),
                bal_acc=("bal_acc", "mean"),
                mcc=("mcc", "mean"),
                brier=("brier", "mean"),
                ece=("ece", "mean"),
                n_test=("n_test", "mean"),
            )
            .sort_values(["scenario", "window_size"])
        )
        g.to_csv(out_dir / f"SETUP_{setup_u}_EXACT_summary_global.csv", index=False)

    # Per-workload summary, averaged over folds
    per_wl_df = df[df["workload"] != "ALL"].copy()
    if not per_wl_df.empty:
        p = (
            per_wl_df.groupby(["scenario", "workload", "window_size"], as_index=False)
            .agg(
                auc_roc=("auc_roc", "mean"),
                auc_pr=("auc_pr", "mean"),
                f1=("f1", "mean"),
                bal_acc=("bal_acc", "mean"),
                mcc=("mcc", "mean"),
                brier=("brier", "mean"),
                ece=("ece", "mean"),
                n_test=("n_test", "mean"),
            )
            .sort_values(["scenario", "workload", "window_size"])
        )
        p.to_csv(out_dir / f"SETUP_{setup_u}_EXACT_summary_per_workload.csv", index=False)
