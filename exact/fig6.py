from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D


def _domain_color(domain: str) -> str:
    d = str(domain).upper()
    if d == "CORE":
        return "#1f77b4"  # blue
    if d == "MEMORY":
        return "#9467bd"  # purple
    if d == "SENSOR":
        return "#ff7f0e"  # orange
    return "#7f7f7f"


def plot_topk_features_two_panel(
    *,
    ranks_csv_A: Path,
    ranks_csv_B: Path,
    out_png: Path,
    top_k: int = 15,
    title: str = "Feature Importance Analysis",
    setupA_label: str = "Setup A",
    setupB_label: str = "Setup B",
    hatch_align_quantile: float = 0.75,
    star_centrality_quantile: float = 0.75,
) -> None:
    """Produce a Fig. 6-style top-k feature bar plot.

    This uses the rank CSVs produced by `exact.causal_corr.build_causal_and_rank_features_for_setup`.

    Expected columns in each ranks CSV:
      - feature
      - domain (CORE/MEMORY/SENSOR)
      - importance_score
      - graph_centrality
      - cias_alignment
    """
    dfA = pd.read_csv(ranks_csv_A).copy()
    dfB = pd.read_csv(ranks_csv_B).copy()

    def prep(df: pd.DataFrame) -> pd.DataFrame:
        # tolerate older column naming
        if "score_alignment" in df.columns and "cias_alignment" not in df.columns:
            df = df.rename(columns={"score_alignment": "cias_alignment"})
        for col in ["importance_score", "graph_centrality", "cias_alignment"]:
            if col not in df.columns:
                raise ValueError(f"Missing column '{col}' in ranks CSV. Columns={list(df.columns)}")
        return df

    dfA = prep(dfA)
    dfB = prep(dfB)

    dfA = dfA.head(top_k).iloc[::-1].reset_index(drop=True)
    dfB = dfB.head(top_k).iloc[::-1].reset_index(drop=True)

    # thresholds for hatch/star
    hatch_thr_A = float(dfA["cias_alignment"].quantile(hatch_align_quantile))
    hatch_thr_B = float(dfB["cias_alignment"].quantile(hatch_align_quantile))
    star_thr_A  = float(dfA["graph_centrality"].quantile(star_centrality_quantile))
    star_thr_B  = float(dfB["graph_centrality"].quantile(star_centrality_quantile))

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=False)
    axA, axB = axes

    def draw(ax, df, setup_label, hatch_thr, star_thr):
        y = np.arange(len(df))
        colors = [_domain_color(d) for d in df["domain"]]
        bars = ax.barh(y, df["importance_score"], color=colors, edgecolor="#333333", linewidth=0.8)

        # Apply hatching for strong alignment
        for bar, align in zip(bars, df["cias_alignment"]):
            if float(align) >= hatch_thr:
                bar.set_hatch("///")
                bar.set_alpha(0.95)

        # Star for high centrality (placed near bar end)
        for yi, (imp, cent) in enumerate(zip(df["importance_score"], df["graph_centrality"])):
            if float(cent) >= star_thr:
                ax.scatter([float(imp)], [yi], marker="*", s=80, color="red", zorder=5)

        ax.set_yticks(y)
        ax.set_yticklabels(df["feature"], fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel("Feature importance")
        ax.set_title(setup_label)
        ax.grid(True, axis="x", alpha=0.25)

    draw(axA, dfA, setupA_label, hatch_thr_A, star_thr_A)
    draw(axB, dfB, setupB_label, hatch_thr_B, star_thr_B)

    # Legends
    legend_domains = [
        Patch(facecolor=_domain_color("CORE"), label="CORE"),
        Patch(facecolor=_domain_color("MEMORY"), label="MEMORY"),
        Patch(facecolor=_domain_color("SENSOR"), label="SENSORS"),
    ]
    legend_markers = [
        Patch(facecolor="white", edgecolor="#333333", hatch="///", label="High CINTAS alignment"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor="red", markersize=12, label="High graph centrality"),
    ]
    axB.legend(handles=legend_domains + legend_markers, loc="lower right", fontsize=9, frameon=True)

    fig.suptitle(title, fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0.02, 1, 0.95])

    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
