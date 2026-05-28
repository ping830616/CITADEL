#!/usr/bin/env python3
"""Build rtl_resource_summary.csv from Vivado report folders.

The script uses only Python's standard library so it can run on the ASU server
without extra packages.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


DEFAULT_CONFIGS = {
    "A_DROOP": {"setup": "A", "scenario": "DROOP", "top_k": 15, "fixed_point_q": 15, "window_size": 1000},
    "A_RH": {"setup": "A", "scenario": "RH", "top_k": 20, "fixed_point_q": 8, "window_size": 550},
    "B_DROOP": {"setup": "B", "scenario": "DROOP", "top_k": 15, "fixed_point_q": 15, "window_size": 200},
    "B_SPECTRE": {"setup": "B", "scenario": "SPECTRE", "top_k": 30, "fixed_point_q": 8, "window_size": 700},
}


def read_text(path: Path) -> str:
    return path.read_text(errors="ignore") if path.exists() else ""


def table_used(text: str, label: str) -> int | float | None:
    match = re.search(rf"\|\s*{re.escape(label)}\*?\s*\|\s*([0-9.]+)\s*\|", text)
    if not match:
        return None
    value = match.group(1)
    return float(value) if "." in value else int(value)


def util_pct(text: str, label: str) -> float | None:
    match = re.search(
        rf"\|\s*{re.escape(label)}\*?\s*\|\s*[0-9.]+\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*([0-9.]+)\s*\|",
        text,
    )
    return float(match.group(1)) if match else None


def first_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return float(match.group(1)) if match else None


def run_config(folder: Path) -> dict[str, str]:
    path = folder / "run_config.csv"
    if not path.exists():
        return {}
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows[0] if rows else {}


def infer_config(tag: str, folder: Path) -> dict[str, object]:
    cfg = dict(DEFAULT_CONFIGS.get(tag, {}))
    rcfg = run_config(folder)
    if rcfg:
        cfg.setdefault("setup", tag.split("_", 1)[0])
        cfg.setdefault("scenario", tag.split("_", 1)[1] if "_" in tag else tag)
        cfg["top_k"] = int(rcfg.get("features", cfg.get("top_k", 0)))
        cfg["fixed_point_q"] = int(rcfg.get("q", cfg.get("fixed_point_q", 0)))
        cfg["window_size"] = int(rcfg.get("samples_per_block", cfg.get("window_size", 0)))
    return cfg


def parse_folder(folder: Path) -> dict[str, object]:
    tag = folder.name
    cfg = infer_config(tag, folder)
    util = read_text(folder / "utilization.rpt")
    timing = read_text(folder / "timing_summary.rpt")
    power = read_text(folder / "power.rpt")
    log = read_text(folder / "vivado.log")
    rcfg = run_config(folder)

    device = rcfg.get("part", "unknown")
    match = re.search(r"\| Device\s*:\s*([^\n]+)", util)
    if match:
        device = match.group(1).strip()

    tool_version = "unknown"
    match = re.search(r"\| Tool Version\s*:\s*([^\n]+)", util)
    if match:
        tool_version = match.group(1).strip()

    wns = first_float(r"Worst Slack\s+(-?[0-9.]+)ns", timing)
    clock_period = first_float(r"Requirement:\s*([0-9.]+)ns", timing)
    if clock_period is None:
        clock_period = float(rcfg.get("clock_period_ns", 0.0) or 0.0)
    timing_met = (
        wns >= 0.0
        if wns is not None
        else "Timing constraints are met" in timing and "Timing constraints are not met" not in timing
    )

    fmax_mhz = None
    if clock_period and wns is not None and clock_period - wns > 0:
        fmax_mhz = round(1000.0 / (clock_period - wns), 2)

    total_power_w = first_float(r"\|\s*Total On-Chip Power \(W\)\s*\|\s*([0-9.]+)\s*\|", power)
    dynamic_power_w = first_float(r"\|\s*Dynamic \(W\)\s*\|\s*([0-9.]+)\s*\|", power)
    static_power_w = first_float(r"\|\s*Device Static \(W\)\s*\|\s*([0-9.]+)\s*\|", power)
    confidence = ""
    match = re.search(r"\|\s*Confidence Level\s*\|\s*([^|]+)\|", power)
    if match:
        confidence = match.group(1).strip()

    synth_ok = "synth_design completed successfully" in log
    power_ok = "report_power completed successfully" in log
    top_k = int(cfg.get("top_k", 0) or 0)
    window_size = int(cfg.get("window_size", 0) or 0)

    return {
        "setup": cfg.get("setup", ""),
        "scenario": cfg.get("scenario", tag),
        "top_k": top_k,
        "fixed_point_q": cfg.get("fixed_point_q", ""),
        "window_size": window_size,
        "tag": tag,
        "target_part": device,
        "tool_version": tool_version,
        "luts": table_used(util, "Slice LUTs"),
        "luts_pct": util_pct(util, "Slice LUTs"),
        "ffs": table_used(util, "Slice Registers"),
        "ffs_pct": util_pct(util, "Slice Registers"),
        "dsps": table_used(util, "DSPs"),
        "dsp_pct": util_pct(util, "DSPs"),
        "brams": table_used(util, "Block RAM Tile"),
        "bram_pct": util_pct(util, "Block RAM Tile"),
        "iobs": table_used(util, "Bonded IOB"),
        "iob_pct": util_pct(util, "Bonded IOB"),
        "clock_period_ns": clock_period,
        "wns_ns": wns,
        "timing_met": timing_met,
        "fmax_mhz_est": fmax_mhz,
        "total_power_mw": round(total_power_w * 1000, 3) if total_power_w is not None else "",
        "dynamic_power_mw": round(dynamic_power_w * 1000, 3) if dynamic_power_w is not None else "",
        "static_power_mw": round(static_power_w * 1000, 3) if static_power_w is not None else "",
        "power_confidence": confidence,
        "synth_ok": synth_ok,
        "power_ok": power_ok,
        "latency_cycles": top_k * window_size if top_k and window_size else "",
        "status": "synthesized" if synth_ok else "check_log",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("results/notebook_run/rtl_sweep"))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    folders = [
        item
        for item in sorted(args.root.iterdir())
        if item.is_dir() and (item / "utilization.rpt").exists()
    ]
    rows = [parse_folder(folder) for folder in folders]
    if not rows:
        raise SystemExit(f"No Vivado report folders found under {args.root}")

    output = args.output or args.root / "rtl_resource_summary.csv"
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {output}")
    for row in rows:
        print(
            f"{row['tag']}: LUT={row['luts']} FF={row['ffs']} DSP={row['dsps']} "
            f"BRAM={row['brams']} WNS={row['wns_ns']}ns Power={row['total_power_mw']}mW "
            f"TimingMet={row['timing_met']}"
        )


if __name__ == "__main__":
    main()
