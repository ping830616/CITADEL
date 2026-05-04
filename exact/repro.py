from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import platform
import random
import subprocess
import tempfile
from importlib import metadata
from pathlib import Path
from typing import Iterable


DEFAULT_SEED = 123
DEFAULT_THREADS = 1
THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)
RUNTIME_PACKAGES = (
    "numpy",
    "pandas",
    "scikit-learn",
    "matplotlib",
    "networkx",
    "pytest",
    "jupyterlab",
    "nbformat",
    "ipykernel",
)


def find_repo_root(start: Path | None = None) -> Path:
    """Return the repository root by looking for pyproject.toml and the package dir."""
    current = Path.cwd() if start is None else Path(start).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "exact").is_dir():
            return candidate

    raise FileNotFoundError(f"Could not find repo root from {current}")


def configure_reproducibility(
    seed: int = DEFAULT_SEED,
    *,
    threads: int = DEFAULT_THREADS,
    matplotlib_backend: str | None = "Agg",
) -> dict[str, str]:
    """Set deterministic process knobs before importing numerical libraries."""
    env_updates = {"PYTHONHASHSEED": str(seed)}
    for name in THREAD_ENV_VARS:
        env_updates[name] = str(threads)
    mpl_config_dir = Path(tempfile.gettempdir()) / "exact-matplotlib"
    mpl_config_dir.mkdir(parents=True, exist_ok=True)
    env_updates["MPLCONFIGDIR"] = str(mpl_config_dir)
    if matplotlib_backend:
        env_updates["MPLBACKEND"] = matplotlib_backend

    for name, value in env_updates.items():
        os.environ[name] = value

    random.seed(seed)

    try:
        import numpy as np

        np.random.seed(seed)
    except Exception:
        pass

    return env_updates


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def _safe_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def runtime_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in RUNTIME_PACKAGES:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            continue
    return versions


def write_run_manifest(
    out_root: Path,
    *,
    repo_root: Path,
    data_root: Path,
    cfg: object,
    seed: int,
    artifact_paths: Iterable[Path] = (),
) -> Path:
    """Write a deterministic manifest with config, runtime, and file hashes."""
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    repo_root = Path(repo_root).resolve()
    data_root = Path(data_root).resolve()

    if dataclasses.is_dataclass(cfg):
        config_payload = dataclasses.asdict(cfg)
    else:
        config_payload = {"repr": repr(cfg)}

    data_files = sorted(p for p in data_root.glob("*.csv") if p.is_file())
    artifacts = [Path(path).resolve() for path in artifact_paths if Path(path).exists()]

    payload = {
        "seed": int(seed),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "git_commit": _git_commit(repo_root),
        "config": config_payload,
        "environment": {
            key: os.environ.get(key)
            for key in ("PYTHONHASHSEED", *THREAD_ENV_VARS, "MPLBACKEND", "MPLCONFIGDIR")
            if os.environ.get(key) is not None
        },
        "packages": runtime_versions(),
        "data_root": _safe_relative(data_root, repo_root),
        "data_files": [
            {
                "path": _safe_relative(path, repo_root),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in data_files
        ],
        "artifacts": [
            {
                "path": _safe_relative(path, repo_root),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in artifacts
        ],
    }

    manifest_path = out_root / "run_manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return manifest_path
