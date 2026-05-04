from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def plot_metrics_vs_window_size(
    *,
    per_workload_csv_A: Path,
    per_workload_csv_B: Path,
    out_png: Path,
    n_splits: int = 5,
    metrics: list[tuple[str, str, float | None, float | None]] | None = None,
    title: str = "Performance vs Decision-Block Length",
) -> None:
    """Recreate the 'MCC / Balanced Accuracy / Brier vs window length' style plot.

    Inputs are the per-workload summary CSVs produced by save_exact_summaries_for_setup().
    """
    if metrics is None:
        metrics = [
            ("mcc", "MCC", 0.5, 1.0),
            ("bal_acc", "Balanced Accuracy", 0.5, 1.0),
            ("brier", "Brier Score", None, None),
        ]

    df_a = pd.read_csv(per_workload_csv_A)
    df_b = pd.read_csv(per_workload_csv_B)

    if "n_splits" in df_a.columns:
        df_a = df_a[df_a["n_splits"] == n_splits]
    if "n_splits" in df_b.columns:
        df_b = df_b[df_b["n_splits"] == n_splits]

    window_sizes = sorted(set(df_a["window_size"].unique()).union(set(df_b["window_size"].unique())))

    fig, axes = plt.subplots(nrows=len(metrics), ncols=1, figsize=(12, 12), sharex=True)
    if len(metrics) == 1:
        axes = [axes]

    # Colors (match notebook)
    setup_a_color = "#1E88E5"
    setup_b_color = "#8B0000"

    for ax, (metric_col, metric_label, y_min, y_max) in zip(axes, metrics):
        # scatter points per workload
        for W in window_sizes:
            a_w = df_a[df_a["window_size"] == W]
            b_w = df_b[df_b["window_size"] == W]
            ax.scatter([W] * len(a_w), a_w[metric_col], s=18, color=setup_a_color, alpha=0.35, linewidths=0)
            ax.scatter([W] * len(b_w), b_w[metric_col], s=18, color=setup_b_color, alpha=0.35, linewidths=0)

        # mean lines across workloads
        a_mean = df_a.groupby("window_size")[metric_col].mean().reindex(window_sizes)
        b_mean = df_b.groupby("window_size")[metric_col].mean().reindex(window_sizes)
        ax.plot(window_sizes, a_mean.values, color=setup_a_color, linewidth=2.5, label="Setup A (mean)")
        ax.plot(window_sizes, b_mean.values, color=setup_b_color, linewidth=2.5, linestyle="--", label="Setup B (mean)")

        ax.set_ylabel(metric_label)
        ax.grid(True, alpha=0.25)
        if y_min is not None and y_max is not None:
            ax.set_ylim(y_min, y_max)

    axes[-1].set_xlabel("Decision-block length (window_size)")
    axes[0].set_title(title)

    axes[0].legend(loc="lower right")

    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_png, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
