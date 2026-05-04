from __future__ import annotations

import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_integrated_notebook_namespace() -> dict:
    """Load the notebook-owned experiment functions for tests.

    The repo intentionally keeps experiment orchestration in one notebook.
    Tests execute that notebook utility cell instead of importing a separate
    experiment module.
    """
    from exact.repro import configure_reproducibility

    notebook_path = REPO_ROOT / "notebooks" / "exact_tcad_all_experiments.ipynb"
    nb = json.loads(notebook_path.read_text(encoding="utf-8"))
    utility_cell = next(
        cell for cell in nb["cells"]
        if cell.get("cell_type") == "code"
        and "class ETS2026Config" in "".join(cell.get("source", []))
        and "class TCAD2026Config" in "".join(cell.get("source", []))
    )
    source = "".join(utility_cell["source"])

    module_name = "__citadel_integrated_notebook__"
    module = types.ModuleType(module_name)
    sys.modules[module_name] = module
    ns = module.__dict__
    ns.update({
        "__name__": module_name,
        "REPO_ROOT": REPO_ROOT,
        "DATA_SOURCE_CONFIG": REPO_ROOT / "data" / "external_sources.json",
        "SEED": 123,
        "THREADS": 1,
        "SAMPLE_ROWS": 600,
        "TCAD_PRESET": "smoke",
        "RESULTS_ROOT": REPO_ROOT / "results" / "notebook_test",
        "Path": Path,
        "json": json,
        "os": os,
        "pd": pd,
        "subprocess": subprocess,
        "configure_reproducibility": configure_reproducibility,
    })
    exec(compile(source, str(notebook_path), "exec"), ns)
    return ns
