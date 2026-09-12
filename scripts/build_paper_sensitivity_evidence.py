#!/usr/bin/env python3
"""Build the compact paper-facing evidence for Section V-D.

The source archive is a completed clean run of the graph-parameter and
ranking-term sensitivity experiment.  This utility validates that archive,
independently recomputes the reported extrema and largest MCC reductions, and
writes a small ordinary-Git bundle.  It does not rerun the experiment and does
not claim an independent repeated run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable


REPOSITORY = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = (
    REPOSITORY / "results" / "notebook_run" / "graph_sensitivity"
)
DEFAULT_OUTPUT_ROOT = (
    REPOSITORY / "reproducibility" / "paper_results" / "sensitivity"
)
GENERATOR_VERSION = "1.1.0"

EXPECTED_ARCHIVE_FILES = {
    "README.md",
    "graph_sensitivity_claims.json",
    "graph_sensitivity_feature_ranks.csv",
    "graph_sensitivity_fold_results.csv",
    "graph_sensitivity_graph_edges.csv",
    "graph_sensitivity_selected_features.csv",
    "graph_sensitivity_summary.csv",
    "protocol.json",
    "selected_operating_points.json",
}
OUTPUT_FILES = (
    "section_vd_sensitivity_ranges.csv",
    "section_vd_ranking_reductions.csv",
    "section_vd_stability_threshold_invariance.csv",
    "section_vd_claims.json",
    "evidence_manifest.json",
)
CASE_ORDER = ("A_DROOP", "A_RH", "B_DROOP", "B_SPECTRE")
FAMILY_ORDER = ("graph_parameter", "ranking_term")
METRIC_RULES = {
    "mcc": {
        "unit": "fraction",
        "scale": 1.0,
        "display_decimal_places": 3,
    },
    "fpr": {
        "unit": "percent",
        "scale": 100.0,
        "display_decimal_places": 2,
    },
    "feature_jaccard": {
        "unit": "percent",
        "scale": 100.0,
        "display_decimal_places": 1,
    },
}
PAPER_RANGE_TARGETS = {
    "graph_parameter": {
        "mcc": ("0.940", "0.992"),
        "fpr": ("0.77", "1.71"),
        "feature_jaccard": ("37.9", "100.0"),
    },
    "ranking_term": {
        "mcc": ("0.798", "0.992"),
        "fpr": ("0.77", "1.64"),
        "feature_jaccard": ("53.8", "100.0"),
    },
}
MEMBERSHIP_RULES = {
    "graph_parameter": "All five unique graph configurations, including the baseline.",
    "ranking_term": (
        "The four term-removal variants; the baseline is retained only as a reference."
    ),
}
PAPER_REDUCTION_TARGETS = {
    "A_DROOP": "remove_centrality",
    "A_RH": "remove_alignment",
}
STABILITY_DECISION_METRICS = {
    "mcc": {
        "meaning": "Matthews correlation coefficient",
        "source_unit": "fraction",
        "reported_unit": "fraction",
        "reported_scale": 1.0,
        "reported_decimal_places": 3,
    },
    "fpr": {
        "meaning": "benign false-positive rate",
        "source_unit": "fraction",
        "reported_unit": "percent",
        "reported_scale": 100.0,
        "reported_decimal_places": 2,
    },
}
STABILITY_RELATIVE_TOLERANCE = 0.0
STABILITY_ABSOLUTE_TOLERANCE = 1e-15
SOURCE_ROLES = {
    "README.md": "human-readable source-archive summary",
    "graph_sensitivity_claims.json": "archived machine-readable claim audit",
    "graph_sensitivity_feature_ranks.csv": "complete feature ranks and ranking terms",
    "graph_sensitivity_fold_results.csv": "fold- and workload-level metric records",
    "graph_sensitivity_graph_edges.csv": "retained-edge and graph-fallback audit",
    "graph_sensitivity_selected_features.csv": "selected-feature membership records",
    "graph_sensitivity_summary.csv": "source rows for the paper-facing calculations",
    "protocol.json": "frozen one-at-a-time sensitivity protocol",
    "run_manifest.json": "clean-run provenance and source/input/output hashes",
    "selected_operating_points.json": "four frozen operating points",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    fields: Iterable[str],
    rows: Iterable[dict[str, object]],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def display(value: float, decimal_places: int) -> str:
    return f"{value:.{decimal_places}f}"


def validate_source_archive(source_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path = source_root / "run_manifest.json"
    claims_path = source_root / "graph_sensitivity_claims.json"
    require(manifest_path.is_file(), f"Missing source run manifest: {manifest_path}")
    require(claims_path.is_file(), f"Missing source claim audit: {claims_path}")
    manifest = read_json(manifest_path)
    claims = read_json(claims_path)

    require(manifest.get("schema_version") == 1, "Unsupported source manifest schema")
    require(manifest.get("repository_commit"), "Source commit is missing")
    require(
        manifest.get("repository_commit_at_finish") == manifest["repository_commit"],
        "Repository commit changed during the archived run",
    )
    require(manifest.get("git_dirty_at_start") is False, "Archived run started dirty")
    require(manifest.get("git_status_at_start") == [], "Archived run start was dirty")
    require(manifest.get("git_status_at_finish") == [], "Archived run finish was dirty")
    require(
        manifest.get("source_and_inputs_unchanged_during_run") is True,
        "Sources or inputs changed during the archived run",
    )
    require(
        manifest.get("archival_provenance_status") == "PASS",
        "Archived provenance did not pass",
    )
    require(manifest.get("claim_status") == "PASS", "Archived claim audit did not pass")
    require(
        manifest.get("draft_claims_match_at_reported_precision") is True,
        "Archived values do not match the paper at reported precision",
    )
    require(manifest.get("seed") == 123, "Unexpected base seed")
    require(manifest.get("threads") == 1, "Archived run was not single-threaded")
    require(
        manifest.get("python_hash_seed_at_process_start") == "123",
        "Archived Python hash seed is not 123",
    )
    require(
        manifest.get("runtime_versions", {}).get("mismatches") == {},
        "Archived runtime differs from the locked runtime",
    )

    require(claims.get("schema_version") == 1, "Unsupported source claim schema")
    for key in (
        "archival_evidence_accepted",
        "draft_claims_match_at_reported_precision",
        "all_baseline_validations_pass",
        "all_top_k_boundary_ties_resolved",
        "no_graph_fallback_used",
        "complete_case_set",
    ):
        require(claims.get(key) is True, f"Archived claim gate failed: {key}")
    require(claims.get("archival_provenance_status") == "PASS", "Claim provenance failed")
    require(claims.get("status") == "PASS", "Archived claim status failed")
    require(claims.get("observed_variant_row_count") == 40, "Expected 40 variants")
    require(claims.get("expected_variant_row_count") == 40, "Claim contract is not 40 variants")

    output_records = manifest.get("output_files", [])
    by_name = {Path(record["path"]).name: record for record in output_records}
    require(set(by_name) == EXPECTED_ARCHIVE_FILES, "Unexpected source archive file inventory")
    for name in sorted(EXPECTED_ARCHIVE_FILES):
        path = source_root / name
        require(path.is_file(), f"Missing archived source file: {path}")
        record = by_name[name]
        require(path.stat().st_size == record["bytes"], f"Size mismatch: {name}")
        require(sha256_file(path) == record["sha256"], f"SHA-256 mismatch: {name}")

    return manifest, claims


def calculate_ranges(
    summary_rows: list[dict[str, str]],
    archived_claims: dict[str, Any],
) -> list[dict[str, object]]:
    require(len(summary_rows) == 40, "Sensitivity summary must contain 40 rows")
    ranges: list[dict[str, object]] = []
    for family in FAMILY_ORDER:
        included = [
            row
            for row in summary_rows
            if row["experiment_family"] == family and row["range_included"] == "True"
        ]
        expected_count = 20 if family == "graph_parameter" else 16
        require(len(included) == expected_count, f"Unexpected {family} range membership")
        family_claim = archived_claims["ranges"][family]
        require(family_claim["row_count"] == expected_count, f"Claim row count differs: {family}")
        require(
            family_claim["membership_rule"] == MEMBERSHIP_RULES[family],
            f"Claim membership rule differs: {family}",
        )
        for metric, rule in METRIC_RULES.items():
            raw_values = [float(row[metric]) for row in included]
            minimum_raw = min(raw_values)
            maximum_raw = max(raw_values)
            minimum_sources = sorted(
                row["variant_id"] for row in included if float(row[metric]) == minimum_raw
            )
            maximum_sources = sorted(
                row["variant_id"] for row in included if float(row[metric]) == maximum_raw
            )
            scale = float(rule["scale"])
            decimals = int(rule["display_decimal_places"])
            minimum_unit = minimum_raw * scale
            maximum_unit = maximum_raw * scale
            minimum_display = display(minimum_unit, decimals)
            maximum_display = display(maximum_unit, decimals)
            paper_minimum, paper_maximum = PAPER_RANGE_TARGETS[family][metric]
            matches_paper = (
                minimum_display == paper_minimum and maximum_display == paper_maximum
            )
            require(matches_paper, f"{family}/{metric} does not match Section V-D")

            archived_metric = family_claim[
                "fpr_percent" if metric == "fpr" else
                "feature_jaccard_percent" if metric == "feature_jaccard" else
                metric
            ]
            require(
                archived_metric["observed"]["minimum"]["raw_value"] == minimum_raw,
                f"Independent minimum differs from archived claim: {family}/{metric}",
            )
            require(
                archived_metric["observed"]["maximum"]["raw_value"] == maximum_raw,
                f"Independent maximum differs from archived claim: {family}/{metric}",
            )
            require(
                archived_metric["draft_reference_display"]
                == [paper_minimum, paper_maximum],
                f"Paper target differs from archived claim: {family}/{metric}",
            )
            ranges.append(
                {
                    "study_family": family,
                    "membership_rule": MEMBERSHIP_RULES[family],
                    "variant_rows": expected_count,
                    "metric": metric,
                    "reported_unit": rule["unit"],
                    "minimum_raw": minimum_raw,
                    "maximum_raw": maximum_raw,
                    "minimum_source_variant_ids": "|".join(minimum_sources),
                    "maximum_source_variant_ids": "|".join(maximum_sources),
                    "minimum_reported_unit": minimum_unit,
                    "maximum_reported_unit": maximum_unit,
                    "display_decimal_places": decimals,
                    "minimum_display": minimum_display,
                    "maximum_display": maximum_display,
                    "paper_minimum_display": paper_minimum,
                    "paper_maximum_display": paper_maximum,
                    "matches_paper_at_reported_precision": True,
                }
            )
    return ranges


def calculate_ranking_reductions(
    summary_rows: list[dict[str, str]],
    archived_claims: dict[str, Any],
) -> list[dict[str, object]]:
    ranking_rows = [
        row for row in summary_rows if row["experiment_family"] == "ranking_term"
    ]
    reductions: list[dict[str, object]] = []
    for case_id in CASE_ORDER:
        case_rows = [row for row in ranking_rows if row["case_id"] == case_id]
        baselines = [row for row in case_rows if row["is_reference_baseline"] == "True"]
        variants = [row for row in case_rows if row["range_included"] == "True"]
        require(len(baselines) == 1, f"{case_id}: expected one ranking baseline")
        require(len(variants) == 4, f"{case_id}: expected four term removals")
        baseline_mcc = float(baselines[0]["mcc"])
        deltas = [(row["variant"], float(row["mcc"]) - baseline_mcc) for row in variants]
        minimum_delta = min(delta for _, delta in deltas)
        largest_reductions = sorted(
            variant for variant, delta in deltas if delta == minimum_delta
        )
        archived = archived_claims["ranking_largest_mcc_reduction_by_case"][case_id]
        require(archived["baseline_mcc"] == baseline_mcc, f"{case_id}: baseline differs")
        require(
            archived["minimum_mcc_delta"] == minimum_delta,
            f"{case_id}: MCC reduction differs",
        )
        require(
            sorted(archived["variants"]) == largest_reductions,
            f"{case_id}: largest-reduction variant differs",
        )
        target = PAPER_REDUCTION_TARGETS.get(case_id, "")
        paper_claim_applies = bool(target)
        matches_paper = not paper_claim_applies or target in largest_reductions
        require(matches_paper, f"{case_id}: largest-reduction paper claim differs")
        if paper_claim_applies:
            source_check = archived_claims["draft_largest_reduction_checks"][case_id]
            require(source_check["expected"] == target, f"{case_id}: paper target differs")
            require(source_check["matches"] is True, f"{case_id}: archived target failed")
        reductions.append(
            {
                "case_id": case_id,
                "baseline_mcc": baseline_mcc,
                "largest_reduction_delta_mcc": minimum_delta,
                "largest_reduction_variants": "|".join(largest_reductions),
                "paper_claim_applies": paper_claim_applies,
                "paper_claim_variant": target,
                "matches_paper_claim": matches_paper,
            }
        )
    return reductions


def calculate_stability_threshold_invariance(
    summary_rows: list[dict[str, str]],
    archived_claims: dict[str, Any],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Compare every changed ``pi_min`` row with its same-case baseline.

    The manuscript's "decision metrics" are MCC and benign FPR. The claim gate
    uses the same zero-relative, 1e-15-absolute tolerance as the archived audit.
    Strict CSV-text and parsed-number equality are reported separately, so a
    tolerance-level match cannot be presented as an observed exact identity.
    """

    graph_rows = [
        row for row in summary_rows if row["experiment_family"] == "graph_parameter"
    ]
    graph_protocol = protocol["graph"]
    baseline_pi_min = float(graph_protocol["baseline_pi_min"])
    baseline_tau_c = float(graph_protocol["baseline_tau_c"])
    protocol_pi_values = sorted(float(value) for value in graph_protocol["pi_min_values"])
    require(
        baseline_pi_min in protocol_pi_values,
        "The baseline stability threshold is not in the tested values",
    )
    changed_pi_values = [
        value for value in protocol_pi_values if value != baseline_pi_min
    ]
    require(changed_pi_values, "No changed stability thresholds are defined")

    archived_checks = archived_claims.get("stability_threshold_checks", [])
    archived_by_key = {
        (str(row["case_id"]), str(row["variant"])): row
        for row in archived_checks
    }
    expected_keys = {
        (case_id, f"pi_min_{format(pi_min, 'g')}")
        for case_id in CASE_ORDER
        for pi_min in changed_pi_values
    }
    require(
        set(archived_by_key) == expected_keys,
        "Archived stability-threshold check inventory is incomplete",
    )

    comparisons: list[dict[str, object]] = []
    for case_id in CASE_ORDER:
        case_rows = [row for row in graph_rows if row["case_id"] == case_id]
        baselines = [row for row in case_rows if row["variant"] == "baseline"]
        changed = [
            row for row in case_rows if row["variant"].startswith("pi_min_")
        ]
        require(len(baselines) == 1, f"{case_id}: expected one graph baseline")
        require(
            len(changed) == len(changed_pi_values),
            f"{case_id}: incomplete changed stability-threshold rows",
        )
        baseline = baselines[0]
        require(
            float(baseline["pi_min"]) == baseline_pi_min,
            f"{case_id}: baseline pi_min differs from the protocol",
        )
        require(
            float(baseline["tau_c"]) == baseline_tau_c,
            f"{case_id}: baseline tau_c differs from the protocol",
        )

        observed_changed_values = sorted(float(row["pi_min"]) for row in changed)
        require(
            observed_changed_values == changed_pi_values,
            f"{case_id}: tested pi_min values differ from the protocol",
        )
        for row in sorted(changed, key=lambda item: float(item["pi_min"])):
            require(
                float(row["tau_c"]) == baseline_tau_c,
                f"{case_id}/{row['variant']}: tau_c was not held at baseline",
            )
            metric_results: dict[str, dict[str, object]] = {}
            for metric, rule in STABILITY_DECISION_METRICS.items():
                baseline_raw = float(baseline[metric])
                compared_raw = float(row[metric])
                delta_raw = compared_raw - baseline_raw
                csv_text_identical = row[metric] == baseline[metric]
                numeric_strictly_equal = compared_raw == baseline_raw
                within_tolerance = math.isclose(
                    compared_raw,
                    baseline_raw,
                    rel_tol=STABILITY_RELATIVE_TOLERANCE,
                    abs_tol=STABILITY_ABSOLUTE_TOLERANCE,
                )
                scale = float(rule["reported_scale"])
                decimals = int(rule["reported_decimal_places"])
                baseline_display = display(baseline_raw * scale, decimals)
                compared_display = display(compared_raw * scale, decimals)
                metric_results[metric] = {
                    "baseline_raw": baseline_raw,
                    "compared_raw": compared_raw,
                    "delta_raw": delta_raw,
                    "csv_decimal_text_identical": csv_text_identical,
                    "numeric_strictly_equal": numeric_strictly_equal,
                    "within_declared_tolerance": within_tolerance,
                    "baseline_display": baseline_display,
                    "compared_display": compared_display,
                    "equal_at_reported_precision": baseline_display == compared_display,
                }

            variant = str(row["variant"])
            archived = archived_by_key[(case_id, variant)]
            require(
                archived["baseline_mcc"] == metric_results["mcc"]["baseline_raw"]
                and archived["mcc"] == metric_results["mcc"]["compared_raw"],
                f"{case_id}/{variant}: MCC differs from archived claim audit",
            )
            require(
                archived["baseline_fpr"] == metric_results["fpr"]["baseline_raw"]
                and archived["fpr"] == metric_results["fpr"]["compared_raw"],
                f"{case_id}/{variant}: FPR differs from archived claim audit",
            )
            all_within_tolerance = all(
                bool(result["within_declared_tolerance"])
                for result in metric_results.values()
            )
            all_reported_equal = all(
                bool(result["equal_at_reported_precision"])
                for result in metric_results.values()
            )
            require(
                archived["decision_metrics_exactly_preserved"]
                == all_within_tolerance,
                f"{case_id}/{variant}: archived tolerance verdict differs",
            )
            require(
                archived["decision_metrics_preserved_at_reported_precision"]
                == all_reported_equal,
                f"{case_id}/{variant}: archived display verdict differs",
            )
            comparisons.append(
                {
                    "case_id": case_id,
                    "baseline_variant_id": str(baseline["variant_id"]),
                    "baseline_pi_min": baseline_pi_min,
                    "compared_variant_id": str(row["variant_id"]),
                    "compared_variant": variant,
                    "compared_pi_min": float(row["pi_min"]),
                    "mcc_baseline_raw": metric_results["mcc"]["baseline_raw"],
                    "mcc_compared_raw": metric_results["mcc"]["compared_raw"],
                    "mcc_delta_raw": metric_results["mcc"]["delta_raw"],
                    "mcc_csv_decimal_text_identical": metric_results["mcc"][
                        "csv_decimal_text_identical"
                    ],
                    "mcc_numeric_strictly_equal": metric_results["mcc"][
                        "numeric_strictly_equal"
                    ],
                    "mcc_within_declared_tolerance": metric_results["mcc"][
                        "within_declared_tolerance"
                    ],
                    "mcc_equal_at_reported_precision": metric_results["mcc"][
                        "equal_at_reported_precision"
                    ],
                    "fpr_baseline_raw": metric_results["fpr"]["baseline_raw"],
                    "fpr_compared_raw": metric_results["fpr"]["compared_raw"],
                    "fpr_delta_raw": metric_results["fpr"]["delta_raw"],
                    "fpr_csv_decimal_text_identical": metric_results["fpr"][
                        "csv_decimal_text_identical"
                    ],
                    "fpr_numeric_strictly_equal": metric_results["fpr"][
                        "numeric_strictly_equal"
                    ],
                    "fpr_within_declared_tolerance": metric_results["fpr"][
                        "within_declared_tolerance"
                    ],
                    "fpr_equal_at_reported_precision": metric_results["fpr"][
                        "equal_at_reported_precision"
                    ],
                    "all_decision_metrics_csv_decimal_text_identical": all(
                        bool(result["csv_decimal_text_identical"])
                        for result in metric_results.values()
                    ),
                    "all_decision_metrics_numeric_strictly_equal": all(
                        bool(result["numeric_strictly_equal"])
                        for result in metric_results.values()
                    ),
                    "all_decision_metrics_within_declared_tolerance": all_within_tolerance,
                    "all_decision_metrics_equal_at_reported_precision": all_reported_equal,
                }
            )

    expected_comparisons = len(CASE_ORDER) * len(changed_pi_values)
    require(
        len(comparisons) == expected_comparisons,
        "Stability-threshold comparison inventory is incomplete",
    )
    all_within_tolerance = all(
        bool(row["all_decision_metrics_within_declared_tolerance"])
        for row in comparisons
    )
    require(
        archived_claims.get("stability_threshold_metrics_preserved_exactly")
        == all_within_tolerance,
        "Archived aggregate stability-threshold verdict differs",
    )
    claim_supported = len(comparisons) == expected_comparisons and all_within_tolerance
    require(
        claim_supported,
        "Stability-threshold decision metrics were not preserved",
    )
    return {
        "claim": (
            "Changing the stability threshold preserved the decision metrics "
            "across the tested interval."
        ),
        "parameter": {
            "name": "pi_min",
            "meaning": "minimum benign-bootstrap edge recurrence fraction",
            "baseline": baseline_pi_min,
            "tested_values": protocol_pi_values,
            "tested_interval": [min(protocol_pi_values), max(protocol_pi_values)],
            "changed_values_compared_to_baseline": changed_pi_values,
            "tau_c_held_fixed": baseline_tau_c,
            "variation_rule": graph_protocol["variation_rule"],
        },
        "decision_metrics": [
            {"name": name, **rule}
            for name, rule in STABILITY_DECISION_METRICS.items()
        ],
        "comparison_policy": {
            "claim_gate": (
                "Every changed pi_min row must match its same-case baseline for "
                "both decision metrics under the declared numeric tolerance."
            ),
            "numeric_tolerance": {
                "relative_tolerance": STABILITY_RELATIVE_TOLERANCE,
                "absolute_tolerance": STABILITY_ABSOLUTE_TOLERANCE,
                "formula": (
                    "abs(compared-baseline) <= max(relative_tolerance * "
                    "max(abs(compared), abs(baseline)), absolute_tolerance)"
                ),
                "implementation": "Python math.isclose",
            },
            "strict_equality_audit": (
                "CSV decimal-text identity and parsed-float equality are also "
                "reported, but the declared tolerance is the claim gate."
            ),
            "reported_precision_secondary_check": {
                "mcc_decimal_places": 3,
                "fpr_percent_decimal_places": 2,
                "used_as_claim_gate": False,
            },
        },
        "scope": {
            "case_ids": list(CASE_ORDER),
            "expected_comparisons": expected_comparisons,
            "observed_comparisons": len(comparisons),
            "calculation_basis": (
                "Arithmetic mean workload=ALL cross-validation MCC and benign "
                "FPR at each frozen operating point."
            ),
            "excluded_from_decision_metric_claim": [
                {
                    "metric": "feature_jaccard",
                    "reason": (
                        "Selected-feature overlap is a structural sensitivity output, "
                        "not a classifier decision metric; it changes for A_RH at "
                        "pi_min=0.625 even though MCC and FPR do not."
                    ),
                }
            ],
        },
        "comparisons": comparisons,
        "all_csv_decimal_text_identical": all(
            bool(row["all_decision_metrics_csv_decimal_text_identical"])
            for row in comparisons
        ),
        "all_numeric_values_strictly_equal": all(
            bool(row["all_decision_metrics_numeric_strictly_equal"])
            for row in comparisons
        ),
        "all_within_declared_tolerance": all_within_tolerance,
        "all_equal_at_reported_precision": all(
            bool(row["all_decision_metrics_equal_at_reported_precision"])
            for row in comparisons
        ),
        "claim_supported": claim_supported,
    }


def file_record(path: Path, root: Path, **extra: object) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        **extra,
    }


def build_bundle(
    source_root: Path = DEFAULT_SOURCE_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    source_root = source_root.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    manifest, archived_claims = validate_source_archive(source_root)
    protocol = read_json(source_root / "protocol.json")
    summary_rows = read_csv(source_root / "graph_sensitivity_summary.csv")
    ranges = calculate_ranges(summary_rows, archived_claims)
    reductions = calculate_ranking_reductions(summary_rows, archived_claims)
    stability_invariance = calculate_stability_threshold_invariance(
        summary_rows,
        archived_claims,
        protocol,
    )

    ranges_path = output_root / "section_vd_sensitivity_ranges.csv"
    reductions_path = output_root / "section_vd_ranking_reductions.csv"
    stability_path = output_root / "section_vd_stability_threshold_invariance.csv"
    claims_path = output_root / "section_vd_claims.json"
    evidence_path = output_root / "evidence_manifest.json"
    write_csv(
        ranges_path,
        (
            "study_family",
            "membership_rule",
            "variant_rows",
            "metric",
            "reported_unit",
            "minimum_raw",
            "maximum_raw",
            "minimum_source_variant_ids",
            "maximum_source_variant_ids",
            "minimum_reported_unit",
            "maximum_reported_unit",
            "display_decimal_places",
            "minimum_display",
            "maximum_display",
            "paper_minimum_display",
            "paper_maximum_display",
            "matches_paper_at_reported_precision",
        ),
        ranges,
    )
    write_csv(
        reductions_path,
        (
            "case_id",
            "baseline_mcc",
            "largest_reduction_delta_mcc",
            "largest_reduction_variants",
            "paper_claim_applies",
            "paper_claim_variant",
            "matches_paper_claim",
        ),
        reductions,
    )
    write_csv(
        stability_path,
        (
            "case_id",
            "baseline_variant_id",
            "baseline_pi_min",
            "compared_variant_id",
            "compared_variant",
            "compared_pi_min",
            "mcc_baseline_raw",
            "mcc_compared_raw",
            "mcc_delta_raw",
            "mcc_csv_decimal_text_identical",
            "mcc_numeric_strictly_equal",
            "mcc_within_declared_tolerance",
            "mcc_equal_at_reported_precision",
            "fpr_baseline_raw",
            "fpr_compared_raw",
            "fpr_delta_raw",
            "fpr_csv_decimal_text_identical",
            "fpr_numeric_strictly_equal",
            "fpr_within_declared_tolerance",
            "fpr_equal_at_reported_precision",
            "all_decision_metrics_csv_decimal_text_identical",
            "all_decision_metrics_numeric_strictly_equal",
            "all_decision_metrics_within_declared_tolerance",
            "all_decision_metrics_equal_at_reported_precision",
        ),
        stability_invariance["comparisons"],
    )

    claims = {
        "schema_version": 1,
        "paper_item": "Section V-D graph- and ranking-sensitivity statements",
        "calculation_basis": archived_claims["calculation_basis"],
        "range_membership": archived_claims["range_membership"],
        "ranges": ranges,
        "stability_threshold_invariance": stability_invariance,
        "ranking_largest_mcc_reductions": reductions,
        "paper_specific_reduction_claims": [
            {
                "case_id": case_id,
                "largest_reduction_variant": target,
                "matches": next(
                    row["matches_paper_claim"]
                    for row in reductions
                    if row["case_id"] == case_id
                ),
            }
            for case_id, target in PAPER_REDUCTION_TARGETS.items()
        ],
        "interpretation_limits": archived_claims["interpretation_limits"],
        "status": "PASS",
    }
    claims_path.write_text(
        json.dumps(claims, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    source_files = []
    for name in sorted(EXPECTED_ARCHIVE_FILES | {"run_manifest.json"}):
        path = source_root / name
        source_files.append(
            {
                "path": path.relative_to(REPOSITORY).as_posix(),
                "role": SOURCE_ROLES[name],
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    generator_path = Path(__file__).resolve()
    source_files.append(
        {
            "path": generator_path.relative_to(REPOSITORY).as_posix(),
            "role": "paper-facing projection and independent claim validator",
            "sha256": sha256_file(generator_path),
            "size_bytes": generator_path.stat().st_size,
        }
    )
    source_files.sort(key=lambda row: str(row["path"]))

    outputs = [
        file_record(ranges_path, output_root, row_count=len(ranges)),
        file_record(reductions_path, output_root, row_count=len(reductions)),
        file_record(
            stability_path,
            output_root,
            row_count=len(stability_invariance["comparisons"]),
        ),
        file_record(claims_path, output_root, status=claims["status"]),
    ]
    outputs.sort(key=lambda row: str(row["path"]))
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "evidence_class": "clean_archived_evidence",
        "archival_status": "CLEAN_ARCHIVED",
        "status": "COMPLETE_CLEAN_ARCHIVED_VERIFIED",
        "paper_items": [
            "Section V-D graph-parameter sensitivity ranges",
            "Section V-D stability-threshold decision-metric invariance",
            "Section V-D ranking-term-removal ranges",
            "Section V-D largest-MCC-reduction statements",
        ],
        "source_commit": manifest["repository_commit"],
        "clean_run_evidence": {
            "repository_commit": manifest["repository_commit"],
            "repository_commit_at_finish": manifest["repository_commit_at_finish"],
            "git_dirty_at_start": manifest["git_dirty_at_start"],
            "git_status_at_start": manifest["git_status_at_start"],
            "git_status_at_finish": manifest["git_status_at_finish"],
            "source_and_inputs_unchanged_during_run": manifest[
                "source_and_inputs_unchanged_during_run"
            ],
            "archival_provenance_status": manifest["archival_provenance_status"],
            "claim_status": manifest["claim_status"],
            "draft_claims_match_at_reported_precision": manifest[
                "draft_claims_match_at_reported_precision"
            ],
            "started_utc": manifest["started_utc"],
            "finished_utc": manifest["finished_utc"],
            "runtime_seconds": manifest["runtime_seconds"],
            "seed": manifest["seed"],
            "threads": manifest["threads"],
            "python_hash_seed_at_process_start": manifest[
                "python_hash_seed_at_process_start"
            ],
            "runtime_version_mismatches": manifest["runtime_versions"]["mismatches"],
            "combined_input_sha256": manifest["combined_input_sha256"],
        },
        "verification_scope": {
            "fresh_clean_run_recorded": True,
            "source_archive_hashes_verified": True,
            "claims_independently_recomputed_from_summary": True,
            "stability_threshold_invariance_recomputed_from_summary": True,
            "independent_repeat_recorded": False,
            "projection_reruns_experiment": False,
        },
        "calculation_basis": archived_claims["calculation_basis"],
        "source_files": source_files,
        "outputs": outputs,
        "claim_audit": {
            "path": claims_path.name,
            "sha256": sha256_file(claims_path),
            "status": claims["status"],
        },
    }
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence


def check_bundle(source_root: Path, output_root: Path) -> None:
    require(output_root.is_dir(), f"Tracked sensitivity bundle is missing: {output_root}")
    with tempfile.TemporaryDirectory(prefix="citadel-paper-sensitivity-") as directory:
        candidate = Path(directory) / "sensitivity"
        build_bundle(source_root, candidate)
        for name in OUTPUT_FILES:
            tracked = output_root / name
            generated = candidate / name
            require(tracked.is_file(), f"Tracked bundle file is missing: {tracked}")
            require(
                tracked.read_bytes() == generated.read_bytes(),
                f"Tracked sensitivity bundle is stale: {name}",
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in a temporary directory and require byte-identical tracked files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check:
        check_bundle(args.source_root, args.output_root)
        print(f"PASS: sensitivity paper bundle is current: {args.output_root}")
    else:
        build_bundle(args.source_root, args.output_root)
        print(f"Wrote sensitivity paper bundle: {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
