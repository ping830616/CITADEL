#!/usr/bin/env python3
"""Collect repeated independent Intel benign workload transition runs."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


WORKLOADS = ("DFT", "DJ", "DP", "GL", "GS", "HA", "JA", "MM", "NI", "OE", "PI", "SH", "TR")
DEFAULT_WORKLOADS = ("DFT", "DJ", "DP", "GL", "GS", "HA", "JA", "MM", "NI", "OE", "PI", "TR")


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
        description="Collect independent continuous Intel workload transition runs."
    )
    parser.add_argument("--setup", choices=("A", "B"), required=True)
    parser.add_argument("--pampar-root", type=Path, required=True)
    parser.add_argument("--pcm-bin", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=_repo_root()
        / "data"
        / "telemetry"
        / "raw"
        / "intel_transition_campaigns",
    )
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--calibration-cycles", type=int, default=2)
    parser.add_argument("--evaluation-cycles", type=int, default=3)
    parser.add_argument("--dwell-seconds", type=float, default=20.0)
    parser.add_argument("--pcm-interval-seconds", type=float, default=0.1)
    parser.add_argument("--pcm-warmup-seconds", type=float, default=2.0)
    parser.add_argument("--cooldown-seconds", type=float, default=120.0)
    parser.add_argument("--seed-base", type=int, default=123)
    parser.add_argument("--maximum-switch-gap-seconds", type=float, default=3.0)
    parser.add_argument(
        "--workloads", nargs="+", choices=WORKLOADS, default=list(DEFAULT_WORKLOADS)
    )
    parser.add_argument("--sh-input", type=Path, default=None)
    parser.add_argument("--sh-height", type=int, default=3000)
    parser.add_argument("--sh-width", type=int, default=3000)
    parser.add_argument("--privilege-command", default="sudo")
    parser.add_argument("--allow-non-intel-smoke", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _validate(args: argparse.Namespace) -> None:
    if args.runs < 3:
        raise ValueError("--runs must be at least 3 for across run variation")
    if args.calibration_cycles < 2:
        raise ValueError("--calibration-cycles must be at least 2")
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
    run_id = f"run_{run_index + 1:02d}_seed_{seed}"
    command = [
        sys.executable,
        str(collector),
        "--setup",
        args.setup,
        "--pampar-root",
        str(args.pampar_root),
        "--pcm-bin",
        str(args.pcm_bin),
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
        str(args.calibration_cycles + args.evaluation_cycles),
        "--calibration-cycles",
        str(args.calibration_cycles),
        "--dwell-seconds",
        str(args.dwell_seconds),
        "--pcm-interval-seconds",
        str(args.pcm_interval_seconds),
        "--pcm-warmup-seconds",
        str(args.pcm_warmup_seconds),
        "--maximum-switch-gap-seconds",
        str(args.maximum_switch_gap_seconds),
        "--privilege-command",
        args.privilege_command,
        "--workloads",
        *args.workloads,
    ]
    if args.sh_input:
        command.extend(
            [
                "--sh-input",
                str(args.sh_input),
                "--sh-height",
                str(args.sh_height),
                "--sh-width",
                str(args.sh_width),
            ]
        )
    if args.allow_non_intel_smoke:
        command.append("--allow-non-intel-smoke")
    return command


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = _parser().parse_args()
    _validate(args)
    repo_root = _repo_root()
    collector = repo_root / "scripts" / "collect_intel_workload_transitions.py"
    campaign_id = args.campaign_id or datetime.now(timezone.utc).strftime(
        f"setup_{args.setup}_campaign_%Y%m%dT%H%M%SZ"
    )
    campaign_dir = args.output_root.expanduser().resolve() / campaign_id
    run_root = campaign_dir / "runs"
    seeds = [args.seed_base + 10007 * index for index in range(args.runs)]
    commands = [
        _collector_command(
            args, collector, run_root, campaign_id, run_index, seed
        )
        for run_index, seed in enumerate(seeds)
    ]
    phases_per_run = len(args.workloads) * (
        args.calibration_cycles + args.evaluation_cycles
    )
    estimated_seconds = (
        args.runs
        * (
            phases_per_run * args.dwell_seconds
            + args.pcm_warmup_seconds
        )
        + max(0, args.runs - 1) * args.cooldown_seconds
    )
    plan: dict[str, object] = {
        "campaign_id": campaign_id,
        "setup": args.setup,
        "runs": args.runs,
        "seeds": seeds,
        "workloads": list(args.workloads),
        "calibration_cycles": args.calibration_cycles,
        "evaluation_cycles": args.evaluation_cycles,
        "dwell_seconds": args.dwell_seconds,
        "pcm_requested_interval_seconds": args.pcm_interval_seconds,
        "cooldown_seconds": args.cooldown_seconds,
        "estimated_campaign_seconds": estimated_seconds,
        "commands": commands,
        "independence_definition": (
            "each run starts a new Intel PCM process after the preceding run ends "
            "and the requested cooldown completes"
        ),
    }
    if args.dry_run:
        run_plans = []
        for command in commands:
            completed = subprocess.run(
                [*command, "--dry-run"],
                cwd=repo_root,
                text=True,
                capture_output=True,
                check=True,
            )
            run_plans.append(json.loads(completed.stdout))
        plan["run_plans"] = run_plans
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
    _write_manifest(manifest_path, campaign)
    for run_index, (seed, command) in enumerate(zip(seeds, commands, strict=True)):
        print(f"Starting Intel run {run_index + 1}/{args.runs}, seed={seed}", flush=True)
        started = datetime.now(timezone.utc).isoformat()
        completed = subprocess.run(command, cwd=repo_root, check=False)
        run_dir = run_root / f"run_{run_index + 1:02d}_seed_{seed}"
        collection_manifest = run_dir / "collection_manifest.json"
        collection_status = "missing"
        if collection_manifest.is_file():
            collection_status = json.loads(
                collection_manifest.read_text(encoding="utf-8")
            ).get("status", "unknown")
        campaign["run_results"].append(
            {
                "run_index": run_index,
                "seed": seed,
                "returncode": completed.returncode,
                "collection_status": collection_status,
                "run_dir": _portable_path(run_dir, repo_root),
                "started_at_utc": started,
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        _write_manifest(manifest_path, campaign)
        if completed.returncode != 0 or collection_status != "complete":
            campaign["status"] = "failed"
            campaign["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
            _write_manifest(manifest_path, campaign)
            return 1
        if run_index + 1 < args.runs and args.cooldown_seconds > 0:
            print(f"Cooling down for {args.cooldown_seconds:g}s", flush=True)
            time.sleep(args.cooldown_seconds)
    campaign["status"] = "complete"
    campaign["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    _write_manifest(manifest_path, campaign)
    print(json.dumps({"status": "complete", "campaign_dir": str(campaign_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
