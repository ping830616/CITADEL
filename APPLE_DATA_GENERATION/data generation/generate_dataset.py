#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
from time import perf_counter

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dice.cfg import all_cases, case_id
from dice.run_itc_two_phase import (
    run_case_tier0,
    run_case_tier1,
    run_case_tier1_alt,
    run_case_tier2,
    can_run_tier1,
    can_run_tier1_alt,
    can_run_tier2,
    ensure_xctrace_ready,
)


def mkdirp(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def format_seconds(seconds: float) -> str:
    total = int(round(max(seconds, 0.0)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:d}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes:d}m {secs:02d}s"
    return f"{secs:d}s"


def print_tier_timing_note(phase: str, duration_s: int, n_cases: int) -> None:
    expected = duration_s * n_cases
    note = f"[DICE] {phase}: nominal collection window is about {format_seconds(expected)} for {n_cases} cases"
    if phase == "tier0":
        note += " (+ about 10s once for the Tier-0 schema probe if the schema does not already exist)"
    elif phase == "tier1_alt":
        note += " (+ parsing overhead; fallback to powermetrics can make a failed case take roughly twice as long)"
    elif phase == "tier1":
        note += " (+ parsing overhead and any sudo/powermetrics startup time)"
    elif phase == "tier2":
        note += " (+ trace export overhead after each capture)"
    print(note)


def run_phase(phase: str, cases, runner, duration_s: int) -> None:
    tier_start = perf_counter()
    total = len(cases)
    print(f"[DICE] Generating {phase} for {total} cases...")
    print_tier_timing_note(phase, duration_s, total)

    for idx, c in enumerate(cases, start=1):
        cid = case_id(c.workload, c.stressor)
        case_start = perf_counter()
        print(f"[DICE] [{phase}] {idx}/{total} starting {cid}")
        try:
            runner(c)
        except Exception:
            case_elapsed = perf_counter() - case_start
            tier_elapsed = perf_counter() - tier_start
            print(
                f"[DICE] [{phase}] {idx}/{total} failed {cid} after {format_seconds(case_elapsed)} "
                f"(tier elapsed {format_seconds(tier_elapsed)})"
            )
            raise

        case_elapsed = perf_counter() - case_start
        tier_elapsed = perf_counter() - tier_start
        avg_case = tier_elapsed / idx
        remaining = avg_case * (total - idx)
        print(
            f"[DICE] [{phase}] {idx}/{total} finished {cid} in {format_seconds(case_elapsed)} | "
            f"tier elapsed {format_seconds(tier_elapsed)} | est. remaining {format_seconds(remaining)}"
        )

    tier_elapsed = perf_counter() - tier_start
    print(f"[DICE] {phase} complete in {format_seconds(tier_elapsed)}")


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Generate the DICE ITC dataset across Tier-0, Tier-1, and Tier-2 collection phases. "
            "'recommended' runs the Apple Silicon release profile (Tier-0 + Tier-1-alt + Tier-2); "
            "'portable' collects the best available tier set on the current machine."
        )
    )
    ap.add_argument(
        "--phase",
        choices=["tier0", "tier1", "tier1_alt", "tier2", "both", "all", "recommended", "portable"],
        default="recommended",
    )
    ap.add_argument("--duration_s", "--duration-s", dest="duration_s", type=int, default=1000)
    ap.add_argument("--out_dir", "--out-dir", dest="out_dir", type=Path, default=REPO_ROOT / "data")
    ap.add_argument("--scripts_dir", "--scripts-dir", dest="scripts_dir", type=Path, default=REPO_ROOT / "scripts")
    ap.add_argument("--tier2_template", "--tier2-template", dest="tier2_template", default="Time Profiler")
    ap.add_argument("--tier1_alt_bin", "--tier1-alt-bin", dest="tier1_alt_bin", default="macmon")
    ap.add_argument("--capture_crash_evidence", "--capture-crash-evidence", dest="capture_crash_evidence", action="store_true")
    ap.add_argument("--capture_crash_screenshot", "--capture-crash-screenshot", dest="capture_crash_screenshot", action="store_true")
    ap.add_argument("--crash_log_grace_s", "--crash-log-grace-s", dest="crash_log_grace_s", type=int, default=60)
    args = ap.parse_args()

    out_root = Path(args.out_dir)
    scripts_dir = Path(args.scripts_dir)
    mkdirp(out_root / "tier0")
    mkdirp(out_root / "tier1")
    mkdirp(out_root / "tier1_alt")
    mkdirp(out_root / "tier2")
    mkdirp(out_root / "meta")
    mkdirp(out_root / "logs")

    cases = all_cases()

    if args.phase in ("tier0", "both", "all", "recommended", "portable"):
        run_phase(
            "tier0",
            cases,
            lambda c: run_case_tier0(
                c.workload,
                c.stressor,
                c.label,
                args.duration_s,
                out_root=out_root,
                capture_crash_evidence=args.capture_crash_evidence,
                crash_log_grace_s=args.crash_log_grace_s,
                capture_crash_screenshot=args.capture_crash_screenshot,
            ),
            args.duration_s,
        )

    if args.phase in ("tier1", "both", "all"):
        run_phase(
            "tier1",
            cases,
            lambda c: run_case_tier1(
                c.workload,
                c.stressor,
                c.label,
                args.duration_s,
                out_root=out_root,
                scripts_dir=scripts_dir,
                capture_crash_evidence=args.capture_crash_evidence,
                crash_log_grace_s=args.crash_log_grace_s,
                capture_crash_screenshot=args.capture_crash_screenshot,
            ),
            args.duration_s,
        )

    if args.phase in ("tier1_alt", "recommended"):
        run_phase(
            "tier1_alt",
            cases,
            lambda c: run_case_tier1_alt(
                c.workload,
                c.stressor,
                c.label,
                args.duration_s,
                out_root=out_root,
                scripts_dir=scripts_dir,
                macmon_bin=args.tier1_alt_bin,
                capture_crash_evidence=args.capture_crash_evidence,
                crash_log_grace_s=args.crash_log_grace_s,
                capture_crash_screenshot=args.capture_crash_screenshot,
            ),
            args.duration_s,
        )
    elif args.phase == "portable":
        if can_run_tier1_alt(args.tier1_alt_bin):
            run_phase(
                "tier1_alt",
                cases,
                lambda c: run_case_tier1_alt(
                    c.workload,
                    c.stressor,
                    c.label,
                    args.duration_s,
                    out_root=out_root,
                    scripts_dir=scripts_dir,
                    macmon_bin=args.tier1_alt_bin,
                    capture_crash_evidence=args.capture_crash_evidence,
                    crash_log_grace_s=args.crash_log_grace_s,
                    capture_crash_screenshot=args.capture_crash_screenshot,
                ),
                args.duration_s,
            )
        elif can_run_tier1():
            print("[DICE] portable mode: macmon is unavailable; falling back to legacy Tier-1 powermetrics collection.")
            run_phase(
                "tier1",
                cases,
                lambda c: run_case_tier1(
                    c.workload,
                    c.stressor,
                    c.label,
                    args.duration_s,
                    out_root=out_root,
                    scripts_dir=scripts_dir,
                    capture_crash_evidence=args.capture_crash_evidence,
                    crash_log_grace_s=args.crash_log_grace_s,
                    capture_crash_screenshot=args.capture_crash_screenshot,
                ),
                args.duration_s,
            )
        else:
            print("[DICE] portable mode: skipping Tier-1 because neither macmon nor powermetrics is available on this machine.")

    if args.phase in ("tier2", "all", "recommended"):
        ensure_xctrace_ready()
        run_phase(
            "tier2",
            cases,
            lambda c: run_case_tier2(
                c.workload,
                c.stressor,
                c.label,
                args.duration_s,
                out_root=out_root,
                scripts_dir=scripts_dir,
                template=args.tier2_template,
                capture_crash_evidence=args.capture_crash_evidence,
                crash_log_grace_s=args.crash_log_grace_s,
                capture_crash_screenshot=args.capture_crash_screenshot,
            ),
            args.duration_s,
        )
    elif args.phase == "portable":
        if can_run_tier2():
            run_phase(
                "tier2",
                cases,
                lambda c: run_case_tier2(
                    c.workload,
                    c.stressor,
                    c.label,
                    args.duration_s,
                    out_root=out_root,
                    scripts_dir=scripts_dir,
                    template=args.tier2_template,
                    capture_crash_evidence=args.capture_crash_evidence,
                    crash_log_grace_s=args.crash_log_grace_s,
                    capture_crash_screenshot=args.capture_crash_screenshot,
                ),
                args.duration_s,
            )
        else:
            print("[DICE] portable mode: skipping Tier-2 because xctrace is unavailable on this machine.")

    print(f"[DICE] Done. Output root: {out_root}")


if __name__ == "__main__":
    main()
