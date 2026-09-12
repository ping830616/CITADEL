#!/usr/bin/env python3
"""Deterministic, headless entry point for CITADEL reviewer reproduction.

Run this launcher instead of starting a live Jupyter kernel when producing
comparison-grade results.  It fixes process-level seeds, thread counts,
timezone, locale, notebook section selection, and output isolation before a
kernel or numerical library starts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SEED = 123
THREADS = 1
CANONICAL_PYTHON = "3.11.15"
THREAD_VARIABLES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)
INTEL_WORKLOADS = (
    "dft",
    "dj",
    "dp",
    "gl",
    "gs",
    "ha",
    "ja",
    "mm",
    "ni",
    "oe",
    "pi",
    "sh",
    "tr",
)
INTEL_SETUP_PREFIXES = ("DDR4", "DDR5")
INTEL_NOTEBOOK_UTILITY_LOADER = {
    "mode": "validation-free",
    "profile": "smoke",
    "data_mode": "sample",
    "tcad_preset": "smoke",
    "seed": 123,
    "threads": 1,
    "strict_runtime": False,
    "experiment_sections_enabled": False,
}
LFS_INPUT_PATTERNS = {
    # Computational inputs only. Archived result bundles used solely as
    # comparison references live in ``LFS_REFERENCE_PATTERNS`` so a new run
    # does not need to download its predecessor unless --verify is requested.
    "smoke": ("data/telemetry/processed/ddr_data/*.csv",),
    "workload": ("data/telemetry/processed/ddr_data/*_benign_*.csv",),
    "core": (
        "data/telemetry/processed/ddr_data/*.csv",
        # Section 10 deliberately uses the archived Vivado summary as an input
        # to the deployment-passport figure. Vivado itself is reproduced by
        # the separate strict launcher.
        "results/notebook_run/rtl_sweep/rtl_resource_summary.csv",
    ),
    "sensitivity": (
        "data/telemetry/processed/ddr_data/*.csv",
        "results/notebook_run/droop_adaptive_data/*.csv",
    ),
    "apple": ("data/telemetry/raw/apple_data/**/*.csv",),
    "intel": ("data/telemetry/processed/ddr_data/*_benign_*.csv",),
    "rtl": ("results/notebook_run/rtl_sweep/**/*",),
    "all": (
        "data/telemetry/**/*.csv",
        "results/notebook_run/rtl_sweep/rtl_resource_summary.csv",
    ),
}
LFS_REFERENCE_PATTERNS = {
    "smoke": (),
    "workload": (),
    "core": (
        # Paper-facing references are compact ordinary-Git files under
        # reproducibility/paper_results/core.
    ),
    "sensitivity": (
        # The compact paper-facing reference is ordinary Git content under
        # reproducibility/paper_results/sensitivity.
    ),
    "apple": (
        # Paper-facing references are compact ordinary-Git files under
        # reproducibility/paper_results/apple.
    ),
    # The compact Intel paper reference is ordinary Git content under
    # reproducibility/paper_results/intel, not a Git-LFS result archive.
    "intel": (),
    # The Vivado launcher always validates against this preserved report set,
    # so its archive is already part of the rtl computational-input scope.
    "rtl": (),
    "all": (
        "results/**/*.csv",
        "results/**/*.json",
    ),
}
# Backward-compatible name for callers that mean generation inputs.
LFS_PATTERNS = LFS_INPUT_PATTERNS
PROFILE_SECTIONS = {
    "smoke": {1, 2, 3, 4},
    "workload": {1, 2, 3},
    "core": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 14},
    "apple": {1, 2, 11},
    "all": set(range(1, 15)),
}
PROFILE_SKIP_CELLS = {
    "smoke": {"citadel-workload-profile-analysis", "2158d272"},
    # The workload-profile cell is deliberately self-contained and consumes
    # exactly the 26 benign files; skip the general data-preparation cell that
    # loads the complete anomaly snapshot.
    "workload": {"540aa7ce"},
    "core": set(),
    "apple": set(),
    "all": set(),
}

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
NBCLIENT_LAUNCH_CODE = (
    "import nbformat,sys; from nbclient import NotebookClient; "
    "src,out,cwd=sys.argv[1:4]; nb=nbformat.read(src,as_version=4); "
    "client=NotebookClient(nb,timeout=None,kernel_name='citadel-locked',"
    "resources={'metadata':{'path':cwd}}); "
    "\ntry:\n client.execute()\nfinally:\n nbformat.write(nb,out)"
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deterministic_environment(seed: int = SEED, threads: int = THREADS) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONHASHSEED": str(seed),
            "MPLBACKEND": "Agg",
            # Do not depend on a user's home-directory Matplotlib cache. The
            # cache is execution scratch space, not a scientific input.
            "MPLCONFIGDIR": "/tmp/citadel-matplotlib",
            "TZ": "UTC",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONIOENCODING": "utf-8",
            "CITADEL_SEED": str(seed),
            "CITADEL_THREADS": str(threads),
        }
    )
    for name in THREAD_VARIABLES:
        environment[name] = str(threads)
    return environment


def notebook_strict_runtime_setting(allow_runtime_mismatch: bool) -> str:
    """Translate the wrapper escape hatch into the notebook's runtime gate."""
    return "0" if allow_runtime_mismatch else "1"


def git_output(root: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=root, text=True).strip()


def git_status(root: Path) -> list[str]:
    output = git_output(root, "status", "--porcelain")
    return output.splitlines() if output else []


def assert_repository_snapshot_unchanged(
    root: Path,
    *,
    repository_commit: str,
    status_at_start: list[str],
) -> dict[str, Any]:
    """Fail a completed run if its Git source/input snapshot changed in flight."""
    commit_at_finish = git_output(root, "rev-parse", "HEAD")
    status_at_finish = git_status(root)
    unchanged = (
        commit_at_finish == repository_commit
        and status_at_finish == status_at_start
    )
    payload = {
        "repository_commit_at_finish": commit_at_finish,
        "git_status_at_finish": status_at_finish,
        "repository_snapshot_unchanged_during_run": unchanged,
    }
    if not unchanged:
        raise RuntimeError(
            "Repository commit or worktree status changed during execution; "
            "the partial output is not valid comparison evidence."
        )
    return payload


def direct_requirements(root: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if value.count("==") != 1:
            raise ValueError(f"Every direct requirement must be exactly pinned: {value!r}")
        package, version = value.split("==", 1)
        expected[package.strip()] = version.strip()
    return expected


def runtime_audit(root: Path) -> dict[str, Any]:
    packages = {}
    mismatches = []
    for package, expected in direct_requirements(root).items():
        try:
            observed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            observed = None
        packages[package] = {"expected": expected, "observed": observed}
        if observed != expected:
            mismatches.append(f"{package}: expected {expected}, observed {observed}")
    if platform.python_version() != CANONICAL_PYTHON:
        mismatches.insert(
            0,
            f"python: expected {CANONICAL_PYTHON}, observed {platform.python_version()}",
        )
    return {
        "python_executable": sys.executable,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": packages,
        "mismatches": mismatches,
    }


def numerical_runtime_audit(
    environment: dict[str, str], *, root: Path | None = None
) -> dict[str, Any]:
    """Inspect NumPy/BLAS in a fresh process with the fixed thread environment."""
    code = (
        "import json,numpy as np; from threadpoolctl import threadpool_info; "
        "np.dot(np.ones((2,2)),np.ones((2,2))); "
        "print(json.dumps({'numpy_version':np.__version__,"
        "'numpy_configuration':np.__config__.show(mode='dicts'),"
        "'threadpools':threadpool_info()},sort_keys=True))"
    )
    output = subprocess.check_output(
        [sys.executable, "-c", code],
        cwd=root or repo_root(),
        env=environment,
        text=True,
    )
    return json.loads(output)


def intel_input_paths(root: Path) -> list[Path]:
    data_root = root / "data" / "telemetry" / "processed" / "ddr_data"
    return [
        data_root / f"{prefix}_benign_{workload}.csv"
        for prefix in INTEL_SETUP_PREFIXES
        for workload in INTEL_WORKLOADS
    ]


def intel_source_paths(root: Path) -> list[Path]:
    """Sources whose exact bytes define the wrapped Intel analysis."""
    return [
        root / "scripts" / "reproduce.py",
        root / "scripts" / "analyze_intel_workload_orders.py",
        root / "notebooks" / "exact_tcad_all_experiments.ipynb",
        root / "data" / "external_sources.json",
    ]


def file_inventory(root: Path, paths: list[Path]) -> list[dict[str, Any]]:
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Required input files are missing: {missing}")
    pointers = [path.relative_to(root).as_posix() for path in paths if is_lfs_pointer(path)]
    if pointers:
        raise RuntimeError(f"Required Git LFS objects are pointer stubs: {pointers}")
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in paths
    ]


def is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(64).startswith(b"version https://git-lfs.github.com/spec/v1")
    except OSError:
        return False


def expand_patterns(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    paths: set[Path] = set()
    for pattern in patterns:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(paths)


def lfs_patterns(scope: str, *, include_reference: bool = False) -> tuple[str, ...]:
    patterns = list(LFS_INPUT_PATTERNS[scope])
    if include_reference:
        patterns.extend(LFS_REFERENCE_PATTERNS[scope])
    # Preserve declaration order while avoiding duplicate downloads/audits.
    return tuple(dict.fromkeys(patterns))


def lfs_audit(
    root: Path,
    scope: str | None,
    *,
    include_reference: bool = False,
) -> dict[str, Any]:
    if scope is None:
        return {
            "scope": None,
            "include_reference": False,
            "patterns": [],
            "matched_files": 0,
            "pointer_files": [],
            "status": "NOT_REQUIRED",
        }
    patterns = lfs_patterns(scope, include_reference=include_reference)
    paths = expand_patterns(root, patterns)
    pointers = [path.relative_to(root).as_posix() for path in paths if is_lfs_pointer(path)]
    return {
        "scope": scope,
        "include_reference": bool(include_reference),
        "patterns": list(patterns),
        "matched_files": len(paths),
        "pointer_files": pointers,
        "status": "PASS" if paths and not pointers else "FAIL",
    }


def run_preflight(
    root: Path,
    *,
    scope: str | None,
    allow_dirty: bool,
    allow_runtime_mismatch: bool,
    include_reference: bool = False,
) -> dict[str, Any]:
    status = git_status(root)
    runtime = runtime_audit(root)
    lfs = lfs_audit(root, scope, include_reference=include_reference)
    failures = []
    if status and not allow_dirty:
        failures.append("The Git checkout is dirty; use a clean clone or pass --allow-dirty for development only.")
    if runtime["mismatches"] and not allow_runtime_mismatch:
        failures.extend(runtime["mismatches"])
    if lfs["status"] not in {"PASS", "NOT_REQUIRED"}:
        if not lfs["matched_files"]:
            failures.append(f"No files matched the {scope!r} Git LFS scope.")
        if lfs["pointer_files"]:
            failures.append(
                f"{len(lfs['pointer_files'])} required Git LFS objects are pointer stubs; run the fetch-lfs command."
            )
    payload = {
        "schema_version": 1,
        "status": "PASS" if not failures else "FAIL",
        "repository_commit": git_output(root, "rev-parse", "HEAD"),
        "git_status": status,
        "runtime": runtime,
        "lfs": lfs,
        "failures": failures,
    }
    if failures:
        raise RuntimeError(json.dumps(payload, indent=2))
    return payload


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(
            "Run IDs must start with a letter or digit and contain only letters, "
            "digits, '.', '_', or '-'."
        )
    return run_id


def notebook_lfs_scope(profile: str, data_mode: str) -> str | None:
    if profile == "smoke":
        return None if data_mode == "sample" else "smoke"
    if profile == "apple":
        return "apple"
    if profile == "workload":
        return "workload"
    if profile == "all":
        return "all"
    return "core"


def validate_notebook_request(
    *,
    profile: str,
    preset: str,
    data_mode: str,
    verify: bool,
) -> None:
    if profile == "workload" and (data_mode != "real" or preset != "smoke"):
        raise ValueError(
            "The workload profile always reads the preserved benign telemetry and "
            "requires --data-mode real --preset smoke."
        )
    if verify and profile == "smoke":
        raise ValueError(
            "--verify is not valid for the smoke grid because this snapshot does "
            "not contain a scientifically comparable archived smoke reference. "
            "Use --repeat to compare two isolated runs."
        )
    if verify and profile == "workload":
        raise ValueError(
            "--verify is not valid for the workload profile because this snapshot "
            "does not contain a scientifically comparable archived reference. "
            "Use --repeat to compare two isolated runs."
        )
    if verify and profile == "all":
        raise ValueError(
            "--profile all is a development notebook sweep, not an all-paper-results "
            "verification command. Run `scripts/reproduce.py verify-paper --scope all` "
            "for the compact evidence audit, then use the named reproduction commands."
        )
    if verify and profile == "core" and (preset != "full" or data_mode != "real"):
        raise ValueError(
            "Archive verification for the core profile requires --preset full "
            "and --data-mode real. Use --repeat for development presets or sample data."
        )


def ensure_new_run_root(root: Path, run_id: str) -> Path:
    validated = validate_run_id(run_id)
    run_root = root / "results" / "reproduced" / validated
    if run_root.exists():
        raise FileExistsError(
            f"Run directory already exists: {run_root}. Choose a new --run-id so stale "
            "artifacts cannot be mixed into a reproduction run."
        )
    run_root.mkdir(parents=True)
    return run_root


def assert_planned_run_roots_available(root: Path, run_id: str, *, repeat: bool) -> None:
    """Reject stale primary or repeat destinations before expensive execution."""
    run_ids = [validate_run_id(run_id)]
    if repeat:
        run_ids.append(validate_run_id(f"{run_id}-repeat"))
    existing = [root / "results" / "reproduced" / item for item in run_ids]
    existing = [path for path in existing if path.exists()]
    if existing:
        rendered = ", ".join(str(path) for path in existing)
        raise FileExistsError(
            f"Planned run directory already exists: {rendered}. Choose a new --run-id "
            "so stale artifacts cannot be mixed into a reproduction run."
        )


def nbclient_command(source: Path, destination: Path, cwd: Path) -> list[str]:
    """Return the small, separately testable notebook-execution command."""
    return [
        sys.executable,
        "-c",
        NBCLIENT_LAUNCH_CODE,
        str(source),
        str(destination),
        str(cwd),
    ]


def write_locked_kernelspec(run_root: Path) -> Path:
    """Create an isolated Jupyter kernelspec bound to this exact interpreter."""
    jupyter_root = run_root / "jupyter"
    spec_root = jupyter_root / "kernels" / "citadel-locked"
    spec_root.mkdir(parents=True)
    payload = {
        "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "CITADEL locked Python",
        "language": "python",
        "metadata": {"debugger": False},
    }
    (spec_root / "kernel.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return jupyter_root


def skipped_cell_source(profile: str, cell_id: str, section: int | None) -> list[str]:
    return [
        f"# Skipped by scripts/reproduce.py profile={profile}; cell={cell_id}; section={section}\n",
        "pass\n",
    ]


def prepare_notebook(source: Path, destination: Path, profile: str) -> dict[str, Any]:
    notebook = json.loads(source.read_text(encoding="utf-8"))
    selected_sections = PROFILE_SECTIONS[profile]
    explicit_skips = PROFILE_SKIP_CELLS[profile]
    current_section: int | None = None
    kept: list[str] = []
    skipped: list[str] = []
    section_pattern = re.compile(r"^##\s+(\d+)\.")

    for cell in notebook["cells"]:
        source_text = "".join(cell.get("source", []))
        if cell.get("cell_type") == "markdown":
            first_line = source_text.splitlines()[0] if source_text.splitlines() else ""
            match = section_pattern.match(first_line)
            if match:
                current_section = int(match.group(1))
            continue
        if cell.get("cell_type") != "code":
            continue
        cell_id = str(cell.get("id", "unknown"))
        keep = current_section is None or current_section in selected_sections
        if cell_id in explicit_skips:
            keep = False
        if keep:
            kept.append(cell_id)
        else:
            cell["source"] = skipped_cell_source(profile, cell_id, current_section)
            skipped.append(cell_id)
        cell["execution_count"] = None
        cell["outputs"] = []

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"kept_cell_ids": kept, "skipped_cell_ids": skipped}


def execute_notebook(
    root: Path,
    *,
    profile: str,
    preset: str,
    data_mode: str,
    run_id: str,
    allow_dirty: bool,
    allow_runtime_mismatch: bool,
    include_reference: bool = False,
) -> Path:
    scope = notebook_lfs_scope(profile, data_mode)
    preflight = run_preflight(
        root,
        scope=scope,
        allow_dirty=allow_dirty,
        allow_runtime_mismatch=allow_runtime_mismatch,
        include_reference=include_reference,
    )
    run_root = ensure_new_run_root(root, run_id)
    result_root = run_root / "notebook_run"
    prepared_path = run_root / "prepared_notebook.ipynb"
    executed_path = run_root / "executed_notebook.ipynb"
    receipt_path = run_root / "run_receipt.json"
    selection = prepare_notebook(
        root / "notebooks" / "exact_tcad_all_experiments.ipynb",
        prepared_path,
        profile,
    )
    environment = deterministic_environment()
    environment.update(
        {
            "CITADEL_RESULTS_ROOT": result_root.relative_to(root).as_posix(),
            "CITADEL_SAMPLE_ROOT": (run_root / "sample_data").relative_to(root).as_posix(),
            "CITADEL_PROFILE": profile,
            "CITADEL_DATA_MODE": data_mode,
            "CITADEL_TCAD_PRESET": preset,
            "CITADEL_RUN_LIFECYCLE": "1" if profile in {"core", "all"} else "0",
            "CITADEL_RUN_APPLE_OBSERVABILITY": "1" if profile in {"apple", "all"} else "0",
            "CITADEL_RUN_INTEL_WORKLOAD_ORDERS": "1" if profile == "all" else "0",
            "CITADEL_STRICT_RUNTIME": notebook_strict_runtime_setting(
                allow_runtime_mismatch
            ),
        }
    )
    environment["JUPYTER_PATH"] = str(write_locked_kernelspec(run_root))
    temporary_root = run_root / "tmp"
    temporary_root.mkdir()
    environment["TMPDIR"] = str(temporary_root)
    started = datetime.now(timezone.utc).isoformat()
    clock = time.perf_counter()
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "profile": profile,
        "preset": preset,
        "data_mode": data_mode,
        "seed": SEED,
        "threads": THREADS,
        "started_at_utc": started,
        "repository_commit": preflight["repository_commit"],
        "source_notebook_sha256": sha256_file(root / "notebooks" / "exact_tcad_all_experiments.ipynb"),
        "kernel_python": sys.executable,
        "result_root": result_root.relative_to(root).as_posix(),
        "prepared_notebook": prepared_path.relative_to(root).as_posix(),
        "executed_notebook": executed_path.relative_to(root).as_posix(),
        "cell_selection": selection,
        "preflight": preflight,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Executing {profile} notebook profile; outputs: {result_root}", flush=True)

    command = nbclient_command(prepared_path, executed_path, root)
    try:
        subprocess.run(command, cwd=root, env=environment, check=True)
        paper_profile = profile if profile in {"core", "apple", "all"} else None
        if paper_profile is not None:
            paper_output_root = result_root / "paper_results"
            subprocess.run(
                [
                    sys.executable,
                    str(root / "scripts" / "build_paper_result_bundles.py"),
                    "--repo-root",
                    str(root),
                    "--source-root",
                    str(result_root),
                    "--output-root",
                    str(paper_output_root),
                    "--profile",
                    paper_profile,
                ],
                cwd=root,
                env=environment,
                check=True,
            )
            receipt["paper_result_bundle"] = paper_output_root.relative_to(root).as_posix()
        receipt.update(
            assert_repository_snapshot_unchanged(
                root,
                repository_commit=str(preflight["repository_commit"]),
                status_at_start=list(preflight["git_status"]),
            )
        )
        if sha256_file(root / "notebooks" / "exact_tcad_all_experiments.ipynb") != receipt["source_notebook_sha256"]:
            raise RuntimeError(
                "Notebook source changed during execution; the partial output is not valid comparison evidence."
            )
    except BaseException as exc:
        receipt["status"] = "failed"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    else:
        receipt["status"] = "complete"
    finally:
        receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        receipt["runtime_seconds"] = time.perf_counter() - clock
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Completed notebook profile {profile}: {executed_path}")
    return result_root


def compare_roots(root: Path, reference: Path, candidate: Path, profile: str, report: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "verify_reproducibility.py"),
            "--repo-root",
            str(root),
            "compare",
            "--reference-root",
            str(reference),
            "--candidate-root",
            str(candidate),
            "--profile",
            profile,
            "--report",
            str(report),
        ],
        cwd=root,
        env=deterministic_environment(),
        check=True,
    )


def png_validation(path: Path, *, minimum_width: int = 300, minimum_height: int = 300) -> dict[str, Any]:
    """Decode a plotted result and reject tiny or visually uniform placeholders."""
    result: dict[str, Any] = {
        "path": str(path),
        "decoded": False,
        "width_px": 0,
        "height_px": 0,
        "nonuniform": False,
        "status": "FAIL",
    }
    if not path.is_file() or path.stat().st_size <= 8:
        return result
    try:
        from PIL import Image, ImageStat

        with Image.open(path) as opened:
            if opened.format != "PNG":
                return result
            opened.verify()
        with Image.open(path) as opened:
            width, height = opened.size
            sample = opened.convert("L")
            sample.thumbnail((256, 256))
            variance = float(ImageStat.Stat(sample).var[0])
        result.update(
            {
                "decoded": True,
                "width_px": int(width),
                "height_px": int(height),
                "nonuniform": variance > 1.0,
                "sample_variance": variance,
            }
        )
        result["status"] = (
            "PASS"
            if width >= minimum_width
            and height >= minimum_height
            and result["nonuniform"]
            else "FAIL"
        )
    except (OSError, ValueError):
        pass
    return result


def intel_paper_projection(result_root: Path) -> Path:
    """Copy only Fig. 7 scientific inputs into a comparison-sized root."""
    source = result_root / "intel_workload_orders"
    projection = result_root.parent / "paper_result_projection"
    destination = projection / "intel_workload_orders"
    destination.mkdir(parents=True)
    for filename in (
        "intel_workload_order_run_results.csv",
        "intel_workload_order_summary.csv",
        "fig_intel_workload_order_variation.png",
    ):
        source_path = source / filename
        if not source_path.is_file():
            raise FileNotFoundError(f"Missing generated Figure 7 artifact: {source_path}")
        (destination / filename).write_bytes(source_path.read_bytes())
    return projection


def verify_intel_paper_claims(
    reference_root: Path,
    candidate_root: Path,
    report_path: Path,
) -> None:
    """Trace the displayed Fig. 7 statement to regenerated summary cells."""
    claims_path = reference_root / "figure7_claims.json"
    claims = json.loads(claims_path.read_text(encoding="utf-8"))
    summary_path = (
        candidate_root
        / "intel_workload_orders"
        / "intel_workload_order_summary.csv"
    )
    with summary_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    details = []
    for claim in claims["claims"]:
        matches = {
            row["metric"]: row
            for row in rows
            if row["setup"] == claim["setup"]
            and row["decision_rule"] == claim["decision_rule"]
            and row["metric"] in {
                "overall_benign_fpr",
                "boundary_block_fpr",
                "within_phase_fpr",
            }
        }
        if set(matches) != {
            "overall_benign_fpr",
            "boundary_block_fpr",
            "within_phase_fpr",
        }:
            details.append(
                {
                    "setup": claim["setup"],
                    "status": "SUMMARY_ROW_COUNT_MISMATCH",
                    "observed_metrics": sorted(matches),
                }
            )
            continue
        row = matches["overall_benign_fpr"]
        boundary = matches["boundary_block_fpr"]
        later = matches["within_phase_fpr"]
        decimals = int(claim["display_decimal_places"])
        displayed_mean = f"{100.0 * float(row['mean']):.{decimals}f}"
        displayed_sd = f"{100.0 * float(row['sample_sd']):.{decimals}f}"
        displayed_boundary = f"{100.0 * float(boundary['mean']):.{decimals}f}"
        displayed_later = f"{100.0 * float(later['mean']):.{decimals}f}"
        status = (
            "PASS"
            if displayed_mean == claim["paper_mean_percent"]
            and displayed_sd == claim["paper_sample_sd_percentage_points"]
            and displayed_boundary == claim["paper_boundary_mean_percent"]
            and displayed_later == claim["paper_later_mean_percent"]
            else "CLAIM_MISMATCH"
        )
        details.append(
            {
                "setup": claim["setup"],
                "displayed_mean_percent": displayed_mean,
                "displayed_sample_sd_percentage_points": displayed_sd,
                "displayed_boundary_mean_percent": displayed_boundary,
                "displayed_later_mean_percent": displayed_later,
                "paper_mean_percent": claim["paper_mean_percent"],
                "paper_sample_sd_percentage_points": claim[
                    "paper_sample_sd_percentage_points"
                ],
                "paper_boundary_mean_percent": claim["paper_boundary_mean_percent"],
                "paper_later_mean_percent": claim["paper_later_mean_percent"],
                "status": status,
            }
        )
    figure_path = (
        candidate_root
        / "intel_workload_orders"
        / "fig_intel_workload_order_variation.png"
    )
    figure_validation = png_validation(
        figure_path,
        minimum_width=900,
        minimum_height=1800,
    )
    figure_validation["portrait"] = (
        figure_validation["height_px"] > figure_validation["width_px"]
    )
    figure_validation["layout"] = (
        "three_vertical_panels"
        if figure_validation["status"] == "PASS" and figure_validation["portrait"]
        else "invalid"
    )
    figure_valid = (
        figure_validation["status"] == "PASS"
        and figure_validation["layout"] == "three_vertical_panels"
    )
    failures = sum(item["status"] != "PASS" for item in details) + (not figure_valid)
    payload = {
        "schema_version": 1,
        "check": "figure7_paper_claims",
        "paper_item": claims["paper_item"],
        "details": details,
        "figure_nonempty_png": figure_valid,
        "figure_validation": figure_validation,
        "failures": int(failures),
        "status": "PASS" if not failures else "FAIL",
    }
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True), flush=True)
    if failures:
        raise RuntimeError("Regenerated Figure 7 evidence does not match the paper claims")


def command_preflight(args: argparse.Namespace) -> int:
    payload = run_preflight(
        args.repo_root.resolve(),
        scope=args.scope,
        allow_dirty=args.allow_dirty,
        allow_runtime_mismatch=args.allow_runtime_mismatch,
        include_reference=args.include_reference,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_fetch(args: argparse.Namespace) -> int:
    root = args.repo_root.resolve()
    patterns = lfs_patterns(args.scope, include_reference=args.include_reference)
    command = ["git", "lfs", "pull", f"--include={','.join(patterns)}", "--exclude="]
    print("Fetching only the requested Git LFS scope:")
    print(" ".join(command))
    subprocess.run(command, cwd=root, check=True)
    audit = lfs_audit(root, args.scope, include_reference=args.include_reference)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit["status"] == "PASS" else 1


def command_notebook(args: argparse.Namespace) -> int:
    root = args.repo_root.resolve()
    run_id = args.run_id or f"{args.profile}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    validate_notebook_request(
        profile=args.profile,
        preset=args.preset,
        data_mode=args.data_mode,
        verify=args.verify,
    )
    assert_planned_run_roots_available(root, run_id, repeat=args.repeat)
    first = execute_notebook(
        root,
        profile=args.profile,
        preset=args.preset,
        data_mode=args.data_mode,
        run_id=run_id,
        allow_dirty=args.allow_dirty,
        allow_runtime_mismatch=args.allow_runtime_mismatch,
        include_reference=args.verify,
    )
    if args.verify:
        if args.profile in {"core", "apple"}:
            compare_roots(
                root,
                root / "reproducibility" / "paper_results",
                first / "paper_results",
                f"{args.profile}-paper",
                first.parent / "paper_result_comparison.json",
            )
        else:
            compare_roots(
                root,
                root / "results" / "notebook_run",
                first,
                args.profile,
                first.parent / "archive_comparison.json",
            )
    if args.repeat:
        second = execute_notebook(
            root,
            profile=args.profile,
            preset=args.preset,
            data_mode=args.data_mode,
            run_id=f"{run_id}-repeat",
            allow_dirty=args.allow_dirty,
            allow_runtime_mismatch=args.allow_runtime_mismatch,
            include_reference=False,
        )
        if args.profile in {"core", "apple"}:
            compare_roots(
                root,
                first / "paper_results",
                second / "paper_results",
                f"{args.profile}-paper",
                second.parent / "paper_result_repeat_comparison.json",
            )
        else:
            compare_roots(
                root,
                first,
                second,
                args.profile,
                second.parent / "repeat_comparison.json",
            )
    return 0


def execute_sensitivity(
    root: Path,
    *,
    run_id: str,
    allow_dirty: bool,
    allow_runtime_mismatch: bool,
    include_reference: bool = False,
) -> Path:
    run_preflight(
        root,
        scope="sensitivity",
        allow_dirty=allow_dirty,
        allow_runtime_mismatch=allow_runtime_mismatch,
        include_reference=include_reference,
    )
    run_root = ensure_new_run_root(root, run_id)
    output = run_root / "notebook_run" / "graph_sensitivity"
    temporary_root = run_root / "tmp"
    temporary_root.mkdir()
    environment = deterministic_environment()
    environment["TMPDIR"] = str(temporary_root)
    environment["MPLCONFIGDIR"] = str(temporary_root / "citadel-matplotlib")
    command = [
        sys.executable,
        str(root / "scripts" / "run_graph_sensitivity.py"),
        "--repo-root",
        str(root),
        "--output-root",
        str(output),
        "--droop-data-root",
        str(root / "results" / "notebook_run" / "droop_adaptive_data"),
    ]
    if allow_dirty:
        command.append("--allow-dirty")
    if allow_runtime_mismatch:
        command.append("--allow-version-mismatch")
    subprocess.run(command, cwd=root, env=environment, check=True)
    paper_output = run_root / "paper_results" / "sensitivity"
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "build_paper_sensitivity_evidence.py"),
            "--source-root",
            str(output),
            "--output-root",
            str(paper_output),
        ],
        cwd=root,
        env=environment,
        check=True,
    )
    return output.parent


def command_sensitivity(args: argparse.Namespace) -> int:
    root = args.repo_root.resolve()
    run_id = args.run_id or f"sensitivity-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    assert_planned_run_roots_available(root, run_id, repeat=args.repeat)
    first = execute_sensitivity(
        root,
        run_id=run_id,
        allow_dirty=args.allow_dirty,
        allow_runtime_mismatch=args.allow_runtime_mismatch,
        include_reference=False,
    )
    if args.verify:
        compare_roots(
            root,
            root / "reproducibility" / "paper_results",
            first.parent / "paper_results",
            "sensitivity-paper",
            first.parent / "paper_result_comparison.json",
        )
    if args.repeat:
        second = execute_sensitivity(
            root,
            run_id=f"{run_id}-repeat",
            allow_dirty=args.allow_dirty,
            allow_runtime_mismatch=args.allow_runtime_mismatch,
            include_reference=False,
        )
        compare_roots(
            root,
            first,
            second,
            "sensitivity",
            second.parent / "repeat_comparison.json",
        )
    return 0


def execute_intel_orders(
    root: Path,
    *,
    run_id: str,
    allow_dirty: bool,
    allow_runtime_mismatch: bool,
    include_reference: bool = False,
) -> Path:
    """Run the frozen Intel workload-order protocol in a new isolated root."""
    preflight = run_preflight(
        root,
        scope="intel",
        allow_dirty=allow_dirty,
        allow_runtime_mismatch=allow_runtime_mismatch,
        include_reference=include_reference,
    )
    environment = deterministic_environment()
    input_inventory = file_inventory(root, intel_input_paths(root))
    environment_inventory = file_inventory(
        root,
        [
            root / ".python-version",
            root / "pyproject.toml",
            root / "uv.lock",
            root / "requirements.txt",
            root / "environment.yml",
        ],
    )
    analyzer_path = root / "scripts" / "analyze_intel_workload_orders.py"
    source_paths = intel_source_paths(root)
    source_inventory = file_inventory(root, source_paths)
    run_root = ensure_new_run_root(root, run_id)
    result_root = run_root / "notebook_run"
    output = result_root / "intel_workload_orders"
    receipt_path = run_root / "run_receipt.json"
    temporary_root = run_root / "tmp"
    temporary_root.mkdir()
    environment["TMPDIR"] = str(temporary_root)
    environment["MPLCONFIGDIR"] = str(temporary_root / "citadel-matplotlib")
    numerical_runtime = numerical_runtime_audit(environment, root=root)
    configuration = {
        "setups": ["A", "B"],
        "replicates": 10,
        "recording_block_rows": 1000,
        "calibration_cycles": 2,
        "evaluation_cycles": 3,
        "top_k": 8,
        "window_size": 50,
        "aggregation": "mean",
        "lambda_res": 0.5,
        "weight_mode": "uniform",
        "persistence_blocks": 2,
        "boundary_window_blocks": 1,
        "eta": 0.01,
        "reference_alpha": 0.05,
        "correlation_threshold": 0.35,
        "seed": SEED,
        "bootstrap_resamples": 10000,
    }
    command = [
        sys.executable,
        str(analyzer_path),
        "--output",
        str(output),
        "--setups",
        *configuration["setups"],
        "--replicates",
        str(configuration["replicates"]),
        "--recording-block-rows",
        str(configuration["recording_block_rows"]),
        "--calibration-cycles",
        str(configuration["calibration_cycles"]),
        "--evaluation-cycles",
        str(configuration["evaluation_cycles"]),
        "--top-k",
        str(configuration["top_k"]),
        "--window-size",
        str(configuration["window_size"]),
        "--seed",
        str(configuration["seed"]),
        "--bootstrap-resamples",
        str(configuration["bootstrap_resamples"]),
    ]
    started = datetime.now(timezone.utc).isoformat()
    clock = time.perf_counter()
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "experiment": "intel_workload_orders",
        "started_at_utc": started,
        "repository_commit": preflight["repository_commit"],
        "clean_checkout_at_start": not bool(preflight["git_status"]),
        "result_root": result_root.relative_to(root).as_posix(),
        "configuration": configuration,
        "deterministic_environment": {
            name: environment[name]
            for name in (
                "PYTHONHASHSEED",
                "TZ",
                "LANG",
                "LC_ALL",
                "MPLBACKEND",
                "MPLCONFIGDIR",
                "TMPDIR",
                "CITADEL_SEED",
                "CITADEL_THREADS",
                *THREAD_VARIABLES,
            )
        },
        "sources": source_inventory,
        "inputs": input_inventory,
        "environment_files": environment_inventory,
        "runtime": preflight["runtime"],
        "numerical_runtime": numerical_runtime,
        "preflight": preflight,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Executing Intel workload-order protocol; outputs: {output}", flush=True)
    try:
        subprocess.run(command, cwd=root, env=environment, check=True)
        receipt.update(
            assert_repository_snapshot_unchanged(
                root,
                repository_commit=str(preflight["repository_commit"]),
                status_at_start=list(preflight["git_status"]),
            )
        )
        if file_inventory(root, intel_input_paths(root)) != input_inventory:
            raise RuntimeError(
                "Intel telemetry inputs changed during execution; the partial output is not valid evidence."
            )
        if file_inventory(
            root,
            [
                root / ".python-version",
                root / "pyproject.toml",
                root / "uv.lock",
                root / "requirements.txt",
                root / "environment.yml",
            ],
        ) != environment_inventory:
            raise RuntimeError(
                "Environment specifications changed during execution; the partial output is not valid evidence."
            )
        if file_inventory(root, source_paths) != source_inventory:
            raise RuntimeError(
                "Intel launcher, analyzer, notebook, or external-source registry changed "
                "during execution; the partial output is not valid evidence."
            )
        analyzer_manifest = output / "run_manifest.json"
        if not analyzer_manifest.is_file():
            raise RuntimeError(f"Analyzer did not write its required manifest: {analyzer_manifest}")
        analyzer_payload = json.loads(analyzer_manifest.read_text(encoding="utf-8"))
        if analyzer_payload.get("status") != "complete":
            raise RuntimeError("Analyzer manifest does not report status=complete")
        if analyzer_payload.get("notebook_utility_loader") != INTEL_NOTEBOOK_UTILITY_LOADER:
            raise RuntimeError(
                "Analyzer manifest does not record the expected validation-free "
                "notebook utility-loader mode"
            )
        receipt["notebook_utility_loader"] = analyzer_payload["notebook_utility_loader"]
        receipt["analyzer_run_manifest"] = {
            "path": analyzer_manifest.relative_to(root).as_posix(),
            "sha256": sha256_file(analyzer_manifest),
        }
        receipt["status"] = "complete"
    except BaseException as exc:
        receipt["status"] = "failed"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        receipt["runtime_seconds"] = time.perf_counter() - clock
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return result_root


def command_intel_orders(args: argparse.Namespace) -> int:
    root = args.repo_root.resolve()
    run_id = args.run_id or f"intel-orders-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    archived = root / "reproducibility" / "paper_results" / "intel"
    if args.verify and not (archived / "evidence_manifest.json").is_file():
        raise FileNotFoundError(
            "--verify requires the committed Figure 7 reference bundle at "
            f"{archived}; this snapshot does not contain one."
        )
    assert_planned_run_roots_available(root, run_id, repeat=args.repeat)
    first = execute_intel_orders(
        root,
        run_id=run_id,
        allow_dirty=args.allow_dirty,
        allow_runtime_mismatch=args.allow_runtime_mismatch,
        include_reference=args.verify,
    )
    if args.verify:
        projection = intel_paper_projection(first)
        compare_roots(
            root,
            archived,
            projection,
            "intel-paper",
            first.parent / "figure7_archive_comparison.json",
        )
        verify_intel_paper_claims(
            archived,
            projection,
            first.parent / "figure7_claim_verification.json",
        )
    if args.repeat:
        second = execute_intel_orders(
            root,
            run_id=f"{run_id}-repeat",
            allow_dirty=args.allow_dirty,
            allow_runtime_mismatch=args.allow_runtime_mismatch,
            include_reference=False,
        )
        compare_roots(
            root,
            first,
            second,
            "intel-orders",
            second.parent / "repeat_comparison.json",
        )
    return 0


def command_verify_archive(args: argparse.Namespace) -> int:
    root = args.repo_root.resolve()
    command = [
        sys.executable,
        str(root / "scripts" / "verify_reproducibility.py"),
        "--repo-root",
        str(root),
        "archive",
        "--scope",
        args.scope,
    ]
    if args.require_materialized:
        command.append("--require-materialized")
    return subprocess.run(command, cwd=root, check=False).returncode


def command_verify_paper(args: argparse.Namespace) -> int:
    """Audit compact manuscript evidence without implying a fresh experiment run."""

    root = args.repo_root.resolve()
    command = [
        sys.executable,
        str(root / "scripts" / "verify_paper_results.py"),
        "--repo-root",
        str(root),
    ]
    if args.scope != "all":
        command.extend(["--family", args.scope])
    if args.output is not None:
        command.extend(["--output", str(args.output.resolve())])
    return subprocess.run(command, cwd=root, check=False).returncode


def common_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--allow-runtime-mismatch", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=repo_root())
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="Check runtime, Git state, and scoped LFS inputs.")
    preflight.add_argument("--scope", choices=tuple(LFS_PATTERNS), default="core")
    preflight.add_argument("--allow-dirty", action="store_true")
    preflight.add_argument("--allow-runtime-mismatch", action="store_true")
    preflight.add_argument(
        "--include-reference",
        action="store_true",
        help="Also preflight archived comparison outputs for this scope.",
    )
    preflight.set_defaults(func=command_preflight)

    fetch = subparsers.add_parser("fetch-lfs", help="Materialize only one experiment's LFS inputs.")
    fetch.add_argument("--scope", choices=tuple(LFS_PATTERNS), default="core")
    fetch.add_argument(
        "--include-reference",
        action="store_true",
        help="Also fetch archived result objects needed by --verify.",
    )
    fetch.set_defaults(func=command_fetch)

    notebook = subparsers.add_parser("notebook", help="Execute a deterministic notebook profile headlessly.")
    notebook.add_argument("--profile", choices=tuple(PROFILE_SECTIONS), default="core")
    notebook.add_argument("--preset", choices=("smoke", "balanced", "full"), default="full")
    notebook.add_argument("--data-mode", choices=("real", "sample"), default="real")
    notebook.add_argument("--verify", action="store_true", help="Compare generated tables with the archive.")
    notebook.add_argument("--repeat", action="store_true", help="Execute a second isolated run and compare it.")
    common_run_options(notebook)
    notebook.set_defaults(func=command_notebook)

    sensitivity = subparsers.add_parser("sensitivity", help="Regenerate the frozen graph/ranking study.")
    sensitivity.add_argument("--verify", action="store_true")
    sensitivity.add_argument("--repeat", action="store_true", help="Execute a second isolated run and compare it.")
    common_run_options(sensitivity)
    sensitivity.set_defaults(func=command_sensitivity)

    intel = subparsers.add_parser("intel-orders", help="Regenerate the preserved-data workload-order study.")
    intel.add_argument("--verify", action="store_true", help="Compare with a committed Intel archive, when present.")
    intel.add_argument("--repeat", action="store_true", help="Execute a second isolated run and compare it.")
    common_run_options(intel)
    intel.set_defaults(func=command_intel_orders)

    archive = subparsers.add_parser("verify-archive", help="Validate archived sources, inputs, and outputs.")
    archive.add_argument("--scope", choices=("source", "workload", "core", "sensitivity", "apple", "intel", "rtl", "all"), default="all")
    archive.add_argument("--require-materialized", action="store_true")
    archive.set_defaults(func=command_verify_archive)

    paper = subparsers.add_parser(
        "verify-paper",
        help="Audit compact paper-result coverage, integrity, and manuscript claims.",
    )
    paper.add_argument(
        "--scope",
        choices=("core", "sensitivity", "rtl", "intel", "apple", "all"),
        default="all",
    )
    paper.add_argument(
        "--output",
        type=Path,
        help="Optionally save the machine-readable audit JSON outside the repository.",
    )
    paper.set_defaults(func=command_verify_paper)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
