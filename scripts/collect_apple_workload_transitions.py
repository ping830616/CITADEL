#!/usr/bin/env python3
"""Collect one continuous Tier-0 trace across benign Apple workloads.

The workload bodies mirror the four benign workloads preserved under
APPLE_DATA_GENERATION.  The historical provenance snapshot is intentionally
left unchanged because its original configuration module was not copied into
this repository.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import platform
import queue
import random
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np


WORKLOADS = ("BROWSER", "PY_AI", "PY_STATS", "VIDEO_SW")
SEED = 123


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


def _cpu_brand() -> str:
    if platform.system() == "Darwin":
        try:
            return subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except Exception:
            pass
    return platform.processor() or "unknown"


def _browser_preflight() -> tuple[bool, str]:
    try:
        with urllib.request.urlopen("https://example.com", timeout=10) as response:
            response.read(1)
        return True, "https://example.com reachable"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _load_tier0_collector(repo_root: Path) -> tuple[ModuleType, Path]:
    source = (
        repo_root
        / "APPLE_DATA_GENERATION"
        / "data generation"
        / "src"
        / "dice"
        / "tier0_collect_schema.py"
    )
    if not source.exists():
        raise FileNotFoundError(f"Tier-0 collector not found: {source}")
    spec = importlib.util.spec_from_file_location("citadel_tier0_collector", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Tier-0 collector: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, source


def _sample_tier0(collector: ModuleType, previous: object, interval: float) -> dict[str, float]:
    """Use the preserved collector, omitting fields that macOS denies."""
    while True:
        try:
            raw = collector.sample_raw(previous, interval)
            if getattr(collector, "_citadel_pids_unavailable", False):
                raw.pop("pids_count", None)
            if getattr(collector, "_citadel_boot_time_unavailable", False):
                raw.pop("uptime_s", None)
            return raw
        except PermissionError:
            if not getattr(collector, "_citadel_swap_unavailable", False):
                collector._citadel_swap_unavailable = True
                collector.psutil.swap_memory = lambda: SimpleNamespace(
                    total=float("nan"),
                    used=float("nan"),
                    free=float("nan"),
                    percent=float("nan"),
                    sin=float("nan"),
                    sout=float("nan"),
                )
                print(
                    "Warning: macOS denied swap telemetry access; swap fields will be omitted.",
                    flush=True,
                )
                continue
            if not getattr(collector, "_citadel_pids_unavailable", False):
                collector._citadel_pids_unavailable = True
                collector.psutil.pids = lambda: []
                print(
                    "Warning: macOS denied process-list access; pids_count will be omitted.",
                    flush=True,
                )
                continue
            if not getattr(collector, "_citadel_boot_time_unavailable", False):
                collector._citadel_boot_time_unavailable = True
                collector.psutil.boot_time = time.time
                print(
                    "Warning: macOS denied boot-time access; uptime_s will be omitted.",
                    flush=True,
                )
                continue
            raise


def _seed_all() -> None:
    random.seed(SEED)
    np.random.seed(SEED)


def _workload_browser(stop_event: threading.Event) -> None:
    _seed_all()
    urls = (
        "https://example.com",
        "https://www.iana.org/domains/reserved",
        "https://www.wikipedia.org",
    )
    request_index = 0
    while not stop_event.is_set():
        try:
            urllib.request.urlopen(urls[request_index % len(urls)], timeout=5).read(200_000)
        except Exception:
            pass
        request_index += 1
        time.sleep(0.05)


def _workload_video_sw(stop_event: threading.Event) -> None:
    _seed_all()
    height, width = 720, 1280
    frame = (np.random.rand(height, width, 3) * 255).astype(np.uint8)
    while not stop_event.is_set():
        gray = (
            0.299 * frame[:, :, 0]
            + 0.587 * frame[:, :, 1]
            + 0.114 * frame[:, :, 2]
        ).astype(np.uint8)
        compressed = zlib.compress(gray[::2, ::2].tobytes(), level=1)
        _ = zlib.decompress(compressed)
        frame = (frame + 1) % 255
        time.sleep(0.005)


def _resolve_ai_backend() -> str:
    try:
        import torch

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "torch_mps_and_numpy"
        return "torch_cpu_and_numpy"
    except Exception:
        return "numpy_only_fallback"


def _workload_ai(stop_event: threading.Event, backend: str) -> None:
    _seed_all()
    numpy_size = 1024
    a_numpy = np.random.randn(numpy_size, numpy_size).astype(np.float32)
    b_numpy = np.random.randn(numpy_size, numpy_size).astype(np.float32)

    torch = None
    a_torch = None
    b_torch = None
    if backend != "numpy_only_fallback":
        import torch as torch_module

        torch = torch_module
        torch.manual_seed(SEED)
        device_name = "mps" if backend == "torch_mps_and_numpy" else "cpu"
        device = torch.device(device_name)
        torch_size = 2048
        a_torch = torch.randn((torch_size, torch_size), device=device, dtype=torch.float32)
        b_torch = torch.randn((torch_size, torch_size), device=device, dtype=torch.float32)

    while not stop_event.is_set():
        phase_end = time.monotonic() + 5.0
        if torch is not None and a_torch is not None and b_torch is not None:
            while time.monotonic() < phase_end and not stop_event.is_set():
                result = a_torch @ b_torch
                scalar = result.sum()
                if backend == "torch_cpu_and_numpy":
                    _ = float(scalar.item())
        while time.monotonic() < phase_end + 5.0 and not stop_event.is_set():
            _ = a_numpy @ b_numpy


def _workload_stats(stop_event: threading.Event, elements: int) -> None:
    _seed_all()
    values = np.random.rand(int(elements)).astype(np.float32)
    while not stop_event.is_set():
        _ = float(values.sum())
        _ = float(values.mean())
        values[::16] += 1.0


def _run_workload(
    workload: str,
    stop_event: threading.Event,
    error_queue: queue.Queue[dict[str, str]],
    *,
    ai_backend: str,
    stats_elements: int,
) -> None:
    try:
        if workload == "BROWSER":
            _workload_browser(stop_event)
        elif workload == "PY_AI":
            _workload_ai(stop_event, ai_backend)
        elif workload == "PY_STATS":
            _workload_stats(stop_event, stats_elements)
        elif workload == "VIDEO_SW":
            _workload_video_sw(stop_event)
        else:
            raise ValueError(f"Unknown workload: {workload}")
    except BaseException as exc:
        error_queue.put(
            {
                "workload": workload,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        )
        stop_event.set()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect a continuous benign workload-transition trace on Apple hardware."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=_repo_root() / "data" / "telemetry" / "raw" / "apple_transitions",
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--hz", type=float, default=5.0)
    parser.add_argument("--probe-seconds", type=float, default=5.0)
    parser.add_argument("--dwell-seconds", type=float, default=60.0)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--workloads", nargs="+", default=list(WORKLOADS), choices=WORKLOADS)
    parser.add_argument(
        "--stats-elements",
        type=int,
        default=100_000_000,
        help="PY_STATS array length. The preserved workload uses 100,000,000 float32 values.",
    )
    parser.add_argument("--allow-non-apple", action="store_true")
    parser.add_argument(
        "--allow-browser-offline",
        action="store_true",
        help="Allow BROWSER to run without a successful network preflight. Disclose this in results.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if args.hz <= 0:
        raise ValueError("--hz must be positive")
    if args.probe_seconds <= 0:
        raise ValueError("--probe-seconds must be positive")
    if args.dwell_seconds <= 0:
        raise ValueError("--dwell-seconds must be positive")
    if args.cycles <= 0:
        raise ValueError("--cycles must be positive")
    if args.stats_elements <= 0:
        raise ValueError("--stats-elements must be positive")
    if platform.system() != "Darwin" and not args.allow_non_apple:
        raise RuntimeError(
            "This supplemental experiment is intended for the Apple platform. "
            "Use --allow-non-apple only for a collection smoke test."
        )


def _write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    repo_root: Path,
    collector_source: Path,
    workload_source: Path,
    schema: list[str],
    ai_backend: str,
    status: str,
    trace_rows: int,
    events: list[dict[str, object]],
    started_at: str,
    unavailable_fields: list[str],
    browser_network: dict[str, object],
    sample_times_s: list[float],
    error: str | None = None,
) -> None:
    sample_intervals = np.diff(np.asarray(sample_times_s, dtype=float))
    observed_sampling = {
        "sample_count": int(len(sample_times_s)),
        "elapsed_seconds": float(sample_times_s[-1]) if sample_times_s else 0.0,
        "median_interval_seconds": float(np.median(sample_intervals)) if sample_intervals.size else None,
        "p95_interval_seconds": float(np.quantile(sample_intervals, 0.95)) if sample_intervals.size else None,
        "maximum_interval_seconds": float(np.max(sample_intervals)) if sample_intervals.size else None,
    }
    payload = {
        "status": status,
        "started_at_utc": started_at,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(repo_root),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_brand": _cpu_brand(),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "protocol": {
            "workloads": list(args.workloads),
            "cycles": int(args.cycles),
            "dwell_seconds": float(args.dwell_seconds),
            "requested_hz": float(args.hz),
            "probe_seconds": float(args.probe_seconds),
            "seed": SEED,
            "continuous_collector": True,
            "labels": "scheduled benign workload phase",
            "ai_backend": ai_backend,
            "py_stats_float32_elements": int(args.stats_elements),
        },
        "trace_rows": int(trace_rows),
        "observed_sampling": observed_sampling,
        "browser_network_preflight": browser_network,
        "schema": schema,
        "unavailable_fields": unavailable_fields,
        "events": events,
        "source_files": {
            str(collector_source.relative_to(repo_root)): _sha256(collector_source),
            str(workload_source.relative_to(repo_root)): _sha256(workload_source),
            str(Path(__file__).resolve().relative_to(repo_root)): _sha256(Path(__file__).resolve()),
        },
        "error": error,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = _build_parser().parse_args()
    _validate_args(args)
    repo_root = _repo_root()
    collector, collector_source = _load_tier0_collector(repo_root)
    workload_source = (
        repo_root
        / "APPLE_DATA_GENERATION"
        / "data generation"
        / "src"
        / "dice"
        / "workloads.py"
    )
    ai_backend = _resolve_ai_backend()
    phases = [workload for _ in range(args.cycles) for workload in args.workloads]
    browser_ok, browser_detail = (True, "BROWSER not requested")
    if "BROWSER" in args.workloads:
        browser_ok, browser_detail = _browser_preflight()
        if not browser_ok and not args.allow_browser_offline:
            raise RuntimeError(
                "BROWSER network preflight failed. Restore network access and retry, or use "
                "--allow-browser-offline only if the limitation will be disclosed. "
                f"Detail: {browser_detail}"
            )

    plan = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "phases": phases,
        "requested_hz": args.hz,
        "probe_seconds": args.probe_seconds,
        "dwell_seconds": args.dwell_seconds,
        "estimated_collection_seconds": len(phases) * args.dwell_seconds,
        "ai_backend": ai_backend,
        "browser_network_preflight": {"passed": browser_ok, "detail": browser_detail},
        "py_stats_memory_gib": args.stats_elements * np.dtype(np.float32).itemsize / (1024**3),
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output_root.expanduser().resolve() / run_id
    if run_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing run directory: {run_dir}")
    run_dir.mkdir(parents=True)

    trace_path = run_dir / "transition_trace.csv"
    events_path = run_dir / "transition_events.csv"
    schema_path = run_dir / "tier0_schema.json"
    manifest_path = run_dir / "collection_manifest.json"
    started_at = datetime.now(timezone.utc).isoformat()
    interval = 1.0 / float(args.hz)

    probe_rows: list[dict[str, float]] = []
    probe_prev = collector.Prev()
    probe_count = max(2, int(round(args.probe_seconds * args.hz)))
    for _ in range(probe_count):
        sample_started = time.monotonic()
        probe_rows.append(_sample_tier0(collector, probe_prev, interval))
        time.sleep(max(0.0, interval - (time.monotonic() - sample_started)))
    schema = collector.build_schema(probe_rows)
    schema_path.write_text(
        json.dumps(
            {
                "schema": schema,
                "probe_seconds": args.probe_seconds,
                "requested_hz": args.hz,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    events: list[dict[str, object]] = []
    errors: queue.Queue[dict[str, str]] = queue.Queue()
    active_threads: list[tuple[threading.Thread, threading.Event, float, str]] = []
    trace_rows = 0
    sample_times_s: list[float] = []
    status = "running"
    failure: str | None = None
    experiment_t0_wall = time.time()
    experiment_t0_mono = time.monotonic()
    next_sample = experiment_t0_mono
    phase_index = -1
    phase_end = experiment_t0_mono
    current_workload = ""

    fieldnames = [
        "idx",
        "ts_unix_s",
        "t_rel_s",
        "phase_index",
        "cycle_index",
        "workload",
    ] + schema

    try:
        with trace_path.open("w", newline="", encoding="utf-8") as trace_handle:
            writer = csv.DictWriter(trace_handle, fieldnames=fieldnames)
            writer.writeheader()
            previous = collector.Prev()

            while phase_index + 1 < len(phases) or time.monotonic() < phase_end:
                now = time.monotonic()
                if now >= phase_end and phase_index + 1 < len(phases):
                    if active_threads:
                        active_threads[-1][1].set()
                    phase_index += 1
                    current_workload = phases[phase_index]
                    phase_started_wall = time.time()
                    phase_started_mono = time.monotonic()
                    if events:
                        events[-1].update(
                            {
                                "end_ts_unix_s": phase_started_wall,
                                "end_t_rel_s": phase_started_wall - experiment_t0_wall,
                                "end_sample_index": max(trace_rows - 1, 0),
                            }
                        )
                    stop_event = threading.Event()
                    thread = threading.Thread(
                        target=_run_workload,
                        args=(current_workload, stop_event, errors),
                        kwargs={
                            "ai_backend": ai_backend,
                            "stats_elements": args.stats_elements,
                        },
                        name=f"citadel-{current_workload}-{phase_index}",
                        daemon=True,
                    )
                    thread.start()
                    active_threads.append(
                        (thread, stop_event, phase_started_mono, current_workload)
                    )
                    phase_end = phase_started_mono + float(args.dwell_seconds)
                    events.append(
                        {
                            "phase_index": phase_index,
                            "cycle_index": phase_index // len(args.workloads),
                            "workload": current_workload,
                            "start_ts_unix_s": phase_started_wall,
                            "start_t_rel_s": phase_started_wall - experiment_t0_wall,
                            "start_sample_index": trace_rows,
                            "is_transition": phase_index > 0,
                            "end_ts_unix_s": None,
                            "end_t_rel_s": None,
                            "end_sample_index": None,
                        }
                    )
                    print(
                        f"Phase {phase_index + 1}/{len(phases)}: {current_workload} "
                        f"for {args.dwell_seconds:g} seconds",
                        flush=True,
                    )

                if not errors.empty():
                    error_record = errors.get_nowait()
                    raise RuntimeError(json.dumps(error_record))

                for thread, _, stopped_at, workload in active_threads[:-1]:
                    if thread.is_alive() and now - stopped_at > float(args.dwell_seconds) + 30.0:
                        raise RuntimeError(f"Workload thread did not stop within 30 seconds: {workload}")

                if now < next_sample:
                    time.sleep(min(next_sample - now, 0.05))
                    continue

                sample_wall = time.time()
                raw = _sample_tier0(collector, previous, interval)
                row = {name: raw.get(name, float("nan")) for name in schema}
                writer.writerow(
                    {
                        "idx": trace_rows,
                        "ts_unix_s": sample_wall,
                        "t_rel_s": sample_wall - experiment_t0_wall,
                        "phase_index": phase_index,
                        "cycle_index": phase_index // len(args.workloads),
                        "workload": current_workload,
                        **row,
                    }
                )
                trace_rows += 1
                sample_times_s.append(sample_wall - experiment_t0_wall)
                trace_handle.flush()
                next_sample += interval
                if next_sample < time.monotonic() - interval:
                    next_sample = time.monotonic()

        status = "complete"
    except KeyboardInterrupt:
        status = "interrupted"
        failure = "KeyboardInterrupt"
    except BaseException as exc:
        status = "failed"
        failure = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        if events and events[-1].get("end_ts_unix_s") is None:
            ended_wall = time.time()
            events[-1].update(
                {
                    "end_ts_unix_s": ended_wall,
                    "end_t_rel_s": ended_wall - experiment_t0_wall,
                    "end_sample_index": max(trace_rows - 1, 0),
                }
            )
        for _, stop_event, _, _ in active_threads:
            stop_event.set()
        for thread, _, _, _ in active_threads:
            thread.join(timeout=30.0)

        with events_path.open("w", newline="", encoding="utf-8") as event_handle:
            event_writer = csv.DictWriter(
                event_handle,
                fieldnames=[
                    "phase_index",
                    "cycle_index",
                    "workload",
                    "start_ts_unix_s",
                    "start_t_rel_s",
                    "start_sample_index",
                    "is_transition",
                    "end_ts_unix_s",
                    "end_t_rel_s",
                    "end_sample_index",
                ],
            )
            event_writer.writeheader()
            event_writer.writerows(events)

        _write_manifest(
            manifest_path,
            args=args,
            repo_root=repo_root,
            collector_source=collector_source,
            workload_source=workload_source,
            schema=schema,
            ai_backend=ai_backend,
            status=status,
            trace_rows=trace_rows,
            events=events,
            started_at=started_at,
            unavailable_fields=[
                field
                for field, unavailable in (
                    ("swap telemetry", getattr(collector, "_citadel_swap_unavailable", False)),
                    ("pids_count", getattr(collector, "_citadel_pids_unavailable", False)),
                    ("uptime_s", getattr(collector, "_citadel_boot_time_unavailable", False)),
                )
                if unavailable
            ],
            browser_network={"passed": browser_ok, "detail": browser_detail},
            sample_times_s=sample_times_s,
            error=failure,
        )

    print(json.dumps({"status": status, "run_dir": str(run_dir), "trace_rows": trace_rows}))
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
