#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DatasetGroup:
    name: str
    glob_pattern: str


BASE_GROUPS: List[DatasetGroup] = [
    DatasetGroup("tier0_full", "tier0/*/tier0_full_5hz.csv"),
    DatasetGroup("tier2_core", "tier2/*/tier2_core_5hz.csv"),
    DatasetGroup("tier2_full", "tier2/*/tier2_full_5hz.csv"),
]

TIER1_GROUPS: List[DatasetGroup] = [
    DatasetGroup("tier1_core", "tier1/*/tier1_core_5hz.csv"),
    DatasetGroup("tier1_full", "tier1/*/tier1_full_5hz.csv"),
]

TIER1_ALT_GROUPS: List[DatasetGroup] = [
    DatasetGroup("tier1_alt_core", "tier1_alt/*/tier1_alt_core_5hz.csv"),
    DatasetGroup("tier1_alt_full", "tier1_alt/*/tier1_alt_full_5hz.csv"),
]


def build_groups(tier1_mode: str) -> List[DatasetGroup]:
    groups = list(BASE_GROUPS)
    if tier1_mode in ("powermetrics", "both"):
        groups.extend(TIER1_GROUPS)
    if tier1_mode in ("alt", "both"):
        groups.extend(TIER1_ALT_GROUPS)
    return groups


def _coverage_for_group(files: List[Path]) -> Tuple[Dict[str, float], Dict[str, int], Dict[str, int]]:
    non_nan: Dict[str, int] = {}
    total: Dict[str, int] = {}
    present: Dict[str, int] = {}

    for fp in files:
        df = pd.read_csv(fp)
        for c in df.columns:
            present[c] = present.get(c, 0) + 1
            nn = int(df[c].notna().sum())
            non_nan[c] = non_nan.get(c, 0) + nn
            total[c] = total.get(c, 0) + len(df)

    coverage = {c: (non_nan[c] / total[c]) if total[c] else 0.0 for c in total}
    return coverage, present, total


def _keep_columns(
    coverage: Dict[str, float],
    min_coverage_ratio: float,
    always_keep: List[str],
    keep_all_nan_columns: bool,
) -> Tuple[List[str], List[str], List[str]]:
    keep: List[str] = []
    drop_all_nan: List[str] = []
    drop_low_coverage: List[str] = []

    for c, cov in sorted(coverage.items()):
        if c in always_keep:
            keep.append(c)
            continue
        if cov == 0.0 and not keep_all_nan_columns:
            drop_all_nan.append(c)
            continue
        if cov < min_coverage_ratio:
            drop_low_coverage.append(c)
            continue
        keep.append(c)

    # Keep stable ordering with idx first if present.
    if "idx" in keep:
        keep = ["idx"] + [c for c in keep if c != "idx"]
    return keep, drop_all_nan, drop_low_coverage


def _compute_fill_values(
    files: List[Path],
    keep_cols: List[str],
    fill_strategy: str,
    idx_col: str = "idx",
) -> Dict[str, float]:
    feat_cols = [c for c in keep_cols if c != idx_col]
    if fill_strategy == "zero":
        return {c: 0.0 for c in feat_cols}

    values: Dict[str, List[float]] = {c: [] for c in feat_cols}
    for fp in files:
        df = pd.read_csv(fp)
        for c in feat_cols:
            if c not in df.columns:
                continue
            s = pd.to_numeric(df[c], errors="coerce").dropna()
            if not s.empty:
                values[c].extend(s.tolist())

    fill_values: Dict[str, float] = {}
    for c in feat_cols:
        if values[c]:
            fill_values[c] = float(pd.Series(values[c]).median())
        else:
            fill_values[c] = 0.0
    return fill_values


def _impute_numeric(
    df: pd.DataFrame,
    keep_cols: List[str],
    fill_values: Dict[str, float],
    idx_col: str = "idx",
) -> pd.DataFrame:
    out = df.copy()
    for c in keep_cols:
        if c == idx_col:
            continue
        out[c] = pd.to_numeric(out[c], errors="coerce")

    feat_cols = [c for c in keep_cols if c != idx_col]
    if feat_cols:
        # Fill temporal gaps with local context first.
        out[feat_cols] = out[feat_cols].ffill().bfill()
        # Then fill residual NaNs using group-level fallback values.
        for c in feat_cols:
            fallback = fill_values.get(c, 0.0)
            out[c] = out[c].fillna(fallback)
        # Final safeguard.
        out[feat_cols] = out[feat_cols].fillna(0.0)

    return out[keep_cols]


def _write_group(
    files: List[Path],
    in_root: Path,
    out_root: Path,
    keep_cols: List[str],
    fill_values: Dict[str, float],
) -> Dict[str, float]:
    before_nan_cells = 0
    before_total_cells = 0
    after_nan_cells = 0
    after_total_cells = 0

    for fp in files:
        rel = fp.relative_to(in_root)
        out_fp = out_root / rel
        out_fp.parent.mkdir(parents=True, exist_ok=True)

        df = pd.read_csv(fp)
        if "idx" in keep_cols and "idx" not in df.columns:
            df = df.reset_index(names="idx")
        # Force stable schema across all files in a group.
        for c in keep_cols:
            if c not in df.columns:
                df[c] = pd.NA

        before = df[keep_cols]
        before_nan_cells += int(before.isna().sum().sum())
        before_total_cells += int(before.shape[0] * before.shape[1])

        cleaned = _impute_numeric(df, keep_cols, fill_values=fill_values)
        after_nan_cells += int(cleaned.isna().sum().sum())
        after_total_cells += int(cleaned.shape[0] * cleaned.shape[1])

        cleaned.to_csv(out_fp, index=False)

    before_frac = (before_nan_cells / before_total_cells) if before_total_cells else 0.0
    after_frac = (after_nan_cells / after_total_cells) if after_total_cells else 0.0
    return {
        "before_nan_fraction": before_frac,
        "after_nan_fraction": after_frac,
    }


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Create a NaN-free, model-ready copy of Tier-0/1_alt/2 CSVs. "
            "Unsupported columns are dropped globally by coverage threshold."
        )
    )
    ap.add_argument("--root", type=Path, default=REPO_ROOT / "data", help="Input dataset root.")
    ap.add_argument(
        "--out_dir",
        "--out-dir",
        dest="out_dir",
        type=Path,
        default=None,
        help="Output root for cleaned dataset. Default: <root>_clean_no_nan",
    )
    ap.add_argument(
        "--min_coverage_ratio",
        "--min-coverage-ratio",
        dest="min_coverage_ratio",
        type=float,
        default=0.95,
        help=(
            "Drop columns whose global non-NaN ratio is below this threshold "
            "(except idx). Use 0.0 to keep sparse columns."
        ),
    )
    ap.add_argument(
        "--audit_only",
        "--audit-only",
        dest="audit_only",
        action="store_true",
        help="Only produce availability report, do not write cleaned CSVs.",
    )
    ap.add_argument(
        "--tier1_mode",
        "--tier1-mode",
        dest="tier1_mode",
        choices=["powermetrics", "alt", "both"],
        default="both",
        help="Which Tier-1 source groups to include in cleaning.",
    )
    ap.add_argument(
        "--keep_all_nan_columns",
        "--keep-all-nan-columns",
        dest="keep_all_nan_columns",
        action="store_true",
        help="Keep even globally all-NaN columns, then impute them (0.0 fallback).",
    )
    ap.add_argument(
        "--fallback_fill",
        "--fallback-fill",
        dest="fallback_fill",
        choices=["global_median", "zero"],
        default="global_median",
        help="Fallback imputation used after local forward/backward fill.",
    )
    args = ap.parse_args()

    in_root = Path(args.root)
    out_root = Path(args.out_dir) if args.out_dir else in_root.parent / f"{in_root.name}_clean_no_nan"
    report = {
        "input_root": str(in_root),
        "output_root": str(out_root),
        "min_coverage_ratio": args.min_coverage_ratio,
        "audit_only": args.audit_only,
        "tier1_mode": args.tier1_mode,
        "keep_all_nan_columns": args.keep_all_nan_columns,
        "fallback_fill": args.fallback_fill,
        "groups": {},
    }

    for g in build_groups(args.tier1_mode):
        files = sorted(in_root.glob(g.glob_pattern))
        if not files:
            report["groups"][g.name] = {
                "files": 0,
                "note": "No files found for this group.",
            }
            continue

        coverage, present, _ = _coverage_for_group(files)
        keep_cols, drop_all_nan, drop_low_cov = _keep_columns(
            coverage=coverage,
            min_coverage_ratio=args.min_coverage_ratio,
            always_keep=["idx"],
            keep_all_nan_columns=args.keep_all_nan_columns,
        )
        fill_values = _compute_fill_values(
            files=files,
            keep_cols=keep_cols,
            fill_strategy=args.fallback_fill,
        )

        grp_report = {
            "files": len(files),
            "columns_present": sorted(coverage.keys()),
            "kept_columns": keep_cols,
            "dropped_all_nan_columns": drop_all_nan,
            "dropped_low_coverage_columns": drop_low_cov,
            "coverage_ratio_by_column": {k: round(v, 6) for k, v in sorted(coverage.items())},
            "present_file_count_by_column": present,
            "imputation_fill_value_by_column": {k: round(v, 6) for k, v in sorted(fill_values.items())},
        }

        if not args.audit_only:
            nan_stats = _write_group(
                files=files,
                in_root=in_root,
                out_root=out_root,
                keep_cols=keep_cols,
                fill_values=fill_values,
            )
            grp_report.update(nan_stats)

        report["groups"][g.name] = grp_report

    out_report_root = out_root if not args.audit_only else in_root
    out_report_root.mkdir(parents=True, exist_ok=True)
    report_path = out_report_root / "no_nan_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    print("NaN handling report written:", report_path)
    for g, info in report["groups"].items():
        if info.get("files", 0) == 0:
            print(f"[{g}] files=0")
            continue
        dropped = len(info["dropped_all_nan_columns"]) + len(info["dropped_low_coverage_columns"])
        msg = f"[{g}] files={info['files']} keep={len(info['kept_columns'])} dropped={dropped}"
        if not args.audit_only:
            msg += f" | before_nan={info['before_nan_fraction']:.6f} after_nan={info['after_nan_fraction']:.6f}"
        print(msg)


if __name__ == "__main__":
    main()
