#!/usr/bin/env python3
"""Render paper Figure 5 from a parsed CITADEL RTL summary."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle
from PIL import Image, ImageStat


PAPER_ORDER = ("A_DROOP", "A_RH", "B_DROOP", "B_SPECTRE")


def _as_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "pass", "met"}
    return bool(value)


def _percent(value: object) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def validate_summary(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "tag", "setup", "scenario", "clock_period_ns", "wns_ns", "timing_met",
        "luts_pct", "ffs_pct", "dsp_pct", "iob_pct", "brams",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"RTL summary is missing Figure 5 columns: {missing}")
    if set(frame["tag"]) != set(PAPER_ORDER) or len(frame) != len(PAPER_ORDER):
        raise ValueError("Figure 5 requires exactly the four paper RTL cases")
    ordered = frame.copy()
    ordered["_order"] = ordered["tag"].map({tag: index for index, tag in enumerate(PAPER_ORDER)})
    ordered = ordered.sort_values("_order").reset_index(drop=True)
    ordered["case"] = ordered["setup"].astype(str) + "/" + ordered["scenario"].astype(str).str.upper()
    return ordered


def render_figure5(summary_path: Path, output_path: Path) -> dict[str, object]:
    """Render and decode-check the timing/resource composition used in the paper."""

    rtl = validate_summary(pd.read_csv(summary_path))
    colors = {
        "text": "#0F172A", "muted": "#334155", "grid": "#CBD5E1",
        "pass": "#0B7A28", "pass_bg": "#D7FBE3",
        "logic": "#0057B8", "logic_bg": "#D9EAFF",
        "reg": "#334155", "reg_bg": "#E2E8F0",
        "dsp": "#6D28D9", "dsp_bg": "#EDE2FF",
        "io": "#008C89", "io_bg": "#D7FFFB",
        "power": "#D97706", "power_bg": "#FFE8BF",
        "warn": "#C2410C", "warn_bg": "#FFEDD5",
        "fail": "#B91C1C", "fail_bg": "#FEE2E2",
        "A": "#0057B8", "B": "#E05A00",
    }
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.titleweight": "bold"})
    figure = plt.figure(figsize=(8.35, 8.35), dpi=240)
    grid = figure.add_gridspec(2, 1, height_ratios=[0.72, 2.72], hspace=0.64)
    timing = figure.add_subplot(grid[0])
    matrix = figure.add_subplot(grid[1])

    y_positions = np.arange(len(rtl))[::-1]
    case_colors = [colors[str(setup)] for setup in rtl["setup"]]
    timing.axvline(0, color=colors["fail"], linestyle="--", linewidth=1.8, zorder=1)
    timing.barh(
        y_positions,
        rtl["wns_ns"],
        height=0.44,
        color=case_colors,
        edgecolor="#111827",
        linewidth=0.85,
        zorder=3,
    )
    for y, row, color in zip(y_positions, rtl.itertuples(index=False), case_colors):
        timing.scatter(
            row.wns_ns, y, s=98, color="white", edgecolors=color, linewidths=2.4, zorder=4
        )
        timing.text(
            row.wns_ns + 0.06,
            y,
            f"+{row.wns_ns:.2f}",
            ha="left",
            va="center",
            fontsize=10.2,
            fontweight="bold",
            color=colors["pass"],
        )
    timing.set_yticks(y_positions)
    timing.set_yticklabels(rtl["case"], fontsize=10.8, fontweight="bold", color=colors["text"])
    timing.set_xlim(-0.25, max(3.0, float(rtl["wns_ns"].max()) + 0.60))
    timing.set_title("Timing Slack at 25 ns Clock Target", fontsize=13.6, pad=8)
    timing.set_xlabel("Slack (ns)", fontsize=10.3, labelpad=3)
    timing.grid(axis="x", color=colors["grid"], linewidth=0.85, alpha=0.82, zorder=0)
    timing.tick_params(axis="x", labelsize=9.7, colors=colors["muted"])
    for spine in ("top", "right", "left"):
        timing.spines[spine].set_visible(False)
    timing.spines["bottom"].set_color(colors["grid"])
    timing.text(
        0.012, -0.28, "0 ns timing limit", transform=timing.transAxes,
        ha="left", va="center", fontsize=9.9, fontweight="bold", color=colors["fail"],
    )

    criteria = (
        ("Post-synthesis timing", "timing"),
        ("Logic footprint", "luts_pct"),
        ("Register footprint", "ffs_pct"),
        ("DSP footprint", "dsp_pct"),
        ("I/O ports", "iob_pct"),
        ("BRAM use", "brams"),
        ("Power evidence", "power"),
    )
    matrix.set_xlim(0, len(rtl))
    matrix.set_ylim(0, len(criteria))
    matrix.invert_yaxis()
    matrix.set_xticks(np.arange(len(rtl)) + 0.5)
    matrix.set_xticklabels(rtl["case"], fontsize=11.8, fontweight="bold")
    matrix.tick_params(top=True, labeltop=True, bottom=False, labelbottom=False, length=0, pad=10)
    matrix.set_yticks(np.arange(len(criteria)) + 0.5)
    matrix.set_yticklabels([label for label, _ in criteria], fontsize=11.4, fontweight="bold")
    matrix.set_title("Post-Synthesis Resource Summary", fontsize=14.6, pad=32)

    for row_index, (_, kind) in enumerate(criteria):
        for column_index, row in enumerate(rtl.itertuples(index=False)):
            status, detail = "Positive WNS", ""
            color, background = colors["pass"], colors["pass_bg"]
            bar_color: str | None = None
            fraction: float | None = None
            if kind == "timing":
                met = _as_bool(row.timing_met)
                status = "Positive WNS" if met else "CHECK"
                detail = f"WNS {float(row.wns_ns):+.2f} ns"
                color, background = (
                    (colors["pass"], colors["pass_bg"])
                    if met else (colors["fail"], colors["fail_bg"])
                )
            elif kind == "luts_pct":
                status, detail = "LOW", f"{_percent(row.luts_pct)} LUT"
                color, background, bar_color = colors["logic"], colors["logic_bg"], colors["logic"]
                fraction = min(float(row.luts_pct) / 10.0, 1.0)
            elif kind == "ffs_pct":
                status, detail = "LOW", f"{_percent(row.ffs_pct)} FF"
                color, background, bar_color = colors["reg"], colors["reg_bg"], colors["reg"]
                fraction = min(float(row.ffs_pct) / 10.0, 1.0)
            elif kind == "dsp_pct":
                status, detail = "BOUNDED", f"{_percent(row.dsp_pct)} DSP"
                color, background, bar_color = colors["dsp"], colors["dsp_bg"], colors["dsp"]
                fraction = min(float(row.dsp_pct) / 10.0, 1.0)
            elif kind == "iob_pct":
                tight = float(row.iob_pct) >= 90.0
                status, detail = ("TIGHT" if tight else "WITHIN"), f"{_percent(row.iob_pct)} I/O"
                color, background = (
                    (colors["warn"], colors["warn_bg"])
                    if tight else (colors["io"], colors["io_bg"])
                )
                bar_color = color
                fraction = min(float(row.iob_pct) / 100.0, 1.0)
            elif kind == "brams":
                status, detail = "NONE", f"{int(row.brams)} BRAM"
            elif kind == "power":
                status, detail = "VECTORLESS", "estimate"
                color, background = colors["power"], colors["power_bg"]

            matrix.add_patch(
                FancyBboxPatch(
                    (column_index + 0.035, row_index + 0.055), 0.93, 0.89,
                    boxstyle="round,pad=0.012,rounding_size=0.035",
                    facecolor=background, edgecolor=color, linewidth=1.55, zorder=2,
                )
            )
            matrix.text(
                column_index + 0.5, row_index + 0.30, status,
                ha="center", va="center", fontsize=10.7, fontweight="bold", color=color, zorder=3,
            )
            matrix.text(
                column_index + 0.5, row_index + 0.55, detail,
                ha="center", va="center", fontsize=9.6, fontweight="bold", color=colors["text"], zorder=3,
            )
            if fraction is not None and bar_color is not None:
                matrix.add_patch(
                    Rectangle(
                        (column_index + 0.12, row_index + 0.725), 0.76, 0.125,
                        facecolor="white", edgecolor="#94A3B8", linewidth=0.75, zorder=3,
                    )
                )
                matrix.add_patch(
                    Rectangle(
                        (column_index + 0.12, row_index + 0.725), 0.76 * fraction, 0.125,
                        facecolor=bar_color, edgecolor="none", zorder=4,
                    )
                )

    for spine in matrix.spines.values():
        spine.set_visible(False)
    for x in range(len(rtl) + 1):
        matrix.axvline(x, color="#D1D5DB", linewidth=1.05, zorder=0)
    for y in range(len(criteria) + 1):
        matrix.axhline(y, color="#D1D5DB", linewidth=1.05, zorder=0)

    legend = [
        Patch(facecolor=colors["pass_bg"], edgecolor=colors["pass"], label="Positive WNS / no BRAM"),
        Patch(facecolor=colors["logic_bg"], edgecolor=colors["logic"], label="Logic LUTs"),
        Patch(facecolor=colors["reg_bg"], edgecolor=colors["reg"], label="Registers FFs"),
        Patch(facecolor=colors["dsp_bg"], edgecolor=colors["dsp"], label="DSP use"),
        Patch(facecolor=colors["io_bg"], edgecolor=colors["io"], label="I/O ports"),
        Patch(facecolor=colors["power_bg"], edgecolor=colors["power"], label="Power estimate"),
    ]
    figure.legend(handles=legend, loc="lower center", ncol=3, frameon=False, fontsize=9.8,
                  bbox_to_anchor=(0.5, 0.012), columnspacing=1.35, handlelength=1.55)
    figure.subplots_adjust(left=0.235, right=0.985, top=0.94, bottom=0.108)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(figure)

    with Image.open(output_path) as opened:
        if opened.format != "PNG":
            raise RuntimeError("Rendered Figure 5 is not PNG")
        opened.verify()
    with Image.open(output_path) as opened:
        width, height = opened.size
        sample = opened.convert("L")
        sample.thumbnail((256, 256))
        variance = float(ImageStat.Stat(sample).var[0])
    if width < 1000 or height < 900 or variance <= 1.0:
        raise RuntimeError("Rendered Figure 5 failed raster validation")
    return {
        "width_px": int(width),
        "height_px": int(height),
        "decoded_png": True,
        "nonuniform": True,
        "composition": "timing_slack_panel_plus_four_case_resource_summary",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    facts = render_figure5(args.summary.resolve(), args.output.resolve())
    print(f"Wrote {args.output.resolve()} ({facts['width_px']}x{facts['height_px']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
