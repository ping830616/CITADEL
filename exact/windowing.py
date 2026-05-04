from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import pandas as pd

from .preprocessing import get_feature_columns
from .cintas import CINTASModel


AggMode = Literal["mean", "max", "median"]


def score_samples(df: pd.DataFrame, model: CINTASModel) -> np.ndarray:
    """Compute per-sample CINTAS scores for every row."""
    score, _, _ = model.score_dataframe(df)
    return score


def build_window_dataset(
    df: pd.DataFrame,
    model: CINTASModel,
    *,
    scenario_anom: str,
    window_size: int,
    agg_mode: AggMode = "max",
    balance_per_workload: bool = True,
    seed: int = 123,
    scenario_col: str = "scenario",
    workload_col: str = "workload",
    time_col: str = "time_idx",
) -> pd.DataFrame:
    """Build a benign-vs-anomaly window dataset for one anomaly scenario.

    Matches the logic in EXACT.ipynb (S6):
      * Keep only BENIGN and the specified anomaly scenario.
      * Split into non-overlapping windows per (workload, scenario).
      * Aggregate per-window scores with mean/max/median.
      * Optionally balance benign/anomaly windows per workload.

    Returns a table with one row per window:
      setup, scenario, workload, window_size, agg_mode, score_win, label
    """
    rng = np.random.default_rng(seed)

    if "setup" not in df.columns:
        raise KeyError("df must contain a 'setup' column.")
    setup_vals = df["setup"].unique()
    if len(setup_vals) != 1:
        raise ValueError(f"df must contain exactly one setup; got {setup_vals}.")

    setup = str(setup_vals[0])

    scen_anom_u = scenario_anom.upper()
    df_sub = df[df[scenario_col].astype(str).str.upper().isin(["BENIGN", scen_anom_u])].copy()
    if df_sub.empty:
        return pd.DataFrame()

    if time_col not in df_sub.columns:
        df_sub[time_col] = df_sub.groupby([scenario_col, workload_col]).cumcount()

    df_sub = df_sub.sort_values([workload_col, scenario_col, time_col]).reset_index(drop=True)

    df_sub["score_sample"] = score_samples(df_sub, model)

    rows = []
    for wl, df_w in df_sub.groupby(workload_col):
        df_b = df_w[df_w[scenario_col].astype(str).str.upper() == "BENIGN"]
        df_a = df_w[df_w[scenario_col].astype(str).str.upper() == scen_anom_u]

        s_b = df_b["score_sample"].to_numpy(dtype=float)
        s_a = df_a["score_sample"].to_numpy(dtype=float)

        if s_b.size < window_size or s_a.size < window_size:
            continue

        n_win_b = s_b.size // window_size
        n_win_a = s_a.size // window_size

        if balance_per_workload:
            n_win = min(n_win_b, n_win_a)
            n_win_b = n_win_a = n_win

        def _agg(scores_1d: np.ndarray, n_win: int) -> np.ndarray:
            out = []
            for i in range(n_win):
                start = i * window_size
                end = start + window_size
                w_scores = scores_1d[start:end]
                if w_scores.size < window_size:
                    break
                if agg_mode == "mean":
                    s_win = float(w_scores.mean())
                elif agg_mode == "median":
                    s_win = float(np.median(w_scores))
                else:  # "max"
                    s_win = float(w_scores.max())
                out.append(s_win)
            return np.asarray(out, dtype=float)

        win_scores_b = _agg(s_b, n_win_b)
        win_scores_a = _agg(s_a, n_win_a)

        for s in win_scores_b:
            rows.append({
                "setup": setup,
                "scenario": scen_anom_u,
                "workload": str(wl),
                "window_size": int(window_size),
                "agg_mode": str(agg_mode),
                "score_win": float(s),
                "label": 0,
            })
        for s in win_scores_a:
            rows.append({
                "setup": setup,
                "scenario": scen_anom_u,
                "workload": str(wl),
                "window_size": int(window_size),
                "agg_mode": str(agg_mode),
                "score_win": float(s),
                "label": 1,
            })

    return pd.DataFrame(rows)
