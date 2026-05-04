from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    f1_score,
    balanced_accuracy_score,
    matthews_corrcoef,
    brier_score_loss,
)


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error (ECE) for binary probabilities."""
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob).astype(float)

    if y_true.size == 0:
        return float("nan")
    if np.unique(y_true).size < 2:
        return 0.0

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0

    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        if i < n_bins - 1:
            mask = (y_prob >= lo) & (y_prob < hi)
        else:
            mask = (y_prob >= lo) & (y_prob <= hi)
        if not np.any(mask):
            continue
        p_bin = float(y_prob[mask].mean())
        y_bin = float(y_true[mask].mean())
        w_bin = float(mask.mean())
        ece += w_bin * abs(p_bin - y_bin)

    return float(ece)


def _safe_binary_metric(fn, y_true, y_score_or_pred, default=np.nan, **kwargs) -> float:
    y_true = np.asarray(y_true).astype(int)
    if y_true.size == 0 or np.unique(y_true).size < 2:
        return float(default)
    try:
        return float(fn(y_true, y_score_or_pred, **kwargs))
    except Exception:
        return float(default)


def compute_binary_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray) -> dict:
    """Compute detection metrics (AUC-ROC/PR, F1, bal-acc, MCC, Brier, ECE)."""
    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    y_prob = np.asarray(y_prob).astype(float)

    auc_roc = _safe_binary_metric(roc_auc_score, y_true, y_prob, default=np.nan)
    auc_pr = _safe_binary_metric(average_precision_score, y_true, y_prob, default=np.nan)
    f1 = _safe_binary_metric(f1_score, y_true, y_pred, default=0.0)
    bal_acc = _safe_binary_metric(balanced_accuracy_score, y_true, y_pred, default=0.5)
    mcc = _safe_binary_metric(matthews_corrcoef, y_true, y_pred, default=0.0)
    brier = _safe_binary_metric(brier_score_loss, y_true, y_prob, default=np.nan)
    ece = expected_calibration_error(y_true, y_prob, n_bins=10)

    return {
        "auc_roc": auc_roc,
        "auc_pr": auc_pr,
        "f1": f1,
        "bal_acc": bal_acc,
        "mcc": mcc,
        "brier": brier,
        "ece": ece,
    }
