#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def default_repo_root() -> Path:
    env_hint = os.environ.get("DICE_REPO_ROOT")
    if env_hint:
        return Path(env_hint).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def main() -> int:
    repo_root = default_repo_root()
    default_dataset_root = repo_root / "data generation" / "dataset" / "ITC_M2Pro_DATA"

    parser = argparse.ArgumentParser(
        description="Validate the pinned DICE notebook environment and dataset layout."
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument("--dataset-root", type=Path, default=default_dataset_root)
    parser.add_argument("--report-path", type=Path, default=repo_root / "ci_artifacts" / "notebook_environment_report.json")
    args = parser.parse_args()

    cmd = [
        sys.executable,
        str(args.repo_root / "tools" / "check_notebook_environment.py"),
        "--repo-root",
        str(args.repo_root),
        "--dataset-root",
        str(args.dataset_root),
        "--report-path",
        str(args.report_path),
    ]
    return subprocess.run(cmd, check=False).returncode
    

if __name__ == "__main__":
    raise SystemExit(main())
