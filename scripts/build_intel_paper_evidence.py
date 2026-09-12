#!/usr/bin/env python3
"""Promote a clean, repeated Intel workload-order run into Fig. 7 evidence.

This maintainer utility deliberately archives only the two scientific tables
that drive Fig. 7, the rendered figure, the paper-claim audit, and compact
provenance.  The complete per-block run remains reproducible but is not part of
the paper-facing reference bundle.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


SOURCE_SUBDIR = Path("notebook_run/intel_workload_orders")
REFERENCE_SUBDIR = Path("intel_workload_orders")
SCIENTIFIC_FILES = (
    "intel_workload_order_run_results.csv",
    "intel_workload_order_summary.csv",
)
FIGURE_FILE = "fig_intel_workload_order_variation.png"
ANALYZER_MANIFEST_FILE = "run_manifest.json"
REPORTED_CLAIMS = {
    "A": {
        "overall_mean_percent": 0.58,
        "overall_sample_sd_percentage_points": 0.82,
        "boundary_mean_percent": 0.26,
        "later_mean_percent": 0.68,
    },
    "B": {
        "overall_mean_percent": 0.83,
        "overall_sample_sd_percentage_points": 1.00,
        "boundary_mean_percent": 0.51,
        "later_mean_percent": 0.94,
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_facts(path: Path) -> dict[str, Any]:
    """Decode a PNG and record the layout facts required by paper Figure 7."""

    from PIL import Image, ImageStat

    with Image.open(path) as opened:
        require(opened.format == "PNG", f"Figure is not a PNG: {path}")
        opened.verify()
    with Image.open(path) as opened:
        width, height = opened.size
        sample = opened.convert("L")
        sample.thumbnail((256, 256))
        variance = float(ImageStat.Stat(sample).var[0])
    return {
        "decoded_png": True,
        "width_px": int(width),
        "height_px": int(height),
        "nonuniform": variance > 1.0,
        "layout": "three_vertical_panels" if height > width else "not_vertical",
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def copy_csv_with_lf(source: Path, destination: Path) -> None:
    """Copy a CSV while making the tracked text representation platform-neutral."""

    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows(rows)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def validate_receipt(receipt: dict[str, Any], label: str) -> None:
    require(receipt.get("schema_version") == 1, f"{label}: unsupported receipt schema")
    require(receipt.get("status") == "complete", f"{label}: run did not complete")
    require(receipt.get("experiment") == "intel_workload_orders", f"{label}: wrong experiment")
    require(receipt.get("clean_checkout_at_start") is True, f"{label}: checkout was dirty")
    require(
        receipt.get("repository_snapshot_unchanged_during_run") is True,
        f"{label}: repository changed during the run",
    )
    require(receipt.get("git_status_at_finish") == [], f"{label}: checkout was dirty at finish")
    require(not receipt.get("runtime", {}).get("mismatches"), f"{label}: runtime mismatch")
    require(len(receipt.get("inputs", [])) == 26, f"{label}: expected 26 Intel inputs")


def portable_runtime(receipt: dict[str, Any]) -> dict[str, Any]:
    runtime = dict(receipt["runtime"])
    runtime.pop("python_executable", None)
    environment = {
        key: value
        for key, value in receipt["deterministic_environment"].items()
        if key not in {"MPLCONFIGDIR", "TMPDIR"}
    }
    numerical = dict(receipt["numerical_runtime"])
    return {
        "locked_runtime": runtime,
        "deterministic_environment": environment,
        "numerical_runtime": numerical,
    }


def paper_protocol(run_manifest_path: Path, run_results_path: Path) -> dict[str, Any]:
    """Project the exact Section V-I protocol from one completed analyzer run."""

    run_manifest = read_json(run_manifest_path)
    config = run_manifest.get("config")
    require(isinstance(config, dict), "Analyzer run manifest has no config object")
    with run_results_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    current = [row for row in rows if row.get("decision_rule") == "current"]
    require(current, "Intel run results contain no current-rule rows")

    setup_replicates = {
        setup: sorted(
            {
                int(row["replicate_index"])
                for row in current
                if row.get("setup") == setup
            }
        )
        for setup in ("A", "B")
    }
    require(
        all(indices == list(range(1, 11)) for indices in setup_replicates.values()),
        "Section V-I requires ten current-rule replicates for each setup",
    )
    calibration_counts = {int(row["calibration_block_count"]) for row in current}
    evaluation_counts = {int(row["n_blocks"]) for row in current}
    threshold_ranks = {int(row["calibration_threshold_rank"]) for row in current}
    threshold_rules = {row["threshold_rule"] for row in current}
    require(calibration_counts == {104}, "Expected 104 calibration blocks per replicate")
    require(evaluation_counts == {156}, "Expected 156 evaluation blocks per replicate")
    require(threshold_ranks == {104}, "Finite-sample threshold must use calibration rank 104")
    require(
        threshold_rules == {"finite_sample_upper_rank_with_strict_exceedance"},
        "Expected the finite-sample upper-rank rule with strict exceedance",
    )

    protocol = {
        "setups": list(config["setups"]),
        "selected_features": int(config["top_k"]),
        "block_length": int(config["window_size"]),
        "aggregation": str(config["aggregation"]),
        "weighting": str(config["weight_mode"]),
        "score_mixture": float(config["lambda_res"]),
        "replicates_per_setup": 10,
        "calibration_blocks_per_replicate": 104,
        "evaluation_blocks_per_replicate": 156,
        "calibration_threshold_rank": 104,
        "threshold_rule": "finite_sample_upper_rank_with_strict_exceedance",
        "persistence_blocks": int(config["persistence_blocks"]),
    }
    require(
        protocol
        == {
            "setups": ["A", "B"],
            "selected_features": 8,
            "block_length": 50,
            "aggregation": "mean",
            "weighting": "uniform",
            "score_mixture": 0.5,
            "replicates_per_setup": 10,
            "calibration_blocks_per_replicate": 104,
            "evaluation_blocks_per_replicate": 156,
            "calibration_threshold_rank": 104,
            "threshold_rule": "finite_sample_upper_rank_with_strict_exceedance",
            "persistence_blocks": 2,
        },
        "Analyzer run does not match the Section V-I protocol",
    )
    return protocol


def claim_audit(summary_path: Path) -> dict[str, Any]:
    with summary_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    claims: list[dict[str, Any]] = []
    for setup, reported in REPORTED_CLAIMS.items():
        by_metric = {
            row["metric"]: row
            for row in rows
            if row["setup"] == setup and row["decision_rule"] == "current"
        }
        required_metrics = {
            "overall_benign_fpr",
            "boundary_block_fpr",
            "within_phase_fpr",
        }
        require(
            required_metrics.issubset(by_metric),
            f"Setup {setup}: missing one or more current-rule Figure 7 rows",
        )
        overall = by_metric["overall_benign_fpr"]
        boundary = by_metric["boundary_block_fpr"]
        later = by_metric["within_phase_fpr"]
        observed_mean = 100.0 * float(overall["mean"])
        observed_sd = 100.0 * float(overall["sample_sd"])
        observed_boundary = 100.0 * float(boundary["mean"])
        observed_later = 100.0 * float(later["mean"])
        displayed_mean = round(observed_mean, 2)
        displayed_sd = round(observed_sd, 2)
        displayed_boundary = round(observed_boundary, 2)
        displayed_later = round(observed_later, 2)
        mean_matches = displayed_mean == reported["overall_mean_percent"]
        sd_matches = displayed_sd == reported["overall_sample_sd_percentage_points"]
        boundary_matches = displayed_boundary == reported["boundary_mean_percent"]
        later_matches = displayed_later == reported["later_mean_percent"]
        claims.append(
            {
                "setup": setup,
                "decision_rule": "current",
                "metrics": [
                    "overall_benign_fpr",
                    "boundary_block_fpr",
                    "within_phase_fpr",
                ],
                "n_recording_block_replicates": int(overall["n_recording_block_replicates"]),
                "observed_mean_fraction": float(overall["mean"]),
                "observed_sample_sd_fraction": float(overall["sample_sd"]),
                "observed_boundary_mean_fraction": float(boundary["mean"]),
                "observed_later_mean_fraction": float(later["mean"]),
                "observed_mean_percent": observed_mean,
                "observed_sample_sd_percentage_points": observed_sd,
                "observed_boundary_mean_percent": observed_boundary,
                "observed_later_mean_percent": observed_later,
                "display_decimal_places": 2,
                "displayed_mean_percent": f"{displayed_mean:.2f}",
                "displayed_sample_sd_percentage_points": f"{displayed_sd:.2f}",
                "displayed_boundary_mean_percent": f"{displayed_boundary:.2f}",
                "displayed_later_mean_percent": f"{displayed_later:.2f}",
                "paper_mean_percent": f"{reported['overall_mean_percent']:.2f}",
                "paper_sample_sd_percentage_points": (
                    f"{reported['overall_sample_sd_percentage_points']:.2f}"
                ),
                "paper_boundary_mean_percent": f"{reported['boundary_mean_percent']:.2f}",
                "paper_later_mean_percent": f"{reported['later_mean_percent']:.2f}",
                "matches_paper_at_reported_precision": (
                    mean_matches and sd_matches and boundary_matches and later_matches
                ),
            }
        )
    return {
        "schema_version": 1,
        "paper_item": "Figure 7 and its accompanying Section V-I numerical statement",
        "calculation_basis": (
            "Arithmetic mean and sample standard deviation across ten nonoverlapping "
            "recording-block replicates for the current decision rule."
        ),
        "interpretation_boundary": (
            "Constructed workload-order boundaries use separately recorded benign files; "
            "they do not measure a physical switch transient."
        ),
        "claims": claims,
        "status": (
            "PASS"
            if all(item["matches_paper_at_reported_precision"] for item in claims)
            else "FAIL"
        ),
    }


def build_bundle(primary_root: Path, repeat_root: Path, output_root: Path) -> None:
    require(not output_root.exists(), f"Output already exists: {output_root}")
    primary_receipt = read_json(primary_root / "run_receipt.json")
    repeat_receipt = read_json(repeat_root / "run_receipt.json")
    validate_receipt(primary_receipt, "primary")
    validate_receipt(repeat_receipt, "repeat")
    for field in (
        "repository_commit",
        "configuration",
        "inputs",
        "sources",
        "environment_files",
        "runtime",
        "notebook_utility_loader",
    ):
        require(primary_receipt[field] == repeat_receipt[field], f"Run receipts differ: {field}")

    comparison_path = repeat_root / "repeat_comparison.json"
    comparison = read_json(comparison_path)
    require(comparison.get("status") == "PASS", "Repeated-run comparison did not pass")
    require(comparison.get("verification_coverage") == "COMPLETE", "Comparison is partial")
    require(comparison.get("failures") == 0, "Comparison contains failures")
    require(comparison.get("unverified_files") == 0, "Comparison left files unverified")

    primary_source = primary_root / SOURCE_SUBDIR
    repeat_source = repeat_root / SOURCE_SUBDIR
    primary_manifest_path = primary_source / ANALYZER_MANIFEST_FILE
    repeat_manifest_path = repeat_source / ANALYZER_MANIFEST_FILE
    for label, receipt, manifest_path in (
        ("primary", primary_receipt, primary_manifest_path),
        ("repeat", repeat_receipt, repeat_manifest_path),
    ):
        require(manifest_path.is_file(), f"Missing {label} analyzer run manifest")
        require(
            sha256_file(manifest_path) == receipt["analyzer_run_manifest"]["sha256"],
            f"{label}: analyzer run-manifest hash differs from its receipt",
        )
    for filename in (*SCIENTIFIC_FILES, FIGURE_FILE):
        require((primary_source / filename).is_file(), f"Missing primary artifact: {filename}")
        require((repeat_source / filename).is_file(), f"Missing repeated artifact: {filename}")
    for filename in SCIENTIFIC_FILES:
        require(
            sha256_file(primary_source / filename) == sha256_file(repeat_source / filename),
            f"Repeated scientific table differs byte-for-byte: {filename}",
        )

    primary_protocol = paper_protocol(
        primary_manifest_path,
        primary_source / SCIENTIFIC_FILES[0],
    )
    repeat_protocol = paper_protocol(
        repeat_manifest_path,
        repeat_source / SCIENTIFIC_FILES[0],
    )
    require(primary_protocol == repeat_protocol, "Repeated-run protocols differ")
    primary_figure_facts = png_facts(primary_source / FIGURE_FILE)
    repeat_figure_facts = png_facts(repeat_source / FIGURE_FILE)
    for label, facts in (("primary", primary_figure_facts), ("repeat", repeat_figure_facts)):
        require(facts["nonuniform"] is True, f"{label}: Figure 7 raster is uniform")
        require(
            facts["layout"] == "three_vertical_panels"
            and facts["height_px"] >= 1800
            and facts["width_px"] >= 900,
            f"{label}: Figure 7 is not the manuscript's three-panel vertical layout",
        )

    output_data = output_root / REFERENCE_SUBDIR
    output_data.mkdir(parents=True)
    for filename in SCIENTIFIC_FILES:
        copy_csv_with_lf(primary_source / filename, output_data / filename)
    shutil.copy2(primary_source / FIGURE_FILE, output_data / FIGURE_FILE)

    provenance = output_root / "provenance"
    provenance.mkdir()
    provenance_sources = {
        "primary_run_receipt.json": primary_root / "run_receipt.json",
        "repeat_run_receipt.json": repeat_root / "run_receipt.json",
        "primary_analyzer_manifest.json": primary_manifest_path,
        "repeat_analyzer_manifest.json": repeat_manifest_path,
    }
    for filename, source in provenance_sources.items():
        shutil.copy2(source, provenance / filename)

    claims = claim_audit(output_data / "intel_workload_order_summary.csv")
    require(claims["status"] == "PASS", "Figure 7 values do not match the paper")
    claims_path = output_root / "figure7_claims.json"
    claims_path.write_text(json.dumps(claims, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    repeat_verification = {
        "schema_version": 1,
        "check": comparison["check"],
        "profile": comparison["profile"],
        "status": comparison["status"],
        "verification_coverage": comparison["verification_coverage"],
        "compared_files": comparison["compared_files"],
        "failures": comparison["failures"],
        "unverified_files": comparison["unverified_files"],
        "relative_tolerance": comparison["relative_tolerance"],
        "absolute_tolerance": comparison["absolute_tolerance"],
    }
    repeat_path = output_root / "repeat_verification.json"
    repeat_path.write_text(
        json.dumps(repeat_verification, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    archived_paths = [
        output_data / SCIENTIFIC_FILES[0],
        output_data / SCIENTIFIC_FILES[1],
        output_data / FIGURE_FILE,
        claims_path,
        repeat_path,
        *(provenance / filename for filename in provenance_sources),
    ]
    manifest = {
        "schema_version": 1,
        "status": "COMPLETE_CLEAN_REPEAT_VERIFIED",
        "paper_items": ["Figure 7", "Section V-I numerical statement"],
        "source_commit": primary_receipt["repository_commit"],
        "clean_run_evidence": {
            "primary": {
                "started_at_utc": primary_receipt["started_at_utc"],
                "finished_at_utc": primary_receipt["finished_at_utc"],
                "clean_checkout_at_start": primary_receipt["clean_checkout_at_start"],
                "repository_snapshot_unchanged_during_run": primary_receipt[
                    "repository_snapshot_unchanged_during_run"
                ],
                "git_status_at_finish": primary_receipt["git_status_at_finish"],
                "analyzer_run_manifest_sha256": primary_receipt["analyzer_run_manifest"][
                    "sha256"
                ],
            },
            "repeat": {
                "started_at_utc": repeat_receipt["started_at_utc"],
                "finished_at_utc": repeat_receipt["finished_at_utc"],
                "clean_checkout_at_start": repeat_receipt["clean_checkout_at_start"],
                "repository_snapshot_unchanged_during_run": repeat_receipt[
                    "repository_snapshot_unchanged_during_run"
                ],
                "git_status_at_finish": repeat_receipt["git_status_at_finish"],
                "analyzer_run_manifest_sha256": repeat_receipt["analyzer_run_manifest"][
                    "sha256"
                ],
            },
        },
        "configuration": primary_receipt["configuration"],
        "paper_protocol": primary_protocol,
        "runtime": portable_runtime(primary_receipt),
        "environment_files": primary_receipt["environment_files"],
        "sources": primary_receipt["sources"],
        "inputs": primary_receipt["inputs"],
        "repeat_verification": repeat_verification,
        "claim_audit": {
            "path": "figure7_claims.json",
            "sha256": sha256_file(claims_path),
            "status": claims["status"],
        },
        "archived_artifacts": [
            {
                "path": path.relative_to(output_root).as_posix(),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in archived_paths
        ],
        "figure_validation": {
            "path": f"{REFERENCE_SUBDIR.as_posix()}/{FIGURE_FILE}",
            "nonempty": (output_data / FIGURE_FILE).stat().st_size > 0,
            "png_signature_valid": (output_data / FIGURE_FILE).read_bytes().startswith(
                b"\x89PNG\r\n\x1a\n"
            ),
            **primary_figure_facts,
            "repeat_figure": repeat_figure_facts,
            "comparison_policy": (
                "Raster bytes are archived for inspection; regenerated scientific CSVs "
                "are the cross-machine comparison target."
            ),
        },
    }
    (output_root / "evidence_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--primary-run-root", type=Path, required=True)
    result.add_argument("--repeat-run-root", type=Path, required=True)
    result.add_argument("--output-root", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    build_bundle(
        args.primary_run_root.resolve(),
        args.repeat_run_root.resolve(),
        args.output_root.resolve(),
    )
    print(f"Wrote clean Figure 7 evidence: {args.output_root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
