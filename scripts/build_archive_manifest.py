#!/usr/bin/env python3
"""Build the deterministic SHA-256 inventory used by archive verification."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


OUTPUT_PATH = Path("reproducibility/archive_manifest.json")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_files(root: Path) -> list[str]:
    output = subprocess.check_output(["git", "ls-files"], cwd=root, text=True)
    return sorted(line for line in output.splitlines() if line and line != OUTPUT_PATH.as_posix())


def lfs_files(root: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(
        subprocess.check_output(["git", "lfs", "ls-files", "--json"], cwd=root, text=True)
    )
    return {entry["name"]: entry for entry in payload["files"]}


def scopes_for(path: str) -> list[str]:
    scopes: list[str] = []
    if not path.startswith(("data/telemetry/", "results/")):
        scopes.append("source")
    if path.startswith("data/telemetry/processed/ddr_data/"):
        scopes.extend(["core", "sensitivity"])
        if "_benign_" in Path(path).name:
            scopes.extend(["intel", "workload"])
    if path.startswith("data/telemetry/raw/apple_data/"):
        scopes.append("apple")
    if path.startswith("results/notebook_run/graph_sensitivity/"):
        scopes.extend(["core", "sensitivity"])
    if path.startswith(
        (
            "results/notebook_run/tcad_ablation/",
            "results/notebook_run/droop_adaptive_ablation/",
            "results/notebook_run/droop_adaptive_data/",
            "results/notebook_run/lifecycle_drift/",
            "results/notebook_run/fpga/",
            "results/notebook_run/workload_profiles/",
            "results/notebook_run/ets_baseline/",
        )
    ) or path == "results/notebook_run/paper_tbd_replacements.csv":
        scopes.append("core")
    if path.startswith("results/notebook_run/workload_profiles/"):
        scopes.append("workload")
    if path.startswith("results/notebook_run/apple_limited_observability/"):
        scopes.append("apple")
    if path == "results/notebook_run/rtl_sweep/rtl_resource_summary.csv":
        scopes.extend(["core", "rtl"])
    elif path.startswith("results/notebook_run/rtl_sweep/") or path.startswith("rtl/"):
        scopes.append("rtl")
    if path.startswith("results/notebook_run/intel_workload_orders/"):
        scopes.append("intel")
    if path.startswith("reproducibility/paper_results/intel/"):
        scopes.append("intel")
    if path.startswith("reproducibility/paper_results/core/"):
        scopes.append("core")
    if path.startswith("reproducibility/paper_results/sensitivity/"):
        scopes.append("sensitivity")
    if path.startswith("reproducibility/paper_results/rtl/"):
        scopes.append("rtl")
    if path.startswith("reproducibility/paper_results/apple/"):
        scopes.append("apple")
    if path == "reproducibility/paper_results/README.md":
        scopes.extend(["core", "sensitivity", "rtl", "intel", "apple"])
    if path in {
        ".python-version",
        "pyproject.toml",
        "uv.lock",
        "requirements.txt",
        "environment.yml",
        "scripts/analyze_intel_workload_orders.py",
        "scripts/build_intel_paper_evidence.py",
        "scripts/reproduce.py",
        "scripts/verify_reproducibility.py",
    }:
        scopes.append("intel")
    if path == "scripts/build_paper_result_bundles.py":
        scopes.extend(["core", "apple"])
    if path == "scripts/build_paper_sensitivity_evidence.py":
        scopes.append("sensitivity")
    if path in {
        "scripts/build_paper_rtl_evidence.py",
        "scripts/render_rtl_figure5.py",
        "scripts/reproduce_rtl.py",
    }:
        scopes.append("rtl")
    if path == "scripts/verify_paper_results.py":
        scopes.extend(["core", "sensitivity", "rtl", "intel", "apple"])
    return sorted(set(scopes))


def main() -> int:
    root = repo_root()
    lfs = lfs_files(root)
    files = []
    for relative in tracked_files(root):
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        if relative in lfs:
            entry = lfs[relative]
            sha256 = str(entry["oid"])
            size = int(entry["size"])
            storage = "git-lfs"
        else:
            sha256 = sha256_file(path)
            size = path.stat().st_size
            storage = "git"
        files.append(
            {
                "path": relative,
                "scopes": scopes_for(relative),
                "sha256": sha256,
                "size_bytes": size,
                "storage": storage,
            }
        )

    payload = {
        "schema_version": 1,
        "algorithm": "sha256",
        "description": "Deterministic inventory of every tracked source, input, and archived output. Git-LFS entries use the content OID and declared object size.",
        "file_count": len(files),
        "lfs_file_count": sum(entry["storage"] == "git-lfs" for entry in files),
        "files": files,
    }
    output = root / OUTPUT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {output} ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
