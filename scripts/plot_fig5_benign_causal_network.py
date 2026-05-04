#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from exact.repro import configure_reproducibility


def main() -> None:
    p = argparse.ArgumentParser(description="Plot the benign sparse causal network (Fig. 5 style).")
    p.add_argument("--edges-a", type=Path, required=True, help="CSV with columns u,v,strength,(optional)domain_u,domain_v for Setup A.")
    p.add_argument("--edges-b", type=Path, required=True, help="CSV with columns u,v,strength,(optional)domain_u,domain_v for Setup B.")
    p.add_argument("--out", type=Path, default=Path("./results/figures/fig5_benign_sparse_causal_network.png"))
    p.add_argument("--title-a", type=str, default="Setup A")
    p.add_argument("--title-b", type=str, default="Setup B")
    p.add_argument("--seed", type=int, default=42, help="Seed passed to the graph layout.")
    p.add_argument("--threads", type=int, default=1, help="Thread cap for deterministic numerical kernels.")
    args = p.parse_args()

    configure_reproducibility(seed=int(args.seed), threads=int(args.threads), matplotlib_backend="Agg")

    from exact.fig5 import plot_benign_sparse_causal_network_two_panel

    plot_benign_sparse_causal_network_two_panel(
        edges_csv_A=args.edges_a,
        edges_csv_B=args.edges_b,
        out_png=args.out,
        title_A=args.title_a,
        title_B=args.title_b,
        seed=int(args.seed),
    )


if __name__ == "__main__":
    main()
