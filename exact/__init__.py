"""CITADEL/EXACT causal telemetry package.

This package preserves the portable EXACT implementation and adds the
CITADEL journal-extension workflow for hardware-aware SLM experiments.

Key ideas (see docs/draft):
  * Benign-only calibration (mean/std) for telemetry normalization.
  * Causal structure learning / feature ranking (offline).
  * Fixed-point friendly on-device scoring via CINTAS.
  * CITADEL design-space sweeps, hardware-cost summaries, and drift checks.

"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

for _thread_env_var in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ.setdefault(_thread_env_var, "1")
os.environ.setdefault("PYTHONHASHSEED", "123")
os.environ.setdefault("MPLBACKEND", "Agg")
_mpl_config_dir = Path(tempfile.gettempdir()) / "exact-matplotlib"
_mpl_config_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_config_dir))

__version__ = "0.1.0"

from .io import load_telemetry_for_setup, load_telemetry_two_setups
from .preprocessing import clean_and_debias_telemetry, get_feature_columns
from .cintas import CINTASModel, fit_cintas_from_benign
from .repro import DEFAULT_SEED, configure_reproducibility, find_repo_root
from .sample_data import create_sample_dataset

__all__ = [
    "__version__",
    "DEFAULT_SEED",
    "load_telemetry_for_setup",
    "load_telemetry_two_setups",
    "clean_and_debias_telemetry",
    "get_feature_columns",
    "CINTASModel",
    "fit_cintas_from_benign",
    "configure_reproducibility",
    "find_repo_root",
    "create_sample_dataset",
]
