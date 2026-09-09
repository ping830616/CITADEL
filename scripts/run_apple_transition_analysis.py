#!/usr/bin/env python3
"""Execute the notebook's Apple transition analysis for one collected trace."""

from __future__ import annotations

import argparse
import json
import os
import sys
import types
from pathlib import Path


CELL_IDS = (
    "0bbebb9d",
    "3d1f98fe",
    "integrated-utilities-code",
    "e71b2ac4",
    "84fc2d6b",
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

    output.mkdir(parents=True, exist_ok=True)
    os.environ["CITADEL_APPLE_TRANSITION_TRACE"] = str(trace)
    os.environ["CITADEL_APPLE_TRANSITION_OUT"] = str(output)
    os.environ["CITADEL_APPLE_TRANSITION_CALIBRATION_CYCLES"] = str(
        args.calibration_cycles
    )

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
        for cell_id in CELL_IDS:
            source = "".join(cells[cell_id].get("source", []))
            compiled = compile(source, f"{notebook_path.name}:{cell_id}", "exec")
            exec(compiled, namespace)
    finally:
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
