from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

try:
    import networkx as nx
except Exception:  # pragma: no cover
    nx = None

import matplotlib.pyplot as plt


def assign_feature_domain(feat: str) -> str:
    """Heuristic mapping from feature name to domain (EXACT.ipynb).

    Returns one of: CORE, MEMORY, SENSOR
    """
    name = feat.lower()
    if any(tok in name for tok in ["temp", "therm", "pk", "pkg", "pwr", "power", "volt", "vcc"]):
        return "SENSOR"
    if any(tok in name for tok in ["dram", "mem", "imc", "unc_m", "llc", "l3", "l2", "dimm"]):
        return "MEMORY"
    return "CORE"


def build_edges_from_corr(
    corr_df: pd.DataFrame,
    corr_threshold: float = 0.35,
) -> pd.DataFrame:
    """Turn a correlation matrix into an edge list (directional heuristic)."""
    features = list(corr_df.columns)
    domains = {f: assign_feature_domain(f) for f in features}
    domain_order = {"CORE": 0, "MEMORY": 1, "SENSOR": 2}

    rows = []
    for i, f_i in enumerate(features):
        for j in range(i + 1, len(features)):
            f_j = features[j]
            rho = float(corr_df.iloc[i, j])
            if not np.isfinite(rho) or abs(rho) < corr_threshold:
                continue

            dom_i = domains[f_i]
            dom_j = domains[f_j]

            if domain_order[dom_i] < domain_order[dom_j]:
                src, dst = f_i, f_j
            elif domain_order[dom_j] < domain_order[dom_i]:
                src, dst = f_j, f_i
            else:
                src, dst = (f_i, f_j) if f_i <= f_j else (f_j, f_i)

            rows.append({"src": src, "dst": dst, "rho": rho, "abs_rho": abs(rho)})
    return pd.DataFrame(rows)


def compute_degree_centrality(
    features: list[str],
    edges_df: pd.DataFrame,
) -> Dict[str, float]:
    """Degree centrality on the undirected skeleton (normalized)."""
    n = max(len(features) - 1, 1)
    deg_counts = {f: 0 for f in features}
    if edges_df is None or edges_df.empty:
        return {f: 0.0 for f in features}
    for row in edges_df.itertuples():
        deg_counts[row.src] += 1
        deg_counts[row.dst] += 1
    return {f: deg_counts[f] / n for f in features}


def compute_feature_cias_alignment(
    df: pd.DataFrame,
    features: list[str],
    *,
    score_col: str = "cias_sample_score",
    scenarios: tuple[str, ...] = ("DROOP", "RH", "SPECTRE"),
) -> Dict[str, float]:
    """Average |Spearman rho| between each feature and score_col over scenarios."""
    corr_map = {f: [] for f in features}
    df2 = df.copy()
    df2["scenario"] = df2["scenario"].astype(str).str.upper()

    for scen in scenarios:
        df_s = df2[df2["scenario"] == scen.upper()]
        if df_s.empty:
            continue
        for f in features:
            if f not in df_s.columns:
                continue
            sub = df_s[[f, score_col]].dropna()
            if sub[f].nunique() <= 1 or sub[score_col].nunique() <= 1:
                continue
            rho = sub.corr(method="spearman").iloc[0, 1]
            if np.isfinite(rho):
                corr_map[f].append(abs(float(rho)))

    return {f: float(np.mean(vals)) if vals else 0.0 for f, vals in corr_map.items()}


def build_causal_and_rank_features_for_setup(
    *,
    setup: str,
    df: pd.DataFrame,
    feature_cols: list[str],
    out_root: Path,
    corr_threshold: float = 0.35,
    top_k_plot: int = 20,
    score_col: str = "cias_sample_score",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build benign correlation skeleton + rank features (EXACT.ipynb S10)."""
    setup_u = setup.upper()
    df_setup = df[df["setup"].astype(str).str.upper() == setup_u].copy()
    if df_setup.empty:
        raise ValueError(f"No rows found for setup={setup_u} in df.")

    df_ben = df_setup[df_setup["scenario"].astype(str).str.upper() == "BENIGN"].copy()
    if df_ben.empty:
        raise ValueError(f"No BENIGN rows found for setup={setup_u}.")

    feats = [f for f in feature_cols if f in df_ben.columns]
    if not feats:
        raise ValueError("None of feature_cols are present in the BENIGN dataframe.")

    corr_df = df_ben[feats].astype(float).corr(method="spearman")
    edges_df = build_edges_from_corr(corr_df, corr_threshold=corr_threshold)
    centrality = compute_degree_centrality(feats, edges_df)
    align = compute_feature_cias_alignment(df_setup, feats, score_col=score_col)

    g = np.array([centrality[f] for f in feats], dtype=float)
    a = np.array([align[f] for f in feats], dtype=float)
    g_norm = g / max(g.max(), 1e-8)
    a_norm = a / max(a.max(), 1e-8)
    imp = g_norm * a_norm
    imp_norm = imp / max(imp.max(), 1e-8)

    domains = {f: assign_feature_domain(f) for f in feats}

    nodes_df = pd.DataFrame({
        "feature": feats,
        "domain": [domains[f] for f in feats],
        "graph_centrality": g_norm,
        "cias_alignment": a_norm,
        "importance_score": imp_norm,
    })
    ranks_df = nodes_df.sort_values("importance_score", ascending=False).reset_index(drop=True)

    causal_dir = Path(out_root) / "causal"
    causal_dir.mkdir(parents=True, exist_ok=True)

    nodes_df.to_csv(causal_dir / f"SETUP_{setup_u}_causal_nodes.csv", index=False)
    edges_df.to_csv(causal_dir / f"SETUP_{setup_u}_causal_edges.csv", index=False)
    ranks_df.to_csv(causal_dir / f"SETUP_{setup_u}_feature_ranks.csv", index=False)

    # Optional combined plot
    if nx is not None and len(ranks_df):
        try:
            _plot_causal_and_topk(
                setup=setup_u,
                nodes_df=nodes_df,
                edges_df=edges_df,
                ranks_df=ranks_df,
                out_path=causal_dir / f"SETUP_{setup_u}_causal_graph_and_top{top_k_plot}.png",
                top_k=top_k_plot,
            )
        except Exception:
            pass

    return nodes_df, edges_df, ranks_df


def export_edges_for_fig5(edges_df: pd.DataFrame, out_csv: Path) -> None:
    """Export a CSV compatible with the Fig.5 plotting helper from EXACT-2.

    Output columns:
      u, v, strength, domain_u, domain_v
    """
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    def dom(name: str) -> str:
        d = assign_feature_domain(name)
        return {"CORE": "compute", "MEMORY": "memory", "SENSOR": "sensors"}.get(d, "compute")

    rows = []
    for r in edges_df.itertuples():
        u = str(r.src)
        v = str(r.dst)
        strength = float(getattr(r, "abs_rho", getattr(r, "rho", 0.0)))
        rows.append({
            "u": u,
            "v": v,
            "strength": strength,
            "domain_u": dom(u),
            "domain_v": dom(v),
        })
    pd.DataFrame(rows).to_csv(out_csv, index=False)


def _plot_causal_and_topk(
    *,
    setup: str,
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    ranks_df: pd.DataFrame,
    out_path: Path,
    top_k: int = 20,
) -> None:
    if nx is None:
        return

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    domains = {r.feature: r.domain for r in nodes_df.itertuples()}
    dom_y = {"CORE": 0.0, "MEMORY": 1.0, "SENSOR": 2.0}

    # Graph
    G = nx.DiGraph()
    for r in nodes_df.itertuples():
        G.add_node(r.feature, domain=r.domain, importance=r.importance_score)
    for r in edges_df.itertuples():
        G.add_edge(r.src, r.dst, weight=r.abs_rho)

    pos = {}
    by_dom = {"CORE": [], "MEMORY": [], "SENSOR": []}
    for n, d in G.nodes(data=True):
        by_dom.setdefault(d.get("domain", "CORE"), []).append(n)
    for dom, ns in by_dom.items():
        if not ns:
            continue
        xs = np.linspace(0.0, 1.0, len(ns))
        y = dom_y.get(dom, 0.0)
        for x, n in zip(xs, ns):
            pos[n] = (float(x), float(y))

    # Bar chart
    top_k = min(top_k, len(ranks_df))
    top = ranks_df.head(top_k)

    fig = plt.figure(figsize=(14, 6))
    ax_g = fig.add_subplot(1, 2, 1)
    ax_b = fig.add_subplot(1, 2, 2)

    color_map = {"CORE": "#1f77b4", "MEMORY": "#2ca02c", "SENSOR": "#ff7f0e"}

    nx.draw_networkx_edges(G, pos, ax=ax_g, alpha=0.2, arrows=False)
    nx.draw_networkx_nodes(
        G, pos, ax=ax_g,
        node_size=[250 + 1200 * float(G.nodes[n].get("importance", 0.0)) for n in G.nodes()],
        node_color=[color_map.get(domains.get(n, "CORE"), "#aaaaaa") for n in G.nodes()],
        linewidths=0.8, edgecolors="#333333"
    )
    ax_g.set_title(f"Setup {setup}: benign correlation skeleton")
    ax_g.axis("off")

    ax_b.barh(top["feature"][::-1], top["importance_score"][::-1])
    ax_b.set_title(f"Top-{top_k} ranked telemetry features")
    ax_b.set_xlabel("importance_score")
    ax_b.grid(True, axis="x", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
