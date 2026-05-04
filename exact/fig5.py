from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import networkx as nx
from matplotlib.patches import Patch


# ---------------------------------------------------------------------
# Domain inference (copied from EXACT-2-Copy1.ipynb, trimmed)
# ---------------------------------------------------------------------
MEM_PAT = re.compile(r"(L[123]|\bLLC\b|CACHE|L3MISS|LLCMISS|DRAM|MEM(?!S)|BW)", re.IGNORECASE)
SEN_PAT = re.compile(r"(TEMP|THERM|Tdie|FAN|VOLT|POWER|ENERGY|SENSOR|THRM)", re.IGNORECASE)
CMP_PAT = re.compile(r"(ACYC|CPI|IPC|INST|C0res|C7res|TIME\(ticks\)|CYC|UOPS|ALU|CORE|SYSTEM|SOCKET)", re.IGNORECASE)

def infer_domain(name: str) -> str:
    if MEM_PAT.search(name): return "memory"
    if SEN_PAT.search(name): return "sensors"
    if CMP_PAT.search(name): return "compute"
    return "compute"


def _safe_savefig(path: Path, fig=None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fig is None:
        plt.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
        plt.close()
    else:
        fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
        plt.close(fig)


def _normalize_pos_to_circle(pos: dict, r: float = 1.0) -> dict:
    if not pos:
        return pos
    xy = np.array(list(pos.values()), dtype=float)
    xy = xy - xy.mean(axis=0, keepdims=True)
    rad = np.sqrt((xy**2).sum(axis=1))
    m = rad.max() if rad.size else 1.0
    if m > 0:
        xy = (r * 0.98) * xy / m
    return {n: tuple(xy[i]) for i, n in enumerate(pos.keys())}


def _pick_majority(dct: dict) -> str:
    order = ["compute", "memory", "sensors", "other"]
    if not dct:
        return "other"
    m = max(dct.values())
    cands = [k for k, v in dct.items() if v == m]
    for k in order:
        if k in cands:
            return k
    return "other"


def _scale_size(deg_map: dict, n: str, lo=220.0, hi=520.0) -> float:
    if not deg_map:
        return (lo + hi) / 2
    dvals = list(deg_map.values())
    dmin, dmax = min(dvals), max(dvals)
    d = deg_map.get(n, dmin)
    if dmax == dmin:
        return (lo + hi) / 2
    return lo + (hi - lo) * (d - dmin) / (dmax - dmin)


def _clean_name(n: str) -> str:
    n = str(n)
    if "Core" in n and "Socket" in n:
        try:
            core_id = n.split("Core", 1)[1].split("(", 1)[0].strip()
            metric = n.split(".", 1)[1].split("_")[-1] if "." in n else n.split("_")[-1]
            return f"C{core_id}.{metric}"
        except Exception:
            return n
    if "System" in n:
        parts = n.split(".", 1)
        return f"Sys.{parts[1]}" if len(parts) > 1 else "System"
    if "Socket" in n and "Core" not in n:
        parts = n.split(".", 1)
        return f"Socket.{parts[1]}" if len(parts) > 1 else "Socket"
    return n


def _draw_labels_with_boxes(ax, pos, label_nodes, fontsize=11, radial_offset=0.03) -> None:
    if not label_nodes:
        return
    xy = np.array([pos[n] for n in label_nodes if n in pos], dtype=float)
    if xy.size == 0:
        return
    center = xy.mean(axis=0)

    for n in label_nodes:
        if n not in pos:
            continue
        x, y = pos[n]
        v = np.array([x, y]) - center
        nv = np.linalg.norm(v)
        if nv > 0:
            v = v / nv
            x2, y2 = (np.array([x, y]) + radial_offset * v).tolist()
        else:
            x2, y2 = x, y

        t = ax.text(
            x2, y2, _clean_name(n),
            fontsize=fontsize,
            fontweight="bold",
            ha="center", va="center",
            zorder=10,
            bbox=dict(
                boxstyle="round,pad=0.25,rounding_size=0.15",
                facecolor="white",
                edgecolor="none",
                alpha=0.90
            )
        )
        t.set_path_effects([pe.withStroke(linewidth=2, foreground="white")])


def _load_edges_csv(edges_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(edges_csv)
    # Required columns: u, v, strength. Domains are optional.
    if not {"u", "v", "strength"}.issubset(df.columns):
        raise ValueError(f"Edges CSV must include columns u,v,strength. Got: {list(df.columns)}")
    return df


def _build_3domain_graph(edges_df: pd.DataFrame) -> tuple[nx.Graph, dict, dict]:
    # Ensure domains exist
    df = edges_df.copy()
    if "domain_u" not in df.columns:
        df["domain_u"] = df["u"].map(lambda s: infer_domain(str(s)))
    if "domain_v" not in df.columns:
        df["domain_v"] = df["v"].map(lambda s: infer_domain(str(s)))

    # normalize strength to [0,1]
    s = df["strength"].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0).values
    if len(s) and np.nanmax(s) > np.nanmin(s):
        s_norm = (s - np.nanmin(s)) / (np.nanmax(s) - np.nanmin(s))
    else:
        s_norm = np.zeros_like(s)
    df["strength_norm"] = s_norm

    G = nx.Graph()
    for _, r in df.iterrows():
        u, v = str(r["u"]), str(r["v"])
        w = float(r["strength_norm"])
        du, dv = str(r["domain_u"]).lower(), str(r["domain_v"]).lower()
        G.add_node(u); G.add_node(v)
        G.add_edge(u, v, strength=w, domain_u=du, domain_v=dv)

    # node domain by majority incidence
    domain_counts = {}
    for u, v, d in G.edges(data=True):
        for node, dn in [(u, d.get("domain_u", "other")), (v, d.get("domain_v", "other"))]:
            domain_counts.setdefault(node, {"compute": 0, "memory": 0, "sensors": 0, "other": 0})
            domain_counts[node][dn if dn in domain_counts[node] else "other"] += 1

    node_domain = {n: _pick_majority(domain_counts.get(n, {})) for n in G.nodes()}
    keep_nodes = [n for n, dn in node_domain.items() if dn in {"compute", "memory", "sensors"}]
    G3 = G.subgraph(keep_nodes).copy()
    deg = dict(G3.degree())
    return G3, node_domain, deg


def _draw_one_panel(ax, G3: nx.Graph, node_domain: dict, deg: dict, title: str, k_full: float, seed: int, label_only_top_n: int) -> None:
    domain_colors = {"compute": "#9ecae1", "memory": "#a1d99b", "sensors": "#fdae6b"}

    if G3.number_of_nodes() == 0:
        ax.set_title(title, fontsize=18, fontweight="bold", pad=10)
        ax.axis("off")
        return

    pos = nx.spring_layout(G3, k=k_full, iterations=300, seed=seed)
    pos = _normalize_pos_to_circle(pos, r=1.0)

    node_sizes = [_scale_size(deg, n) for n in G3.nodes()]
    node_colors = [domain_colors.get(node_domain.get(n, "other"), "#bdbdbd") for n in G3.nodes()]

    edge_strengths = [G3[u][v].get("strength", 0.0) for u, v in G3.edges()]
    edge_colors = [plt.cm.viridis(x) for x in edge_strengths]
    edge_widths = [0.35 + 1.4 * x for x in edge_strengths]

    nx.draw_networkx_edges(G3, pos, edge_color=edge_colors, width=edge_widths, alpha=0.20, ax=ax)
    nx.draw_networkx_nodes(
        G3, pos,
        node_size=node_sizes,
        node_color=node_colors,
        alpha=0.95,
        edgecolors="#2f2f2f",
        linewidths=1.0,
        ax=ax
    )

    # label selection
    top_nodes = [n for n, _ in sorted(deg.items(), key=lambda t: t[1], reverse=True)[:label_only_top_n]]
    _draw_labels_with_boxes(ax, pos, top_nodes, fontsize=10, radial_offset=0.035)

    ax.set_title(title, fontsize=18, fontweight="bold", pad=10)
    ax.axis("off")


def plot_benign_sparse_causal_network_two_panel(
    *,
    edges_csv_A: Path,
    edges_csv_B: Path,
    out_png: Path,
    title_A: str = "Setup A",
    title_B: str = "Setup B",
    label_only_top_n: int = 12,
    spring_k: float = 10.0,
    seed: int = 42,
) -> None:
    """Create the two-panel network plot (Fig. 5 style)."""
    edges_A = _load_edges_csv(Path(edges_csv_A))
    edges_B = _load_edges_csv(Path(edges_csv_B))

    G3A, node_dom_A, deg_A = _build_3domain_graph(edges_A)
    G3B, node_dom_B, deg_B = _build_3domain_graph(edges_B)

    fig, axes = plt.subplots(1, 2, figsize=(18, 7))
    axA, axB = axes

    _draw_one_panel(axA, G3A, node_dom_A, deg_A, title_A, spring_k, seed, label_only_top_n)
    _draw_one_panel(axB, G3B, node_dom_B, deg_B, title_B, spring_k, seed, label_only_top_n)

    # Legend + shared colorbar
    domain_colors = {"compute": "#9ecae1", "memory": "#a1d99b", "sensors": "#fdae6b"}
    legend_elements = [
        Patch(facecolor=domain_colors["compute"], label="Compute", alpha=0.95),
        Patch(facecolor=domain_colors["memory"],  label="Memory",  alpha=0.95),
        Patch(facecolor=domain_colors["sensors"], label="Sensors", alpha=0.95),
    ]
    axB.legend(handles=legend_elements, loc="upper left", bbox_to_anchor=(1.02, 1.02),
               frameon=False, fontsize=12)

    sm = plt.cm.ScalarMappable(cmap=plt.cm.viridis, norm=plt.Normalize(vmin=0.0, vmax=1.0))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes.ravel().tolist(), fraction=0.03, pad=0.02)
    cbar.set_label("Connection strength (normalized)", rotation=270, labelpad=18)

    fig.tight_layout()
    _safe_savefig(Path(out_png), fig=fig)
