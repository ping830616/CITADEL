#!/usr/bin/env python3
"""Collect one continuous Intel PCM trace across benign PAMPAR workloads.

One Intel PCM process remains active while workload processes are stopped and
started at recorded phase boundaries. This provides the physical transition
evidence that cannot be reconstructed from the preserved per workload files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import queue
import random
import shlex
import signal
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


WORKLOADS = ("DFT", "DJ", "DP", "GL", "GS", "HA", "JA", "MM", "NI", "OE", "PI", "SH", "TR")
DEFAULT_WORKLOADS = ("DFT", "DJ", "DP", "GL", "GS", "HA", "JA", "MM", "NI", "OE", "PI", "TR")
THREADS = {"A": 4, "B": 16}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _cpu_brand() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                return line.split(":", 1)[1].strip()
    return platform.processor() or "unknown"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect a continuous Intel PCM trace across randomized PAMPAR workloads."
    )
    parser.add_argument("--setup", choices=("A", "B"), required=True)
    parser.add_argument("--pampar-root", type=Path, required=True)
    parser.add_argument("--pcm-bin", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=_repo_root() / "data" / "telemetry" / "raw" / "intel_transitions",
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--run-index", type=int, default=None)
    parser.add_argument("--runs-purpose", default="benign_workload_transition")
    parser.add_argument("--pcm-interval-seconds", type=float, default=0.1)
    parser.add_argument("--pcm-warmup-seconds", type=float, default=2.0)
    parser.add_argument("--dwell-seconds", type=float, default=20.0)
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--calibration-cycles", type=int, default=2)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument(
        "--workloads", nargs="+", choices=WORKLOADS, default=list(DEFAULT_WORKLOADS)
    )
    parser.add_argument("--sh-input", type=Path, default=None)
    parser.add_argument("--sh-height", type=int, default=3000)
    parser.add_argument("--sh-width", type=int, default=3000)
    parser.add_argument(
        "--privilege-command",
        default="sudo",
        help="Command placed before PCM, or an empty string when privileges are configured separately.",
    )
    parser.add_argument("--maximum-switch-gap-seconds", type=float, default=3.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--allow-non-intel-smoke",
        action="store_true",
        help="Permit a non Intel host only for an explicit fake tool smoke test.",
    )
    return parser


def _validate(args: argparse.Namespace, *, check_host: bool) -> None:
    if args.pcm_interval_seconds <= 0:
        raise ValueError("--pcm-interval-seconds must be positive")
    if args.pcm_warmup_seconds < 0:
        raise ValueError("--pcm-warmup-seconds cannot be negative")
    if args.dwell_seconds <= 0:
        raise ValueError("--dwell-seconds must be positive")
    if args.cycles <= args.calibration_cycles or args.calibration_cycles < 2:
        raise ValueError("Use at least two calibration cycles and one evaluation cycle")
    if args.maximum_switch_gap_seconds <= 0:
        raise ValueError("--maximum-switch-gap-seconds must be positive")
    if len(set(args.workloads)) != len(args.workloads):
        raise ValueError("--workloads cannot contain duplicates")
    if len(args.workloads) < 3:
        raise ValueError("Use at least three workloads for transition testing")
    if "SH" in args.workloads:
        if args.sh_input is None or not args.sh_input.expanduser().is_file():
            raise ValueError("SH requires --sh-input pointing to the exact input image")
        if args.sh_height <= 0 or args.sh_width <= 0:
            raise ValueError("SH dimensions must be positive")
    if check_host and not args.allow_non_intel_smoke:
        brand = _cpu_brand().lower()
        if platform.system() != "Linux" or "intel" not in brand:
            raise RuntimeError(
                "A physical run requires an Intel Linux host. Use --allow-non-intel-smoke "
                "only with fake tools for pipeline testing."
            )


def _workload_command(
    setup: str,
    workload: str,
    pampar_root: Path,
    sh_input: Path | None,
    sh_height: int,
    sh_width: int,
) -> list[str]:
    threads = str(THREADS[setup])
    executable = pampar_root / "Apps" / workload / "pthread"
    if workload == "DFT":
        arguments = [threads, "32768" if setup == "A" else "50000"]
    elif workload == "DJ":
        arguments = [threads, "16384", str(pampar_root / "Apps" / "DJ" / "inputDJ" / "1024.txt")]
    elif workload == "DP":
        arguments = [threads, "50000000000" if setup == "A" else "100000000000"]
    elif workload == "GL":
        arguments = [threads, str(pampar_root / "Apps" / "GL" / "inputGL" / "1024.txt")]
    elif workload == "GS":
        arguments = [threads, "1300"]
    elif workload == "HA":
        arguments = [threads, "10000", "300000" if setup == "A" else "1200000"]
    elif workload == "JA":
        arguments = [threads, "4096"]
    elif workload == "MM":
        arguments = [threads, "4096" if setup == "A" else "5000"]
    elif workload == "NI":
        arguments = [threads, "5000000000"]
    elif workload == "OE":
        arguments = [threads, "300000"]
    elif workload == "PI":
        arguments = [threads, "4000000000" if setup == "A" else "8000000000"]
    elif workload == "SH":
        if sh_input is None:
            raise ValueError("SH requires --sh-input")
        arguments = [str(sh_input), str(sh_height), str(sh_width), threads]
    elif workload == "TR":
        arguments = [threads, "2500"]
    else:
        raise ValueError(f"Unsupported workload: {workload}")
    return [str(executable), *arguments]


def _phase_plan(workloads: list[str], cycles: int, seed: int) -> list[dict[str, object]]:
    rng = random.Random(int(seed))
    plan: list[dict[str, object]] = []
    previous: str | None = None
    used: set[tuple[str, ...]] = set()
    for cycle_index in range(cycles):
        for _ in range(10_000):
            order = list(workloads)
            rng.shuffle(order)
            key = tuple(order)
            if (previous is None or order[0] != previous) and key not in used:
                break
        else:
            raise RuntimeError("Could not create a unique boundary safe workload order")
        used.add(tuple(order))
        for position, workload in enumerate(order):
            plan.append(
                {
                    "phase_index": len(plan),
                    "cycle_index": cycle_index,
                    "cycle_position": position,
                    "workload": workload,
                }
            )
        previous = order[-1]
    return plan


def _write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _stop_process(process: subprocess.Popen[object], timeout: float = 5.0) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=timeout)
    except ProcessLookupError:
        pass


def _workload_loop(
    command: list[str],
    workload: str,
    phase_index: int,
    stop_event: threading.Event,
    invocation_rows: list[dict[str, object]],
    error_queue: queue.Queue[dict[str, str]],
    log_path: Path,
) -> None:
    invocation = 0
    try:
        with log_path.open("ab") as log_handle:
            while not stop_event.is_set():
                started = time.time()
                process = subprocess.Popen(
                    command,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                row = {
                    "phase_index": phase_index,
                    "workload": workload,
                    "invocation_index": invocation,
                    "pid": process.pid,
                    "start_ts_unix_s": started,
                    "end_ts_unix_s": None,
                    "returncode": None,
                    "termination_reason": None,
                }
                invocation_rows.append(row)
                while process.poll() is None and not stop_event.wait(0.05):
                    pass
                if stop_event.is_set() and process.poll() is None:
                    _stop_process(process)
                    row["termination_reason"] = "scheduled_phase_end"
                else:
                    row["termination_reason"] = "workload_completed"
                row["end_ts_unix_s"] = time.time()
                row["returncode"] = process.returncode
                if process.returncode not in (0, -signal.SIGTERM, -signal.SIGKILL):
                    raise RuntimeError(
                        f"{workload} invocation {invocation} returned {process.returncode}"
                    )
                invocation += 1
    except BaseException as exc:
        error_queue.put(
            {
                "phase_index": str(phase_index),
                "workload": workload,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        )
        stop_event.set()


def _write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    repo_root: Path,
    status: str,
    phase_plan: list[dict[str, object]],
    phase_events: list[dict[str, object]],
    workload_commands: dict[str, list[str]],
    pcm_command: list[str],
    pcm_returncode: int | None,
    error: str | None,
    started_at: str,
) -> None:
    payload = {
        "status": status,
        "started_at_utc": started_at,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(repo_root),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_brand": _cpu_brand(),
        "python_version": platform.python_version(),
        "setup": args.setup,
        "protocol": {
            "purpose": args.runs_purpose,
            "campaign_id": args.campaign_id,
            "run_index": args.run_index,
            "seed": args.seed,
            "workloads": list(args.workloads),
            "cycles": args.cycles,
            "calibration_cycles": args.calibration_cycles,
            "evaluation_cycles": args.cycles - args.calibration_cycles,
            "dwell_seconds": args.dwell_seconds,
            "pcm_requested_interval_seconds": args.pcm_interval_seconds,
            "pcm_warmup_seconds": args.pcm_warmup_seconds,
            "continuous_pcm_process": True,
            "phase_orders": [
                [
                    phase["workload"]
                    for phase in phase_plan
                    if phase["cycle_index"] == cycle
                ]
                for cycle in range(args.cycles)
            ],
            "labels": "scheduled benign workload phase",
            "physical_transition_status": (
                "workload processes changed while one Intel PCM process remained active"
            ),
            "operating_condition_control": "none; natural PCM operating telemetry recorded",
        },
        "pampar_root": str(args.pampar_root.expanduser().resolve()),
        "pcm_binary": str(args.pcm_bin.expanduser().resolve()),
        "privilege_command": args.privilege_command or "none",
        "workload_commands": workload_commands,
        "pcm_command": pcm_command,
        "pcm_returncode": pcm_returncode,
        "phase_events": phase_events,
        "error": error,
        "source_files": {
            _portable_path(Path(__file__), repo_root): _sha256(Path(__file__)),
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = _parser().parse_args()
    _validate(args, check_host=not args.dry_run)
    repo_root = _repo_root()
    pampar_root = args.pampar_root.expanduser().resolve()
    pcm_bin = args.pcm_bin.expanduser().resolve()
    sh_input = args.sh_input.expanduser().resolve() if args.sh_input else None
    phase_plan = _phase_plan(list(args.workloads), args.cycles, args.seed)
    workload_commands = {
        workload: _workload_command(
            args.setup,
            workload,
            pampar_root,
            sh_input,
            args.sh_height,
            args.sh_width,
        )
        for workload in args.workloads
    }
    total_phase_seconds = len(phase_plan) * args.dwell_seconds
    pcm_iterations = int(
        math.ceil(
            (args.pcm_warmup_seconds + total_phase_seconds + 30.0)
            / args.pcm_interval_seconds
        )
    )
    privilege = shlex.split(args.privilege_command) if args.privilege_command else []
    pcm_raw_placeholder = "<run_dir>/pcm_raw.csv"
    pcm_command_plan = [
        *privilege,
        str(pcm_bin),
        str(args.pcm_interval_seconds),
        f"-i={pcm_iterations}",
        f"-csv={pcm_raw_placeholder}",
    ]
    plan = {
        "setup": args.setup,
        "seed": args.seed,
        "phase_count": len(phase_plan),
        "phase_orders": [
            [
                phase["workload"]
                for phase in phase_plan
                if phase["cycle_index"] == cycle
            ]
            for cycle in range(args.cycles)
        ],
        "calibration_cycles": args.calibration_cycles,
        "evaluation_cycles": args.cycles - args.calibration_cycles,
        "dwell_seconds": args.dwell_seconds,
        "estimated_collection_seconds": total_phase_seconds + args.pcm_warmup_seconds,
        "continuous_pcm_process": True,
        "pcm_command": pcm_command_plan,
        "workload_commands": workload_commands,
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0

    if not pampar_root.is_dir():
        raise FileNotFoundError(f"PAMPAR root not found: {pampar_root}")
    if not pcm_bin.is_file() or not os.access(pcm_bin, os.X_OK):
        raise FileNotFoundError(f"PCM binary is not executable: {pcm_bin}")
    for workload, command in workload_commands.items():
        executable = Path(command[0])
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise FileNotFoundError(f"{workload} executable is not available: {executable}")
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output_root.expanduser().resolve() / run_id
    if run_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing run directory: {run_dir}")
    run_dir.mkdir(parents=True)
    pcm_raw_path = run_dir / "pcm_raw.csv"
    pcm_stderr_path = run_dir / "pcm_stderr.log"
    phase_path = run_dir / "phase_events.csv"
    invocation_path = run_dir / "workload_invocations.csv"
    manifest_path = run_dir / "collection_manifest.json"
    pcm_command = [
        *privilege,
        str(pcm_bin),
        str(args.pcm_interval_seconds),
        f"-i={pcm_iterations}",
        f"-csv={pcm_raw_path}",
    ]
    started_at = datetime.now(timezone.utc).isoformat()
    phase_events: list[dict[str, object]] = []
    invocation_rows: list[dict[str, object]] = []
    workload_errors: queue.Queue[dict[str, str]] = queue.Queue()
    active_thread: threading.Thread | None = None
    active_stop: threading.Event | None = None
    pcm_process: subprocess.Popen[object] | None = None
    status = "running"
    failure: str | None = None
    previous_end = None
    try:
        with pcm_stderr_path.open("wb") as stderr_handle:
            pcm_process = subprocess.Popen(
                pcm_command,
                stdout=subprocess.DEVNULL,
                stderr=stderr_handle,
                start_new_session=True,
            )
            time.sleep(args.pcm_warmup_seconds)
            if pcm_process.poll() is not None:
                raise RuntimeError(
                    f"Intel PCM exited during warmup with code {pcm_process.returncode}"
                )
            for phase in phase_plan:
                if active_stop is not None and active_thread is not None:
                    active_stop.set()
                    active_thread.join(timeout=args.maximum_switch_gap_seconds)
                    if active_thread.is_alive():
                        raise RuntimeError("Previous workload did not stop within the switch limit")
                if not workload_errors.empty():
                    raise RuntimeError(json.dumps(workload_errors.get_nowait()))
                started_wall = time.time()
                switch_gap = None if previous_end is None else started_wall - previous_end
                if switch_gap is not None and switch_gap > args.maximum_switch_gap_seconds:
                    raise RuntimeError(
                        f"Workload switch gap {switch_gap:.6f}s exceeded "
                        f"{args.maximum_switch_gap_seconds:.6f}s"
                    )
                workload = str(phase["workload"])
                active_stop = threading.Event()
                active_thread = threading.Thread(
                    target=_workload_loop,
                    args=(
                        workload_commands[workload],
                        workload,
                        int(phase["phase_index"]),
                        active_stop,
                        invocation_rows,
                        workload_errors,
                        run_dir / f"workload_{int(phase['phase_index']):03d}_{workload}.log",
                    ),
                    daemon=True,
                )
                active_thread.start()
                event = {
                    **phase,
                    "start_ts_unix_s": started_wall,
                    "end_ts_unix_s": None,
                    "switch_gap_seconds": switch_gap,
                }
                phase_events.append(event)
                print(
                    f"Phase {int(phase['phase_index']) + 1}/{len(phase_plan)}: "
                    f"{workload} for {args.dwell_seconds:g}s",
                    flush=True,
                )
                deadline = time.monotonic() + args.dwell_seconds
                while time.monotonic() < deadline:
                    if pcm_process.poll() is not None:
                        raise RuntimeError(
                            f"Intel PCM stopped during collection with code {pcm_process.returncode}"
                        )
                    if not workload_errors.empty():
                        raise RuntimeError(json.dumps(workload_errors.get_nowait()))
                    time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
                previous_end = time.time()
                event["end_ts_unix_s"] = previous_end
            status = "complete"
    except KeyboardInterrupt:
        status = "interrupted"
        failure = "KeyboardInterrupt"
    except BaseException as exc:
        status = "failed"
        failure = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        if active_stop is not None:
            active_stop.set()
        if active_thread is not None:
            active_thread.join(timeout=args.maximum_switch_gap_seconds)
        if phase_events and phase_events[-1]["end_ts_unix_s"] is None:
            phase_events[-1]["end_ts_unix_s"] = time.time()
        if pcm_process is not None and pcm_process.poll() is None:
            try:
                os.killpg(pcm_process.pid, signal.SIGINT)
                pcm_process.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                _stop_process(pcm_process)
            except ProcessLookupError:
                pass
        _write_csv(
            phase_path,
            phase_events,
            [
                "phase_index",
                "cycle_index",
                "cycle_position",
                "workload",
                "start_ts_unix_s",
                "end_ts_unix_s",
                "switch_gap_seconds",
            ],
        )
        _write_csv(
            invocation_path,
            invocation_rows,
            [
                "phase_index",
                "workload",
                "invocation_index",
                "pid",
                "start_ts_unix_s",
                "end_ts_unix_s",
                "returncode",
                "termination_reason",
            ],
        )
        if status == "complete":
            if not pcm_raw_path.is_file() or pcm_raw_path.stat().st_size == 0:
                status = "failed"
                failure = "Intel PCM output is missing or empty"
            if len(phase_events) != len(phase_plan):
                status = "failed"
                failure = "Not every planned phase was recorded"
        _write_manifest(
            manifest_path,
            args=args,
            repo_root=repo_root,
            status=status,
            phase_plan=phase_plan,
            phase_events=phase_events,
            workload_commands=workload_commands,
            pcm_command=pcm_command,
            pcm_returncode=pcm_process.returncode if pcm_process is not None else None,
            error=failure,
            started_at=started_at,
        )
    print(json.dumps({"status": status, "run_dir": str(run_dir)}))
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
