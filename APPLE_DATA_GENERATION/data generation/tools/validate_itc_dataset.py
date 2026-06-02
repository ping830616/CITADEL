from pathlib import Path
import argparse
import csv
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from dice.cfg import all_cases


def count_lines(p: Path) -> int:
    with p.open("rb") as f:
        return sum(1 for _ in f)


def read_csv_first_pass_non_nan(path: Path, cols):
    """
    Return dict col->(non_nan_count, total_rows).
    Avoid pandas dependency.
    """
    counts = {c: 0 for c in cols}
    total = 0
    with path.open("r", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            total += 1
            for c in cols:
                v = row.get(c, "")
                if v is None:
                    continue
                v = v.strip()
                if v == "" or v.lower() == "nan":
                    continue
                counts[c] += 1
    return counts, total


def read_csv_header(path: Path):
    with path.open("r", newline="") as f:
        r = csv.reader(f)
        return next(r, [])


def pick_tier2_key_cols(path: Path):
    """
    Support both legacy and current Tier-2 core schemas.
    """
    header = read_csv_header(path)
    header_set = set(header)

    candidate_sets = [
        ["cpu_usage_pct", "cpu_time_ms", "thread_count"],  # legacy core schema
        ["samples_per_bucket", "unique_process_count", "unique_thread_count"],  # current core schema
    ]

    best = []
    best_score = -1
    for cols in candidate_sets:
        present = [c for c in cols if c in header_set]
        if len(present) > best_score:
            best = present
            best_score = len(present)

    if best:
        return best

    # Fallback for future schema changes: require any non-idx numeric-like columns
    return [c for c in header if c != "idx"][:3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=REPO_ROOT / "data")
    ap.add_argument("--expected_cases", "--expected-cases", dest="expected_cases", type=int, default=len(all_cases()))
    ap.add_argument("--expected_lines", "--expected-lines", dest="expected_lines", type=int, default=5001)
    ap.add_argument(
        "--tier1_mode",
        "--tier1-mode",
        dest="tier1_mode",
        choices=["powermetrics", "alt", "both"],
        default="powermetrics",
        help="Which Tier-1 source to require: legacy powermetrics, tier1_alt, or both.",
    )
    ap.add_argument("--check_tier1_alt", "--check-tier1-alt", dest="check_tier1_alt", action="store_true")
    ap.add_argument("--check_tier2", "--check-tier2", dest="check_tier2", action="store_true")
    ap.add_argument(
        "--processed_only",
        "--processed-only",
        dest="processed_only",
        action="store_true",
        help="Validate a processed public snapshot that does not include schemas, manifests, or raw artifacts.",
    )
    args = ap.parse_args()

    check_tier1 = args.tier1_mode in ("powermetrics", "both")
    check_tier1_alt = (args.tier1_mode in ("alt", "both")) or args.check_tier1_alt

    root = Path(args.root)
    t0 = root / "tier0"
    t1 = root / "tier1"
    t1a = root / "tier1_alt"
    t2 = root / "tier2"
    problems = []

    if not args.processed_only:
        # --- Schema files ---
        t0_schema = root / "tier0_schema_global.json"
        t1_schema = root / "tier1_schema_global.json"
        if not t0_schema.exists():
            problems.append(f"Missing Tier-0 schema: {t0_schema}")
        if check_tier1 and not t1_schema.exists():
            problems.append(f"Missing Tier-1 schema: {t1_schema}")
        if check_tier1_alt:
            t1a_schema = root / "tier1_alt_schema_global.json"
            if not t1a_schema.exists():
                problems.append(f"Missing Tier-1-alt schema: {t1a_schema}")
        if args.check_tier2:
            t2_schema = root / "tier2_schema_global.json"
            if not t2_schema.exists():
                problems.append(f"Missing Tier-2 schema: {t2_schema}")

        # --- Manifests ---
        m0 = root / "manifest_tier0.csv"
        m1 = root / "manifest_tier1.csv"
        m1a = root / "manifest_tier1_alt.csv"
        m2 = root / "manifest_tier2.csv"
        if m0.exists():
            n = count_lines(m0)
            if n != args.expected_cases + 1:
                problems.append(f"manifest_tier0.csv lines={n} (expected {args.expected_cases+1})")
        else:
            problems.append(f"Missing {m0}")
        if check_tier1:
            if m1.exists():
                n = count_lines(m1)
                if n != args.expected_cases + 1:
                    problems.append(f"manifest_tier1.csv lines={n} (expected {args.expected_cases+1})")
            else:
                problems.append(f"Missing {m1}")
        if check_tier1_alt:
            if m1a.exists():
                n = count_lines(m1a)
                if n != args.expected_cases + 1:
                    problems.append(f"manifest_tier1_alt.csv lines={n} (expected {args.expected_cases+1})")
            else:
                problems.append(f"Missing {m1a}")
        if args.check_tier2:
            if m2.exists():
                n = count_lines(m2)
                if n != args.expected_cases + 1:
                    problems.append(f"manifest_tier2.csv lines={n} (expected {args.expected_cases+1})")
            else:
                problems.append(f"Missing {m2}")

    # --- Tier folder counts ---
    t0_cases = sorted([p.name for p in t0.iterdir() if p.is_dir()]) if t0.exists() else []
    t1_cases = sorted([p.name for p in t1.iterdir() if p.is_dir()]) if t1.exists() else []
    t1a_cases = sorted([p.name for p in t1a.iterdir() if p.is_dir()]) if t1a.exists() else []
    t2_cases = sorted([p.name for p in t2.iterdir() if p.is_dir()]) if t2.exists() else []

    if len(t0_cases) != args.expected_cases:
        problems.append(f"Tier-0 case folders={len(t0_cases)} (expected {args.expected_cases})")
    if check_tier1 and len(t1_cases) != args.expected_cases:
        problems.append(f"Tier-1 case folders={len(t1_cases)} (expected {args.expected_cases})")
    if check_tier1_alt and len(t1a_cases) != args.expected_cases:
        problems.append(f"Tier-1-alt case folders={len(t1a_cases)} (expected {args.expected_cases})")
    if args.check_tier2 and len(t2_cases) != args.expected_cases:
        problems.append(f"Tier-2 case folders={len(t2_cases)} (expected {args.expected_cases})")

    # Check case ID match across tiers
    if check_tier1:
        missing_in_t1 = sorted(set(t0_cases) - set(t1_cases))
        missing_in_t0 = sorted(set(t1_cases) - set(t0_cases))
        if missing_in_t1:
            problems.append(f"Cases missing Tier-1 folders (first 10): {missing_in_t1[:10]}")
        if missing_in_t0:
            problems.append(f"Cases missing Tier-0 folders (first 10): {missing_in_t0[:10]}")
    if check_tier1_alt:
        missing_in_t1a = sorted(set(t0_cases) - set(t1a_cases))
        missing_in_t0_from_t1a = sorted(set(t1a_cases) - set(t0_cases))
        if missing_in_t1a:
            problems.append(f"Cases missing Tier-1-alt folders (first 10): {missing_in_t1a[:10]}")
        if missing_in_t0_from_t1a:
            problems.append(f"Tier-1-alt has unknown case folders (first 10): {missing_in_t0_from_t1a[:10]}")
    if args.check_tier2:
        missing_in_t2 = sorted(set(t0_cases) - set(t2_cases))
        missing_in_t0_from_t2 = sorted(set(t2_cases) - set(t0_cases))
        if missing_in_t2:
            problems.append(f"Cases missing Tier-2 folders (first 10): {missing_in_t2[:10]}")
        if missing_in_t0_from_t2:
            problems.append(f"Tier-2 has unknown case folders (first 10): {missing_in_t0_from_t2[:10]}")

    # --- Per-case file checks ---
    # Tier-0 files
    for cid in t0_cases:
        f0 = t0 / cid / "tier0_full_5hz.csv"
        if not f0.exists():
            problems.append(f"[Tier0] Missing CSV: {f0}")
            continue
        n = count_lines(f0)
        if n != args.expected_lines:
            problems.append(f"[Tier0] {cid} lines={n} (expected {args.expected_lines})")

    # Tier-1 files + core sanity
    core_cols = ["cpu_power_w", "processor_power_w", "cpu_avg_freq_mhz", "gpu_avg_freq_mhz"]
    if check_tier1:
        for cid in t1_cases:
            core = t1 / cid / "tier1_core_5hz.csv"
            full = t1 / cid / "tier1_full_5hz.csv"
            if not core.exists():
                problems.append(f"[Tier1] Missing core CSV: {core}")
            else:
                n = count_lines(core)
                if n != args.expected_lines:
                    problems.append(f"[Tier1] {cid} core lines={n} (expected {args.expected_lines})")
                else:
                    counts, _ = read_csv_first_pass_non_nan(core, core_cols)
                    for c in core_cols:
                        if counts[c] == 0:
                            problems.append(f"[Tier1] {cid} core column '{c}' is all-NaN/empty")
            if not full.exists():
                problems.append(f"[Tier1] Missing full CSV: {full}")
            else:
                n = count_lines(full)
                if n != args.expected_lines:
                    problems.append(f"[Tier1] {cid} full lines={n} (expected {args.expected_lines})")
            raw = t1 / cid / "powermetrics_raw.txt"
            if not args.processed_only and not raw.exists():
                problems.append(f"[Tier1] Missing raw txt: {raw}")

    # Tier-1-alt files + core sanity
    if check_tier1_alt:
        tier1_alt_core_cols = ["cpu_power_w", "gpu_power_w", "cpu_avg_freq_mhz"]
        for cid in t1a_cases:
            core = t1a / cid / "tier1_alt_core_5hz.csv"
            full = t1a / cid / "tier1_alt_full_5hz.csv"
            raw = t1a / cid / "macmon_raw.jsonl"
            if not core.exists():
                problems.append(f"[Tier1-alt] Missing core CSV: {core}")
            else:
                n = count_lines(core)
                if n != args.expected_lines:
                    problems.append(f"[Tier1-alt] {cid} core lines={n} (expected {args.expected_lines})")
                else:
                    counts, _ = read_csv_first_pass_non_nan(core, tier1_alt_core_cols)
                    if not any(counts[c] > 0 for c in tier1_alt_core_cols):
                        problems.append(
                            f"[Tier1-alt] {cid} key core columns are all-NaN/empty "
                            f"(checked: {tier1_alt_core_cols})"
                        )
            if not full.exists():
                problems.append(f"[Tier1-alt] Missing full CSV: {full}")
            else:
                n = count_lines(full)
                if n != args.expected_lines:
                    problems.append(f"[Tier1-alt] {cid} full lines={n} (expected {args.expected_lines})")
            if not args.processed_only and not raw.exists():
                problems.append(f"[Tier1-alt] Missing raw jsonl: {raw}")

    # Tier-2 files + core sanity
    if args.check_tier2:
        for cid in t2_cases:
            core = t2 / cid / "tier2_core_5hz.csv"
            full = t2 / cid / "tier2_full_5hz.csv"
            raw = t2 / cid / "xctrace_export.xml"
            if not core.exists():
                problems.append(f"[Tier2] Missing core CSV: {core}")
            else:
                n = count_lines(core)
                if n != args.expected_lines:
                    problems.append(f"[Tier2] {cid} core lines={n} (expected {args.expected_lines})")
                else:
                    tier2_core_cols = pick_tier2_key_cols(core)
                    if not tier2_core_cols:
                        problems.append(f"[Tier2] {cid} could not infer key core columns from header")
                        continue
                    counts, _ = read_csv_first_pass_non_nan(core, tier2_core_cols)
                    if not any(counts[c] > 0 for c in tier2_core_cols):
                        problems.append(
                            f"[Tier2] {cid} key core columns are all-NaN/empty "
                            f"(checked: {tier2_core_cols})"
                        )
            if not full.exists():
                problems.append(f"[Tier2] Missing full CSV: {full}")
            else:
                n = count_lines(full)
                if n != args.expected_lines:
                    problems.append(f"[Tier2] {cid} full lines={n} (expected {args.expected_lines})")
            if not args.processed_only and not raw.exists():
                problems.append(f"[Tier2] Missing raw export: {raw}")

    # --- Report ---
    if problems:
        print("❌ DATASET VALIDATION FAILED")
        print("Problems:")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    else:
        print("✅ DATASET VALIDATION PASSED")
        extra_parts = []
        if check_tier1_alt:
            extra_parts.append(f"Tier-1-alt folders: {len(t1a_cases)}")
        if args.check_tier2:
            extra_parts.append(f"Tier-2 folders: {len(t2_cases)}")
        extra = " | " + " | ".join(extra_parts) if extra_parts else ""
        tier1_part = f"Tier-1 folders: {len(t1_cases)}" if check_tier1 else "Tier-1 folders: skipped"
        print(f"Tier-0 folders: {len(t0_cases)} | {tier1_part}{extra}")
        print(f"All required CSVs exist and have {args.expected_lines-1} rows ({args.expected_lines} lines).")
        msg = "Tier-1 core sanity columns are populated."
        if not check_tier1:
            msg = "Tier-1 core sanity checks were skipped."
        if check_tier1_alt:
            msg += " Tier-1-alt core sanity columns are populated."
        if args.check_tier2:
            msg += " Tier-2 core sanity columns are populated."
        print(msg)
        sys.exit(0)


if __name__ == "__main__":
    main()
