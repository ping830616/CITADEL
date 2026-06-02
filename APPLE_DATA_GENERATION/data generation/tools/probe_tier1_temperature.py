#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

_NUM_RE = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*([A-Za-z%/]+)?")


def norm_key(k: str) -> str:
    k = k.strip().lower()
    k = re.sub(r"\(.*?\)", "", k)
    k = re.sub(r"[^a-z0-9]+", "_", k)
    return k.strip("_")


def parse_numeric_kv(lines):
    kv = {}
    for line in lines:
        line = line.strip()
        if ":" in line:
            k, v = line.split(":", 1)
        elif "=" in line:
            k, v = line.split("=", 1)
        else:
            continue

        nk = norm_key(k)
        m = _NUM_RE.search(v)
        if not m:
            continue
        val = float(m.group(1))
        kv.setdefault(nk, []).append(val)
    return kv


def main():
    ap = argparse.ArgumentParser(description="Probe Tier-1 temperature support via powermetrics.")
    ap.add_argument("--interval_ms", "--interval-ms", dest="interval_ms", type=int, default=1000)
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--out_raw", "--out-raw", dest="out_raw", type=Path)
    args = ap.parse_args()

    cmd = [
        "sudo",
        "powermetrics",
        "-i",
        str(args.interval_ms),
        "-n",
        str(args.samples),
        "-s",
        "cpu_power,gpu_power,thermal",
        "--show-extra-power-info",
    ]

    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        print("Probe failed.")
        print((p.stderr or p.stdout).strip())
        raise SystemExit(p.returncode)

    text = p.stdout
    if args.out_raw:
        args.out_raw.parent.mkdir(parents=True, exist_ok=True)
        args.out_raw.write_text(text)
        print(f"Wrote raw probe output: {args.out_raw}")

    lines = text.splitlines()
    temp_lines = [ln for ln in lines if re.search(r"temp|temperature", ln, re.IGNORECASE)]
    pressure_lines = [ln for ln in lines if re.search(r"current pressure level", ln, re.IGNORECASE)]
    kv = parse_numeric_kv(lines)

    temp_keys = sorted([k for k in kv if ("temp" in k or "temperature" in k)])

    print("Temperature probe summary")
    print("- sample lines with temp/temperature:", len(temp_lines))
    print("- pressure-level lines:", len(pressure_lines))
    print("- numeric temperature-like keys:", temp_keys)

    if temp_keys:
        for k in temp_keys:
            vals = kv[k]
            vmin = min(vals)
            vmax = max(vals)
            print(f"  - {k}: n={len(vals)} min={vmin:.2f} max={vmax:.2f}")
        print("Result: numeric temperature appears available for Tier-1 extension.")
    else:
        print("Result: no numeric temperature sensor fields detected from powermetrics on this host.")
        print("Tier-1 can still provide thermal pressure state (Nominal/Fair/Serious/Critical).")


if __name__ == "__main__":
    main()
