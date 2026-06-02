from pathlib import Path
import argparse
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=REPO_ROOT / "data")
    ap.add_argument("--out_dir", "--out-dir", dest="out_dir", type=Path)
    args = ap.parse_args()

    tier1_dir = args.root / "tier1"
    out_dir = args.out_dir if args.out_dir else (args.root / "tier1_core_cleaned")
    out_dir.mkdir(parents=True, exist_ok=True)

    core_files = sorted(tier1_dir.glob("*/tier1_core_5hz.csv"))
    if not core_files:
        raise SystemExit(f"No tier1_core_5hz.csv files found under: {tier1_dir}")

    # 1) Find columns that are all-NaN across ALL runs
    #    (this is the strictest and most reproducible rule)
    allnan_cols_global = None
    cols_union = None

    for f in core_files:
        df = pd.read_csv(f)
        cols = df.columns
        cols_union = set(cols) if cols_union is None else (cols_union | set(cols))

        allnan_cols_run = set(df.columns[df.isna().all()].tolist())
        allnan_cols_global = allnan_cols_run if allnan_cols_global is None else (allnan_cols_global & allnan_cols_run)

    allnan_cols_global = sorted(allnan_cols_global) if allnan_cols_global else []
    keep_cols = sorted(list(set(cols_union) - set(allnan_cols_global)))

    # Always keep idx even if it could be non-NaN anyway
    if "idx" not in keep_cols and any("idx" in pd.read_csv(core_files[0]).columns for _ in [0]):
        keep_cols = ["idx"] + [c for c in keep_cols if c != "idx"]

    # 2) Save cleaned per-run CSVs
    written = 0
    for f in core_files:
        case_id = f.parent.name
        df = pd.read_csv(f)
        # keep only columns present in this file
        cols = [c for c in keep_cols if c in df.columns]
        df_clean = df[cols].copy()

        out_case = out_dir / case_id
        out_case.mkdir(parents=True, exist_ok=True)
        out_path = out_case / "tier1_core_5hz_clean.csv"
        df_clean.to_csv(out_path, index=False)
        written += 1

    # 3) Write a report
    report = {
        "n_runs": len(core_files),
        "dropped_all_nan_columns_global": allnan_cols_global,
        "kept_columns_global": keep_cols,
        "output_dir": str(out_dir),
    }
    (out_dir / "clean_report.json").write_text(pd.Series(report).to_json())

    # Human-readable printout
    print("Tier-1 CORE cleaning complete ✅")
    print("Runs processed:", len(core_files))
    print("Dropped all-NaN columns (global):", allnan_cols_global)
    print("Kept columns (global):", keep_cols)
    print("Cleaned CSVs saved under:", out_dir)

if __name__ == "__main__":
    main()
