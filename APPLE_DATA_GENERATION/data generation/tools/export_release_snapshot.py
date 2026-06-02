#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def export_group(root: Path, out_root: Path, rel_glob: str) -> int:
    copied = 0
    for src in sorted(root.glob(rel_glob)):
        rel = src.relative_to(root)
        if copy_if_exists(src, out_root / rel):
            copied += 1
    return copied


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Export a stripped processed dataset snapshot that matches the public "
            "ITC_M2Pro_DATA-style layout."
        )
    )
    ap.add_argument("--root", type=Path, required=True, help="Input full collection root.")
    ap.add_argument("--out_dir", "--out-dir", dest="out_dir", type=Path, required=True, help="Output snapshot root.")
    ap.add_argument(
        "--tier1_mode",
        "--tier1-mode",
        dest="tier1_mode",
        choices=["powermetrics", "alt", "both"],
        default="alt",
        help="Which Tier-1 processed CSVs to export.",
    )
    ap.add_argument(
        "--skip_report",
        "--skip-report",
        dest="skip_report",
        action="store_true",
        help="Skip generation of no_nan_report.json for the exported snapshot.",
    )
    args = ap.parse_args()

    root = Path(args.root)
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    copied = {
        "tier0": export_group(root, out_root, "tier0/*/tier0_full_5hz.csv"),
        "tier2_core": export_group(root, out_root, "tier2/*/tier2_core_5hz.csv"),
        "tier2_full": export_group(root, out_root, "tier2/*/tier2_full_5hz.csv"),
    }
    if args.tier1_mode in ("powermetrics", "both"):
        copied["tier1_core"] = export_group(root, out_root, "tier1/*/tier1_core_5hz.csv")
        copied["tier1_full"] = export_group(root, out_root, "tier1/*/tier1_full_5hz.csv")
    if args.tier1_mode in ("alt", "both"):
        copied["tier1_alt_core"] = export_group(root, out_root, "tier1_alt/*/tier1_alt_core_5hz.csv")
        copied["tier1_alt_full"] = export_group(root, out_root, "tier1_alt/*/tier1_alt_full_5hz.csv")

    if not args.skip_report:
        report_cmd = [
            sys.executable,
            str(REPO_ROOT / "tools" / "ensure_no_nan_dataset.py"),
            "--root",
            str(out_root),
            "--tier1_mode",
            args.tier1_mode,
            "--audit_only",
        ]
        subprocess.run(report_cmd, check=True)

    print("Exported processed snapshot:", out_root)
    for key, value in copied.items():
        print(f" - {key}: {value}")


if __name__ == "__main__":
    main()
