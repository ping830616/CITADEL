#!/usr/bin/env python3
"""Run a repeated, randomized Apple benign workload transition campaign."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


WORKLOADS = ("BROWSER", "PY_AI", "PY_STATS", "VIDEO_SW")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_commit(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()
    except Exception:
        return "unknown"


def _portable_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect independent randomized benign workload transition runs."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=_repo_root() / "data" / "telemetry" / "raw" / "apple_transition_campaigns",
    )
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--calibration-cycles", type=int, default=2)
    parser.add_argument("--evaluation-cycles", type=int, default=3)
    parser.add_argument("--dwell-seconds", type=float, default=60.0)
    parser.add_argument("--hz", type=float, default=5.0)
    parser.add_argument("--probe-seconds", type=float, default=5.0)
    parser.add_argument("--cooldown-seconds", type=float, default=120.0)
    parser.add_argument("--seed-base", type=int, default=123)
    parser.add_argument("--stats-elements", type=int, default=100_000_000)
    parser.add_argument("--maximum-sample-gap-seconds", type=float, default=2.0)
    parser.add_argument("--workloads", nargs="+", default=list(WORKLOADS), choices=WORKLOADS)
    parser.add_argument(
        "--fixed-order",
        dest="randomize_order",
        action="store_false",
        help="Disable the default seeded random permutation in each cycle.",
    )
    parser.set_defaults(randomize_order=True)
    parser.add_argument("--allow-non-apple", action="store_true")
    parser.add_argument("--allow-browser-offline", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _validate(args: argparse.Namespace) -> None:
    if args.runs < 3:
        raise ValueError("--runs must be at least 3 for across run variation")
    if args.calibration_cycles < 2:
        raise ValueError("--calibration-cycles must be at least 2 for this campaign")
    if args.evaluation_cycles <= 0:
        raise ValueError("--evaluation-cycles must be positive")
    if args.cooldown_seconds < 0:
        raise ValueError("--cooldown-seconds cannot be negative")


def _collector_command(
    args: argparse.Namespace,
    collector: Path,
    run_root: Path,
    campaign_id: str,
    run_index: int,
    seed: int,
) -> list[str]:
    total_cycles = int(args.calibration_cycles + args.evaluation_cycles)
    run_id = f"run_{run_index + 1:02d}_seed_{seed}"
    command = [
        sys.executable,
        str(collector),
        "--output-root",
        str(run_root),
        "--run-id",
        run_id,
        "--campaign-id",
        campaign_id,
        "--run-index",
        str(run_index),
        "--seed",
        str(seed),
        "--cycles",
        str(total_cycles),
        "--calibration-cycles",
        str(args.calibration_cycles),
        "--dwell-seconds",
        str(args.dwell_seconds),
        "--hz",
        str(args.hz),
        "--probe-seconds",
        str(args.probe_seconds),
        "--stats-elements",
        str(args.stats_elements),
        "--maximum-sample-gap-seconds",
        str(args.maximum_sample_gap_seconds),
        "--workloads",
        *args.workloads,
    ]
    if args.randomize_order:
        command.append("--randomize-order")
    if args.allow_non_apple:
        command.append("--allow-non-apple")
    if args.allow_browser_offline:
        command.append("--allow-browser-offline")
    return command


def _write_campaign_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = _parser().parse_args()
    _validate(args)
    repo_root = _repo_root()
    collector = repo_root / "scripts" / "collect_apple_workload_transitions.py"
    campaign_id = args.campaign_id or datetime.now(timezone.utc).strftime("campaign_%Y%m%dT%H%M%SZ")
    campaign_dir = args.output_root.expanduser().resolve() / campaign_id
    run_root = campaign_dir / "runs"
    seeds = [int(args.seed_base) + 10007 * index for index in range(int(args.runs))]
    commands = [
        _collector_command(args, collector, run_root, campaign_id, index, seed)
        for index, seed in enumerate(seeds)
    ]
    estimated_seconds = (
        args.runs
        * (len(args.workloads) * (args.calibration_cycles + args.evaluation_cycles) * args.dwell_seconds)
        + max(0, args.runs - 1) * args.cooldown_seconds
    )
    plan = {
        "campaign_id": campaign_id,
        "runs": int(args.runs),
        "seeds": seeds,
        "workloads": list(args.workloads),
        "randomize_order": bool(args.randomize_order),
        "calibration_cycles": int(args.calibration_cycles),
        "evaluation_cycles": int(args.evaluation_cycles),
        "dwell_seconds": float(args.dwell_seconds),
        "requested_hz": float(args.hz),
        "cooldown_seconds": float(args.cooldown_seconds),
        "estimated_campaign_seconds": float(estimated_seconds),
        "commands": commands,
    }
    if args.dry_run:
        dry_plans = []
        for command in commands:
            completed = subprocess.run(
                [*command, "--dry-run"], cwd=repo_root, text=True, capture_output=True, check=True
            )
            dry_plans.append(json.loads(completed.stdout))
        plan["run_plans"] = dry_plans
        print(json.dumps(plan, indent=2))
        return 0

    if campaign_dir.exists():
        raise FileExistsError(f"Refusing to overwrite campaign directory: {campaign_dir}")
    run_root.mkdir(parents=True)
    manifest_path = campaign_dir / "campaign_manifest.json"
    campaign = {
        **plan,
        "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "finished_at_utc": None,
        "git_commit": _git_commit(repo_root),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "run_results": [],
    }
    _write_campaign_manifest(manifest_path, campaign)

    caffeinate = shutil.which("caffeinate") if platform.system() == "Darwin" else None
    for run_index, (seed, command) in enumerate(zip(seeds, commands, strict=True)):
        print(f"Starting campaign run {run_index + 1}/{args.runs}, seed={seed}", flush=True)
        launched_command = [caffeinate, "-dimsu", *command] if caffeinate else command
        started = datetime.now(timezone.utc).isoformat()
        completed = subprocess.run(launched_command, cwd=repo_root, check=False)
        run_dir = run_root / f"run_{run_index + 1:02d}_seed_{seed}"
        collection_manifest = run_dir / "collection_manifest.json"
        collection_status = "missing"
        if collection_manifest.exists():
            collection_status = json.loads(collection_manifest.read_text(encoding="utf-8")).get(
                "status", "unknown"
            )
        campaign["run_results"].append(
            {
                "run_index": run_index,
                "seed": seed,
                "returncode": int(completed.returncode),
                "collection_status": collection_status,
                "run_dir": _portable_path(run_dir, repo_root),
                "started_at_utc": started,
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        _write_campaign_manifest(manifest_path, campaign)
        if completed.returncode != 0 or collection_status != "complete":
            campaign["status"] = "failed"
            campaign["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
            _write_campaign_manifest(manifest_path, campaign)
            print(f"Campaign stopped after failed run {run_index + 1}.", flush=True)
            return 1
        if run_index + 1 < args.runs and args.cooldown_seconds > 0:
            print(f"Cooling down for {args.cooldown_seconds:g} seconds.", flush=True)
            time.sleep(float(args.cooldown_seconds))

    campaign["status"] = "complete"
    campaign["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    _write_campaign_manifest(manifest_path, campaign)
    print(json.dumps({"status": "complete", "campaign_dir": str(campaign_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
