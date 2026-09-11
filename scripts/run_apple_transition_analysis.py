#!/usr/bin/env python3
"""Execute the notebook's Apple transition analysis for one collected trace."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
import types
from pathlib import Path


CELL_IDS = (
    "0bbebb9d",
    "3d1f98fe",
    "integrated-utilities-code",
    "e71b2ac4",
    "84fc2d6b",
)
NOTEBOOK_ENVIRONMENT_KEYS = (
    "CITADEL_SEED",
    "CITADEL_THREADS",
    "CITADEL_STRICT_RUNTIME",
    "CITADEL_PROFILE",
    "CITADEL_DATA_MODE",
    "CITADEL_TCAD_PRESET",
    "CITADEL_SAMPLE_ROWS",
    "CITADEL_RESULTS_ROOT",
    "CITADEL_SAMPLE_ROOT",
    "CITADEL_RUN_INTEL_WORKLOAD_ORDERS",
    "CITADEL_RUN_APPLE_OBSERVABILITY",
    "CITADEL_RUN_LIFECYCLE",
    "CITADEL_APPLE_TRANSITION_TRACE",
    "CITADEL_APPLE_TRANSITION_OUT",
    "CITADEL_APPLE_TRANSITION_CALIBRATION_CYCLES",
    "PYTHONHASHSEED",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "MPLBACKEND",
    "MPLCONFIGDIR",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the exact notebook analysis for one Apple transition trace."
    )
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--calibration-cycles", type=int, default=2)
    return parser


def _create_fresh_output(output: Path) -> None:
    """Reserve a new per-run output without mixing it with stale analysis."""
    if output.exists():
        raise FileExistsError(
            f"Output directory already exists: {output}. Choose a new path, or use "
            "the campaign aggregator's --skip-per-run-analysis option to reuse a "
            "previously completed per-run bundle intentionally."
        )
    output.mkdir(parents=True)


@contextlib.contextmanager
def _isolated_notebook_utility_environment(
    repo_root: Path,
    *,
    trace: Path,
    output: Path,
    calibration_cycles: int,
):
    """Load notebook utilities without validating unrelated archived datasets."""
    previous = {name: os.environ.get(name) for name in NOTEBOOK_ENVIRONMENT_KEYS}
    previous_cwd = Path.cwd()
    scratch_parent = repo_root / "results" / "reproduced"
    scratch_parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(
            prefix="apple-transition-utility-", dir=scratch_parent
        ) as temporary:
            scratch = Path(temporary)
            os.environ.update(
                {
                    "CITADEL_SEED": "123",
                    "CITADEL_THREADS": "1",
                    "CITADEL_STRICT_RUNTIME": "0",
                    "CITADEL_PROFILE": "smoke",
                    "CITADEL_DATA_MODE": "sample",
                    "CITADEL_TCAD_PRESET": "smoke",
                    "CITADEL_SAMPLE_ROWS": "600",
                    "CITADEL_RESULTS_ROOT": str(scratch / "notebook_run"),
                    "CITADEL_SAMPLE_ROOT": str(scratch / "sample_data"),
                    "CITADEL_RUN_INTEL_WORKLOAD_ORDERS": "0",
                    "CITADEL_RUN_APPLE_OBSERVABILITY": "0",
                    "CITADEL_RUN_LIFECYCLE": "0",
                    "CITADEL_APPLE_TRANSITION_TRACE": str(trace),
                    "CITADEL_APPLE_TRANSITION_OUT": str(output),
                    "CITADEL_APPLE_TRANSITION_CALIBRATION_CYCLES": str(
                        calibration_cycles
                    ),
                }
            )
            yield
    finally:
        os.chdir(previous_cwd)
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main() -> int:
    args = _parser().parse_args()
    if args.calibration_cycles < 1:
        raise ValueError("--calibration-cycles must be positive")

    repo_root = _repo_root()
    trace = args.trace.expanduser().resolve()
    output = args.output.expanduser().resolve()
    manifest = trace.with_name("collection_manifest.json")
    if not trace.is_file() or not manifest.is_file():
        raise FileNotFoundError(f"Trace or collection manifest is missing: {trace}")
    if json.loads(manifest.read_text(encoding="utf-8")).get("status") != "complete":
        raise RuntimeError(f"Collection manifest is not complete: {manifest}")

    _create_fresh_output(output)

    notebook_path = repo_root / "notebooks" / "exact_tcad_all_experiments.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    cells = {cell.get("id"): cell for cell in notebook["cells"]}
    missing = [cell_id for cell_id in CELL_IDS if cell_id not in cells]
    if missing:
        raise RuntimeError(f"Required notebook cells are missing: {missing}")

    module_name = "_citadel_apple_transition_notebook"
    module = types.ModuleType(module_name)
    module.__file__ = str(notebook_path)
    sys.modules[module_name] = module
    namespace = module.__dict__
    shared_progress_log = repo_root / "results" / "notebook_run" / "notebook_progress.log"
    saved_progress_log = (
        shared_progress_log.read_bytes() if shared_progress_log.is_file() else None
    )
    try:
        with _isolated_notebook_utility_environment(
            repo_root,
            trace=trace,
            output=output,
            calibration_cycles=args.calibration_cycles,
        ):
            for cell_id in CELL_IDS:
                source = "".join(cells[cell_id].get("source", []))
                compiled = compile(source, f"{notebook_path.name}:{cell_id}", "exec")
                exec(compiled, namespace)
    finally:
        sys.modules.pop(module_name, None)
        if saved_progress_log is not None:
            shared_progress_log.write_bytes(saved_progress_log)
        elif shared_progress_log.exists():
            shared_progress_log.unlink()

    summary_path = output / "transition_rule_summary.csv"
    if not summary_path.is_file():
        raise RuntimeError(f"Analysis did not create the expected summary: {summary_path}")
    print(
        json.dumps(
            {
                "status": "complete",
                "trace": str(trace),
                "output": str(output),
                "summary": str(summary_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
