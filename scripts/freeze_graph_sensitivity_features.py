#!/usr/bin/env python3
"""Maintainer utility to freeze sensitivity feature universes as protocol input.

The runtime sensitivity analysis reads the generated JSON, never the archived
result tables.  This utility exists so the one-time migration from the legacy
DSE rank tables is explicit and hash-auditable.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "configs" / "graph_sensitivity_feature_universes.json"
SOURCES = {
    "A_DROOP": ROOT / "results/notebook_run/droop_adaptive_ablation/p0_99/causal/SETUP_A_feature_ranks.csv",
    "A_RH": ROOT / "results/notebook_run/tcad_ablation/causal/SETUP_A_feature_ranks.csv",
    "B_DROOP": ROOT / "results/notebook_run/droop_adaptive_ablation/p0_99/causal/SETUP_B_feature_ranks.csv",
    "B_SPECTRE": ROOT / "results/notebook_run/tcad_ablation/causal/SETUP_B_feature_ranks.csv",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def feature_list(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "feature" not in reader.fieldnames:
            raise ValueError(f"Missing feature column: {path}")
        values = sorted(str(row["feature"]) for row in reader)
    if not values or len(values) != len(set(values)):
        raise ValueError(f"Feature universe must be nonempty and unique: {path}")
    return values


def main() -> int:
    cases = {}
    sources = {}
    for case_id, path in SOURCES.items():
        if path.read_bytes().startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise RuntimeError(f"Materialize the legacy migration source first: {path}")
        values = feature_list(path)
        cases[case_id] = values
        sources[case_id] = {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(path),
            "feature_count": len(values),
        }
    payload = {
        "schema_version": 1,
        "purpose": "Frozen candidate feature universes used as independent graph-sensitivity protocol inputs.",
        "migration_note": "Created once from the legacy DSE causal rank universes; runtime generation does not read those result files.",
        "legacy_migration_sources": sources,
        "cases": cases,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} with {sum(len(values) for values in cases.values())} case-features")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
