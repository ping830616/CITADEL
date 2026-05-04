from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from .io import META_COLS_BASE


def get_feature_columns(df: pd.DataFrame, meta_cols: Iterable[str] | None = None) -> list[str]:
    """Return numeric telemetry columns used as features.

    The draft notebooks treat all numeric columns as candidate telemetry features
    except for meta/label columns.
    """
    meta = set(META_COLS_BASE if meta_cols is None else meta_cols)
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    return [c for c in numeric_cols if c not in meta]


def clean_and_debias_telemetry(
    df: pd.DataFrame,
    scenario_col: str = "scenario",
    benign_name: str = "BENIGN",
    inplace: bool = False,
) -> pd.DataFrame:
    """Simple cleaning + benign de-biasing (from EXACT.ipynb).

    Steps
    -----
    1) Drop rows where *all* numeric feature columns are NaN.
    2) Fill remaining NaNs with BENIGN means if BENIGN exists else global means.
    3) Subtract BENIGN means (or global means) from every sample.

    Notes
    -----
    This is intentionally minimal and matches the draft notebook behavior.
    If you have monotonic counters, you may want to convert them to per-sample
    deltas before calling this function.
    """
    df2 = df if inplace else df.copy()

    feature_cols = get_feature_columns(df2)
    if not feature_cols:
        raise ValueError("No numeric feature columns found for telemetry.")

    # Drop rows where all feature columns are NaN
    mask_all_nan = df2[feature_cols].isna().all(axis=1)
    if mask_all_nan.any():
        df2 = df2.loc[~mask_all_nan].reset_index(drop=True)

    # Compute BENIGN means if available
    if scenario_col in df2.columns:
        ben_mask = df2[scenario_col].astype(str).str.upper() == benign_name.upper()
        if ben_mask.any():
            benign_means = df2.loc[ben_mask, feature_cols].mean(axis=0)
            df2[feature_cols] = df2[feature_cols].fillna(benign_means)
            df2[feature_cols] = df2[feature_cols] - benign_means
        else:
            global_means = df2[feature_cols].mean(axis=0)
            df2[feature_cols] = df2[feature_cols].fillna(global_means)
            df2[feature_cols] = df2[feature_cols] - global_means
    else:
        global_means = df2[feature_cols].mean(axis=0)
        df2[feature_cols] = df2[feature_cols].fillna(global_means)
        df2[feature_cols] = df2[feature_cols] - global_means

    return df2


def drop_constant_features(df: pd.DataFrame, feature_cols: list[str] | None = None) -> list[str]:
    """Return the subset of feature columns that are non-constant."""
    if feature_cols is None:
        feature_cols = get_feature_columns(df)
    keep = []
    for c in feature_cols:
        s = df[c]
        if s.nunique(dropna=True) > 1:
            keep.append(c)
    return keep
