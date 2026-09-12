#!/usr/bin/env python3
"""Audit the compact, paper-facing CITADEL result bundles.

This verifier deliberately reports two different conclusions:

* ``coverage_status`` / ``traceability_status`` say whether each paper-facing
  bundle is present, internally consistent, and matches the manuscript values
  encoded below at their reported precision.
* ``fresh_clean_rerun_status`` says whether every family is backed by an
  explicitly documented clean rerun.  A reference-only projection or an
  archived-report reanalysis can pass traceability without passing this second
  test.

The distinction prevents a successful integrity audit from being presented as
evidence that every experiment was freshly rerun on the current machine.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE_ROOT = REPO_ROOT / "reproducibility" / "paper_results"
EXPECTED_FAMILIES = ("core", "sensitivity", "rtl", "intel", "apple")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LFS_PREFIX = b"version https://git-lfs.github.com/spec/v1"

EXPECTED_PAPER_ITEMS: dict[str, set[str]] = {
    "core": {
        "Table VI",
        "Figure 3",
        "Section V-B",
        "Table VII",
        "Figure 4",
        "Table VIII",
        "Section V-F",
        "Table IX",
        "Table X CITADEL row",
        "Figure 6",
        "Section V-H",
    },
    # The exact sensitivity wording is checked in the claims payload.  The
    # compact manifest may identify the manuscript sections with either one
    # combined label or several individual labels.
    "sensitivity": {
        "Section V-D graph-parameter sensitivity ranges",
        "Section V-D stability-threshold decision-metric invariance",
        "Section V-D ranking-term-removal ranges",
        "Section V-D largest-MCC-reduction statements",
    },
    "rtl": {"Figure 5", "Table XI"},
    "intel": {"Figure 7", "Section V-I numerical statement"},
    "apple": {"Figure 8", "Section V-J"},
}

REQUIRED_FILES: dict[str, set[str]] = {
    "core": {
        "table_vi_selected_configurations.csv",
        "figure_3_dse_envelope.csv",
        "section_vb_workload_results.csv",
        "section_vb_workload_details.csv",
        "table_vii_feature_budget_tradeoff.csv",
        "figure_4_graph_nodes.csv",
        "figure_4_graph_edges.csv",
        "figure_4_top_features.csv",
        "table_viii_integer_reference_error.csv",
        "table_ix_analytical_cost.csv",
        "section_vf_operator_constants.csv",
        "section_vf_cost_basis.csv",
        "table_x_citadel_row.csv",
        "figure_6_reference_validity_trend.csv",
        "figure_6_reference_validity_summary.csv",
        "section_vh_lifecycle_protocol.csv",
    },
    "sensitivity": {
        "section_vd_claims.json",
        "section_vd_sensitivity_ranges.csv",
        "section_vd_ranking_reductions.csv",
        "section_vd_stability_threshold_invariance.csv",
    },
    "rtl": {"table_xi.csv", "figure_5_source.csv", "figure_5.png"},
    "intel": {
        "figure7_claims.json",
        "repeat_verification.json",
        "intel_workload_orders/intel_workload_order_run_results.csv",
        "intel_workload_orders/intel_workload_order_summary.csv",
        "intel_workload_orders/fig_intel_workload_order_variation.png",
    },
    "apple": {
        "figure_8_portability_envelope.csv",
        "section_vj_workload_averages.csv",
        "section_vj_study_scope.csv",
    },
}


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _content_identity(path: Path) -> tuple[str, int, bool]:
    """Return (sha256 identity, logical size, is_lfs_pointer)."""

    content = path.read_bytes()
    if not content.startswith(LFS_PREFIX):
        return hashlib.sha256(content).hexdigest(), len(content), False

    oid: str | None = None
    logical_size: int | None = None
    for line in content.decode("ascii").splitlines():
        if line.startswith("oid sha256:"):
            oid = line.removeprefix("oid sha256:")
        elif line.startswith("size "):
            logical_size = int(line.removeprefix("size "))
    if oid is None or logical_size is None:
        raise ValueError(f"malformed Git LFS pointer: {path}")
    return oid, logical_size, True


def _relative_target(base: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("record path must be a nonempty string")
    path = Path(relative)
    if path.is_absolute():
        raise ValueError(f"absolute record path is not allowed: {relative}")
    resolved_base = base.resolve()
    resolved = (base / path).resolve()
    try:
        resolved.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"record path escapes its bundle root: {relative}") from exc
    return resolved


def _check_record(
    record: Any,
    *,
    base: Path,
    record_name: str,
) -> tuple[bool, str]:
    if not isinstance(record, dict):
        return False, f"{record_name} is not an object"
    try:
        path = _relative_target(base, record.get("path"))
    except (TypeError, ValueError) as exc:
        return False, f"{record_name}: {exc}"
    expected_sha = record.get("sha256")
    if not isinstance(expected_sha, str) or SHA256_RE.fullmatch(expected_sha) is None:
        return False, f"{record_name} has no valid sha256"
    if not path.is_file():
        return False, f"{record_name} is missing: {record.get('path')}"
    try:
        observed_sha, observed_size, is_pointer = _content_identity(path)
    except (OSError, UnicodeError, ValueError) as exc:
        return False, f"{record_name} could not be read: {exc}"
    if observed_sha != expected_sha:
        return (
            False,
            f"{record_name} sha256 mismatch for {record.get('path')}: "
            f"expected {expected_sha}, observed {observed_sha}",
        )
    expected_size = record.get("size_bytes", record.get("bytes"))
    if expected_size is not None and expected_size != observed_size:
        return (
            False,
            f"{record_name} size mismatch for {record.get('path')}: "
            f"expected {expected_size}, observed {observed_size}",
        )
    pointer_note = " (Git LFS identity)" if is_pointer else ""
    return True, f"{record.get('path')} hash and size match{pointer_note}"


def _record_shape(record: Any, *, record_name: str) -> tuple[bool, str]:
    """Validate provenance metadata without rereading a potentially huge input."""

    if not isinstance(record, dict):
        return False, f"{record_name} is not an object"
    path = record.get("path")
    digest = record.get("sha256")
    if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
        return False, f"{record_name} has an unsafe or empty path"
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        return False, f"{record_name} has no valid sha256"
    return True, f"{path} has a relative path and sha256 identity"


def _png_facts(path: Path) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "decoded": False,
        "width_px": 0,
        "height_px": 0,
        "nonuniform": False,
    }
    try:
        from PIL import Image, ImageStat

        with Image.open(path) as opened:
            if opened.format != "PNG":
                return facts
            opened.verify()
        with Image.open(path) as opened:
            width, height = opened.size
            sample = opened.convert("L")
            sample.thumbnail((256, 256))
            variance = float(ImageStat.Stat(sample).var[0])
        facts.update(
            {
                "decoded": True,
                "width_px": int(width),
                "height_px": int(height),
                "nonuniform": variance > 1.0,
            }
        )
    except (OSError, ValueError):
        pass
    return facts


def _add_check(
    checks: list[dict[str, str]],
    check_id: str,
    passed: bool,
    message: str,
) -> None:
    checks.append(
        {
            "id": check_id,
            "status": "PASS" if passed else "FAIL",
            "message": message,
        }
    )


def _all_pass(checks: Iterable[dict[str, str]]) -> bool:
    return all(item["status"] == "PASS" for item in checks)


def _manifest_path(family_dir: Path, family: str) -> Path | None:
    names = (
        ("evidence.json", "evidence_manifest.json")
        if family == "rtl"
        else ("evidence_manifest.json", "evidence.json")
    )
    return next((family_dir / name for name in names if (family_dir / name).is_file()), None)


def _manifest_items(manifest: dict[str, Any]) -> list[str]:
    items = manifest.get("paper_items", manifest.get("scope", []))
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, str) and item]


def _declared_output_records(manifest: dict[str, Any]) -> tuple[str, list[Any]]:
    for key in ("outputs", "archived_artifacts", "artifacts"):
        records = manifest.get(key)
        if isinstance(records, list):
            return key, records
    return "outputs", []


def _output_base(
    *,
    bundle_root: Path,
    family_dir: Path,
    family: str,
    record: Any,
) -> Path:
    if isinstance(record, dict):
        relative = record.get("path")
        if isinstance(relative, str) and Path(relative).parts[:1] == (family,):
            return bundle_root
    return family_dir


def _required_file_check(family_dir: Path, family: str) -> tuple[bool, str]:
    missing = sorted(
        path for path in REQUIRED_FILES[family] if not (family_dir / path).is_file()
    )
    if missing:
        return False, "missing required paper-facing files: " + ", ".join(missing)
    count = len(REQUIRED_FILES[family])
    return True, f"all {count} required paper-facing files are present"


def _declared_relative_paths(records: Sequence[Any], family: str) -> set[str]:
    declared: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            continue
        parts = Path(record["path"]).parts
        if parts[:1] == (family,):
            parts = parts[1:]
        declared.add(Path(*parts).as_posix())
    return declared


def _core_claim_checks(family_dir: Path) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    try:
        selected = _csv(family_dir / "table_vi_selected_configurations.csv")
        identities = [
            (row["setup"], row["event"], int(row["selected_features"]), int(row["block_length"]))
            for row in selected
        ]
        results.append(
            (
                "table_vi.configurations",
                identities
                == [
                    ("A", "DROOP", 15, 1000),
                    ("A", "RH", 20, 550),
                    ("B", "DROOP", 15, 200),
                    ("B", "SPECTRE", 30, 700),
                ],
                "Table VI has the four selected CINTAS configurations",
            )
        )
        results.append(
            (
                "table_vi.all_reported_cells",
                [
                    (
                        row["setup"],
                        row["event"],
                        row["view"],
                        int(row["selected_features"]),
                        int(row["available_channels"]),
                        round(float(row["retained_percent"]), 1),
                        int(row["block_length"]),
                        row["aggregation"],
                        round(float(row["score_mixture"]), 2),
                        row["weighting"],
                        int(row["fixed_point_q"]),
                        round(float(row["threshold_quantile"]), 2),
                        round(float(row["roc_auc"]), 3),
                        round(float(row["auc_pr"]), 3),
                        round(float(row["f1"]), 3),
                        round(float(row["mcc"]), 3),
                        round(100.0 * float(row["fpr"]), 2),
                        round(float(row["area_overhead_percent"]), 3),
                        round(float(row["idle_power_overhead_percent"]), 3),
                    )
                    for row in selected
                ]
                == [
                    ("A", "DROOP", "Transient", 15, 181, 8.3, 1000, "median", 0.00, "inverse", 15, 0.99, 1.000, 1.000, 0.996, 0.992, 0.78, 0.083, 0.060),
                    ("A", "RH", "Standard", 20, 181, 11.0, 550, "median", 1.00, "uniform", 8, 0.99, 1.000, 1.000, 0.996, 0.992, 0.85, 0.110, 0.080),
                    ("B", "DROOP", "Transient", 15, 460, 3.3, 200, "median", 0.50, "inverse", 15, 0.99, 0.999, 0.999, 0.995, 0.991, 0.77, 0.083, 0.060),
                    ("B", "SPECTRE", "Standard", 30, 460, 6.5, 700, "median", 0.75, "uniform", 8, 0.99, 1.000, 1.000, 0.995, 0.989, 1.10, 0.161, 0.118),
                ],
                "Every Table VI configuration, detection-quality, and analytical-cost cell matches at manuscript precision",
            )
        )

        budgets = _csv(family_dir / "table_vii_feature_budget_tradeoff.csv")
        results.append(
            (
                "table_vii.all_reported_cells",
                [
                    (
                        row["setup"],
                        row["event"],
                        int(row["minimum_budget"]),
                        int(row["maximum_budget"]),
                        int(row["saturation_budget"]),
                        round(float(row["mcc_at_minimum_budget"]), 3),
                        round(float(row["mcc_at_saturation_budget"]), 3),
                        round(float(row["mcc_at_maximum_budget"]), 3),
                        round(float(row["area_at_saturation_percent"]), 3),
                        round(float(row["power_at_saturation_percent"]), 3),
                        round(float(row["area_at_maximum_percent"]), 3),
                        round(float(row["power_at_maximum_percent"]), 3),
                    )
                    for row in budgets
                ]
                == [
                    ("A", "DROOP", 15, 50, 15, 0.992, 0.992, 0.597, 0.083, 0.060, 0.268, 0.197),
                    ("A", "RH", 5, 30, 20, 0.180, 0.992, 0.991, 0.110, 0.080, 0.161, 0.118),
                    ("B", "DROOP", 15, 50, 15, 0.991, 0.991, 0.989, 0.083, 0.060, 0.267, 0.196),
                    ("B", "SPECTRE", 5, 30, 5, 0.986, 0.986, 0.989, 0.030, 0.021, 0.161, 0.118),
                ],
                "Every Table VII budget, MCC, area, and power cell matches at manuscript precision",
            )
        )

        workload = _csv(family_dir / "section_vb_workload_results.csv")
        results.append(
            (
                "section_vb.aggregate_values",
                [round(float(row["mean_mcc"]), 3) for row in workload]
                == [0.989, 0.994, 0.991, 0.990]
                and [round(100.0 * float(row["mean_fpr"]), 2) for row in workload]
                == [1.28, 0.62, 0.77, 1.28]
                and [round(float(row["mean_mcc_gap_to_workload_oracle"]), 3) for row in workload]
                == [0.011, 0.006, 0.009, 0.010],
                "Section V-B aggregate MCC, FPR, and oracle-gap values match",
            )
        )
        workload_details = _csv(family_dir / "section_vb_workload_details.csv")
        minimum_by_case: dict[tuple[str, str], str] = {}
        for setup, event in (("A", "DROOP"), ("A", "RH"), ("B", "DROOP"), ("B", "SPECTRE")):
            case_rows = [
                row for row in workload_details
                if row["setup"] == setup and row["event"] == event
            ]
            minimum = min(float(row["mcc"]) for row in case_rows)
            minimum_by_case[(setup, event)] = "|".join(
                sorted(row["workload"] for row in case_rows if float(row["mcc"]) == minimum)
            )
        mm_rows = [
            row for row in workload_details
            if row["setup"] == "B" and row["event"] == "DROOP" and row["workload"] == "MM"
        ]
        results.append(
            (
                "section_vb.workload_identities",
                len(workload_details) == 52
                and minimum_by_case
                == {
                    ("A", "DROOP"): "JA",
                    ("A", "RH"): "DJ",
                    ("B", "DROOP"): "JA",
                    ("B", "SPECTRE"): "JA",
                }
                and len(mm_rows) == 1
                and float(mm_rows[0]["mcc_gap_to_workload_oracle"]) > 0.0
                and float(mm_rows[0]["mcc"])
                > min(
                    float(row["mcc"])
                    for row in workload_details
                    if row["setup"] == "B" and row["event"] == "DROOP"
                ),
                "Section V-B minimum-workload identities and the nonzero, nonminimum B/DROOP MM gap match",
            )
        )

        integer = _csv(family_dir / "table_viii_integer_reference_error.csv")
        results.append(
            (
                "table_viii.all_reported_cells",
                len(integer) == 4
                and [
                    (
                        row["setup"],
                        row["event"],
                        int(row["fixed_point_q"]),
                        row["view"],
                        int(row["observations_compared"]),
                    )
                    for row in integer
                ]
                == [
                    ("A", "DROOP", 15, "Transient", 5000),
                    ("A", "RH", 8, "Standard", 5000),
                    ("B", "DROOP", 15, "Transient", 5000),
                    ("B", "SPECTRE", 8, "Standard", 5000),
                ]
                and [
                    f"{float(integer[0]['mean_absolute_score_error']):.1e}",
                    f"{float(integer[0]['maximum_absolute_score_error']):.1e}",
                    f"{float(integer[1]['mean_absolute_score_error']):.2e}",
                    f"{float(integer[1]['maximum_absolute_score_error']):.2e}",
                    f"{float(integer[2]['mean_absolute_score_error']):.2e}",
                    f"{float(integer[2]['maximum_absolute_score_error']):.2e}",
                    f"{float(integer[3]['mean_absolute_score_error']):.2e}",
                    f"{float(integer[3]['maximum_absolute_score_error']):.2f}",
                ]
                == [
                    "4.6e-05",
                    "2.6e-04",
                    "3.74e-02",
                    "4.78e-02",
                    "3.88e-04",
                    "4.89e-03",
                    "1.14e-01",
                    "2.09",
                ],
                "Every Table VIII setup, precision, score-error, view, and sample-count cell matches the manuscript",
            )
        )

        costs = _csv(family_dir / "table_ix_analytical_cost.csv")
        results.append(
            (
                "table_ix.all_reported_cells",
                [
                    (
                        row["setup"],
                        row["event"],
                        int(row["selected_features"]),
                        round(float(row["feature_reduction_percent"]), 1),
                        int(row["adders"]),
                        int(row["multipliers"]),
                        int(row["serial_cycles"]),
                        round(float(row["area_overhead_percent"]), 3),
                        round(float(row["idle_power_overhead_percent"]), 3),
                    )
                    for row in costs
                ]
                == [
                    ("A", "DROOP", 15, 91.7, 28, 32, 148, 0.083, 0.060),
                    ("A", "RH", 20, 89.0, 39, 42, 201, 0.110, 0.080),
                    ("B", "DROOP", 15, 96.7, 28, 32, 148, 0.083, 0.060),
                    ("B", "SPECTRE", 30, 93.5, 57, 62, 295, 0.161, 0.118),
                ],
                "Every Table IX feature, operator, cycle, area, and power cell matches at manuscript precision",
            )
        )

        comparison = _csv(family_dir / "table_x_citadel_row.csv")
        row = comparison[0] if len(comparison) == 1 else {}
        results.append(
            (
                "table_x.citadel_row",
                len(comparison) == 1
                and row.get("method") == "CITADEL"
                and row.get("edge_scoring") == "Fixed-point CINTAS"
                and row.get("minimum_runtime_features") == "15"
                and row.get("maximum_runtime_features") == "30"
                and row.get("drift_check") == "yes"
                and row.get("deployment_scope")
                == "Stable graph, DSE, frozen workload, and drift checks."
                and round(float(row["minimum_area_overhead_percent"]), 3) == 0.083
                and round(float(row["maximum_area_overhead_percent"]), 3) == 0.161
                and round(float(row["minimum_idle_power_overhead_percent"]), 3) == 0.060
                and round(float(row["maximum_idle_power_overhead_percent"]), 3) == 0.118,
                "Table X CITADEL row matches its manuscript ranges and wording",
            )
        )

        constants = _csv(family_dir / "section_vf_operator_constants.csv")
        results.append(
            (
                "section_vf.operator_constants",
                [
                    (
                        row["operator"],
                        int(row["bit_width"]),
                        f"{float(row['area_mm2']):.3e}",
                        row["power_mw_at_1ghz"],
                        float(row["delay_ps"]),
                        int(row["cycles"]),
                    )
                    for row in constants
                ]
                == [
                    ("add", 16, "1.165e-03", "0.178", 62.7, 3),
                    ("mult", 16, "4.532e-03", "0.5146", 29.09, 2),
                ],
                "Section V-F operator bit widths, areas, powers, delays, and cycle counts match",
            )
        )
        cost_basis = _csv(family_dir / "section_vf_cost_basis.csv")
        basis = cost_basis[0] if len(cost_basis) == 1 else {}
        results.append(
            (
                "section_vf.cost_basis",
                len(cost_basis) == 1
                and int(basis["operator_bit_width"]) == 16
                and float(basis["area_normalization_mm2"]) == 215.25
                and float(basis["idle_power_normalization_w"]) == 35.5,
                "Section V-F bit width and normalization references match",
            )
        )

        dse = _csv(family_dir / "figure_3_dse_envelope.csv")
        marked = [row for row in dse if row.get("selected_configuration") == "1"]
        results.append(
            (
                "figure_3.selected_markers",
                len(dse) == 270
                and [
                    (row["setup"], row["event"], int(row["feature_budget"]), int(row["block_length"]))
                    for row in marked
                ]
                == [
                    ("A", "DROOP", 15, 1000),
                    ("A", "RH", 20, 550),
                    ("B", "DROOP", 15, 200),
                    ("B", "SPECTRE", 30, 700),
                ],
                "Figure 3 source contains all DSE cells and four selected markers",
            )
        )

        nodes = _csv(family_dir / "figure_4_graph_nodes.csv")
        edges = _csv(family_dir / "figure_4_graph_edges.csv")
        top_features = _csv(family_dir / "figure_4_top_features.csv")
        results.append(
            (
                "figure_4.graph_sources",
                len(nodes) == 272
                and len(edges) == 383
                and bool(top_features)
                and {row["setup"] for row in nodes} == {"A", "B"},
                "Figure 4 node, edge, and label sources are complete",
            )
        )

        lifecycle = _csv(family_dir / "figure_6_reference_validity_summary.csv")
        by_key = {(row["setup"], row["method"]): row for row in lifecycle}
        results.append(
            (
                "figure_6.lifecycle",
                int(by_key[("A", "frozen")]["false_positive_blocks"]) == 4
                and int(by_key[("B", "frozen")]["false_positive_blocks"]) == 9
                and round(100.0 * float(by_key[("A", "frozen")]["fpr"]), 2) == 0.77
                and round(100.0 * float(by_key[("B", "frozen")]["fpr"]), 2) == 1.73
                and round(100.0 * float(by_key[("A", "threshold_only")]["fpr"]), 2) == 1.15
                and round(100.0 * float(by_key[("B", "threshold_only")]["fpr"]), 2) == 1.15
                and round(100.0 * float(by_key[("A", "full_feature_rank")]["fpr"]), 2) == 1.15
                and round(100.0 * float(by_key[("B", "full_feature_rank")]["fpr"]), 2) == 1.15
                and round(100.0 * float(by_key[("A", "full_feature_rank")]["rank_jaccard"]), 1) == 76.5
                and round(100.0 * float(by_key[("B", "full_feature_rank")]["rank_jaccard"]), 1) == 66.7,
                "Figure 6 lifecycle counts, FPRs, and feature overlaps match",
            )
        )
        protocol_rows = _csv(family_dir / "section_vh_lifecycle_protocol.csv")
        protocol = protocol_rows[0] if len(protocol_rows) == 1 else {}
        results.append(
            (
                "section_vh.protocol",
                len(protocol_rows) == 1
                and int(protocol["selected_features"]) == 15
                and int(protocol["block_length"]) == 100
                and protocol["aggregation"] == "max"
                and protocol["weighting"] == "uniform"
                and float(protocol["score_mixture"]) == 0.5
                and float(protocol["threshold_quantile"]) == 0.99
                and float(protocol["initial_reference_fraction"]) == 0.6
                and float(protocol["remaining_fraction"]) == 0.4
                and int(protocol["graph_subsamples"]) == 6
                and float(protocol["rank_centrality_weight"]) == 0.45
                and float(protocol["rank_stability_weight"]) == 0.35
                and float(protocol["rank_dependence_weight"]) == 0.2
                and float(protocol["rank_alignment_weight"]) == 0.0
                and protocol["uses_anomaly_alignment"] == "False"
                and int(protocol["remaining_benign_blocks_per_setup"]) == 520
                and int(protocol["trailing_window_blocks"]) == 25
                and int(protocol["trailing_minimum_blocks"]) == 6
                and float(protocol["stale_fpr_limit"]) == 0.01,
                "Section V-H reference, graph, trend, and drift-limit parameters match",
            )
        )
        manifest = _json(family_dir / "evidence_manifest.json")
        figure_records = manifest.get("rendered_figures", [])
        expected_figures = {
            "gallery_fig1_dse_heatmap.png",
            "gallery_fig1_dse_heatmap_legend.png",
            "gallery_fig4_full_stable_graph_network.png",
            "gallery_fig4_full_stable_graph_network_legend.png",
            "gallery_fig6c_lifecycle_benign_drift_trend.png",
            "gallery_fig6c_lifecycle_benign_drift_trend_legend.png",
        }
        recorded_figures = {Path(item["path"]).name for item in figure_records}
        notebook = _json(
            family_dir.parents[2] / "notebooks" / "exact_tcad_all_experiments.ipynb"
        )
        notebook_source = "\n".join(
            "".join(cell.get("source", []))
            for cell in notebook.get("cells", [])
            if cell.get("cell_type") == "code"
        )
        results.append(
            (
                "figures_3_4_6.composition_and_wording",
                recorded_figures == expected_figures
                and all(item.get("decoded_png") is True for item in figure_records)
                and "Cross-validation MCC" in notebook_source
                and "selected CINTAS configuration" in notebook_source
                and "Deployment MCC" not in notebook_source
                and "selected deployable CINTAS setting" not in notebook_source,
                "Figures 3, 4, and 6 include all main/legend assets and Figure 3 wording",
            )
        )
    except (IndexError, KeyError, OSError, TypeError, ValueError) as exc:
        results.append(("core.claim_files", False, f"could not audit core claims: {exc}"))
    return results


def _apple_claim_checks(family_dir: Path) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    try:
        envelope = _csv(family_dir / "figure_8_portability_envelope.csv")
        results.append(
            (
                "figure_8.portability_envelope",
                [row["stress_condition"] for row in envelope]
                == ["CACHE", "ATOMIC", "MEMBW", "BRANCH", "TLB"]
                and [round(float(row["mcc"]), 3) for row in envelope]
                == [0.917, 0.878, 0.754, 0.370, 0.367],
                "Figure 8 stress cases and MCC envelope match the manuscript",
            )
        )
        display_view = lambda value: (  # noqa: E731 - compact manuscript mapping
            value.upper()
            .replace("TIER1_ALT", "TIER1")
            .replace("_FULL", "-FULL")
            .replace("_CORE", "-CORE")
        )
        results.append(
            (
                "figure_8.printed_configurations",
                [
                    (
                        row["stress_condition"],
                        display_view(row["observability_view"]),
                        int(row["block_length"]),
                        int(row["selected_features"]),
                        f"{float(row['threshold_quantile']):.3f}",
                    )
                    for row in envelope
                ]
                == [
                    ("CACHE", "TIER2-FULL", 250, 8, "0.900"),
                    ("ATOMIC", "TIER2-FULL", 250, 3, "0.950"),
                    ("MEMBW", "TIER2-FULL", 150, 3, "0.990"),
                    ("BRANCH", "TIER1-FULL", 100, 10, "0.990"),
                    ("TLB", "TIER1-FULL", 100, 10, "0.990"),
                ],
                "Figure 8 view, N, k, and p annotations match every plotted stress condition",
            )
        )
        scope = _csv(family_dir / "section_vj_study_scope.csv")
        results.append(
            (
                "section_vj.study_scope",
                len(scope) == 5
                and sorted(int(row["available_features"]) for row in scope)
                == [7, 8, 11, 18, 45]
                and all(int(row["evaluated_workloads"]) == 4 for row in scope)
                and all(int(row["evaluated_stress_conditions"]) == 5 for row in scope),
                "Section V-J has five views spanning 7--45 features, four workloads, and five stress conditions",
            )
        )
        manifest = _json(family_dir / "evidence_manifest.json")
        rendered = manifest.get("rendered_figures", [])
        results.append(
            (
                "figure_8.composition",
                {Path(item["path"]).name for item in rendered}
                == {
                    "fig_apple_portability_envelope.png",
                    "fig_apple_portability_envelope_legend.png",
                }
                and all(item.get("decoded_png") is True for item in rendered),
                "Figure 8 includes its decodable main and legend assets",
            )
        )
        averages = _csv(family_dir / "section_vj_workload_averages.csv")
        values = {
            (row["observability_view"], row["stress_condition"]): round(float(row["mean_mcc"]), 3)
            for row in averages
        }
        results.append(
            (
                "section_vj.workload_averages",
                values
                == {
                    ("TIER2_FULL", "ATOMIC"): 0.921,
                    ("TIER2_CORE", "CACHE"): 0.985,
                    ("TIER2_FULL", "CACHE"): 0.994,
                    ("TIER2_FULL", "MEMBW"): 0.750,
                },
                "Section V-J workload averages match the manuscript",
            )
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        results.append(("apple.claim_files", False, f"could not audit Apple claims: {exc}"))
    return results


def _intel_claim_checks(
    family_dir: Path, manifest: dict[str, Any]
) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    try:
        claims = _json(family_dir / "figure7_claims.json")
        by_setup = {item["setup"]: item for item in claims["claims"]}
        results.append(
            (
                "figure_7.claims",
                claims.get("status") == "PASS"
                and by_setup["A"]["displayed_mean_percent"] == "0.58"
                and by_setup["A"]["displayed_sample_sd_percentage_points"] == "0.82"
                and by_setup["B"]["displayed_mean_percent"] == "0.83"
                and by_setup["B"]["displayed_sample_sd_percentage_points"] == "1.00"
                and by_setup["A"]["displayed_boundary_mean_percent"] == "0.26"
                and by_setup["B"]["displayed_boundary_mean_percent"] == "0.51"
                and by_setup["A"]["displayed_later_mean_percent"] == "0.68"
                and by_setup["B"]["displayed_later_mean_percent"] == "0.94"
                and all(item.get("matches_paper_at_reported_precision") is True for item in by_setup.values()),
                "Figure 7 overall, sample-SD, boundary, and later-block claims match",
            )
        )
        summary = _csv(
            family_dir / "intel_workload_orders" / "intel_workload_order_summary.csv"
        )
        current = {
            (row["setup"], row["metric"]): row
            for row in summary
            if row["decision_rule"] == "current"
            and row["metric"] in {
                "overall_benign_fpr",
                "boundary_block_fpr",
                "within_phase_fpr",
            }
        }
        results.append(
            (
                "figure_7.summary_trace",
                round(100.0 * float(current[("A", "overall_benign_fpr")]["mean"]), 2) == 0.58
                and round(100.0 * float(current[("A", "overall_benign_fpr")]["sample_sd"]), 2) == 0.82
                and round(100.0 * float(current[("B", "overall_benign_fpr")]["mean"]), 2) == 0.83
                and round(100.0 * float(current[("B", "overall_benign_fpr")]["sample_sd"]), 2) == 1.00
                and round(100.0 * float(current[("A", "boundary_block_fpr")]["mean"]), 2) == 0.26
                and round(100.0 * float(current[("B", "boundary_block_fpr")]["mean"]), 2) == 0.51
                and round(100.0 * float(current[("A", "within_phase_fpr")]["mean"]), 2) == 0.68
                and round(100.0 * float(current[("B", "within_phase_fpr")]["mean"]), 2) == 0.94,
                "All Section V-I Figure 7 values trace to the archived summary rows",
            )
        )
        run_rows = _csv(
            family_dir
            / "intel_workload_orders"
            / "intel_workload_order_run_results.csv"
        )
        current_rows = [
            row for row in run_rows if row.get("decision_rule") == "current"
        ]
        protocol = manifest.get("paper_protocol", {})
        results.append(
            (
                "section_v_i.protocol",
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
                }
                and len(current_rows) == 20
                and {
                    (row["setup"], int(row["replicate_index"]))
                    for row in current_rows
                }
                == {
                    (setup, replicate)
                    for setup in ("A", "B")
                    for replicate in range(1, 11)
                }
                and {int(row["calibration_block_count"]) for row in current_rows}
                == {104}
                and {int(row["n_blocks"]) for row in current_rows} == {156}
                and {
                    int(row["calibration_threshold_rank"]) for row in current_rows
                }
                == {104}
                and {row["threshold_rule"] for row in current_rows}
                == {"finite_sample_upper_rank_with_strict_exceedance"},
                "Section V-I configuration, replicate counts, block counts, and strict finite-sample threshold rule match",
            )
        )
        by_rule_metric = {
            (row["setup"], row["decision_rule"], row["metric"]): float(row["mean"])
            for row in summary
        }
        results.append(
            (
                "section_v_i.persistence_reduction",
                all(
                    by_rule_metric[(setup, "persistence", metric)]
                    < by_rule_metric[(setup, "current", metric)]
                    for setup in ("A", "B")
                    for metric in (
                        "overall_benign_fpr",
                        "boundary_block_fpr",
                        "within_phase_fpr",
                    )
                ),
                "The two-block persistence sensitivity lowers all three corresponding benign-FPR summaries for both setups",
            )
        )
        repeated = manifest.get("repeat_verification", {})
        repeat_file = _json(family_dir / "repeat_verification.json")
        results.append(
            (
                "intel.repeat_verification",
                repeated == repeat_file
                and repeated.get("status") == "PASS"
                and repeated.get("verification_coverage") == "COMPLETE"
                and repeated.get("failures") == 0
                and repeated.get("unverified_files") == 0,
                "Intel scientific outputs passed complete repeat comparison",
            )
        )
        figure = (
            family_dir
            / "intel_workload_orders"
            / "fig_intel_workload_order_variation.png"
        )
        figure_validation = manifest.get("figure_validation", {})
        facts = _png_facts(figure)
        results.append(
            (
                "figure_7.raster_validation",
                facts["decoded"] is True
                and facts["nonuniform"] is True
                and facts["height_px"] > facts["width_px"]
                and facts["height_px"] >= 1800
                and figure_validation.get("nonempty") is True
                and figure_validation.get("decoded_png") is True
                and figure_validation.get("layout") == "three_vertical_panels",
                "Figure 7 is a decoded, nonuniform, vertically stacked manuscript raster",
            )
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        results.append(("intel.claim_files", False, f"could not audit Intel claims: {exc}"))
    return results


RTL_TABLE_XI = [
    {
        "setup_event": "A/DROOP",
        "k": "15",
        "q": "15",
        "N": "1000",
        "LUT": "867",
        "FF": "244",
        "DSP": "38",
        "WNS_ns": "2.458",
        "fmax_MHz": "44.36",
        "power_mW": "158",
    },
    {
        "setup_event": "A/RH",
        "k": "20",
        "q": "8",
        "N": "550",
        "LUT": "863",
        "FF": "259",
        "DSP": "37",
        "WNS_ns": "2.569",
        "fmax_MHz": "44.58",
        "power_mW": "157",
    },
    {
        "setup_event": "B/DROOP",
        "k": "15",
        "q": "15",
        "N": "200",
        "LUT": "884",
        "FF": "242",
        "DSP": "38",
        "WNS_ns": "2.474",
        "fmax_MHz": "44.39",
        "power_mW": "158",
    },
    {
        "setup_event": "B/SPECTRE",
        "k": "30",
        "q": "8",
        "N": "700",
        "LUT": "907",
        "FF": "259",
        "DSP": "37",
        "WNS_ns": "2.110",
        "fmax_MHz": "43.69",
        "power_mW": "157",
    },
]


def _rtl_claim_checks(
    family_dir: Path, manifest: dict[str, Any]
) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    try:
        table = _csv(family_dir / "table_xi.csv")
        results.append(
            (
                "table_xi.values",
                table == RTL_TABLE_XI,
                "Table XI matches all four manuscript rows exactly",
            )
        )
        figure = _csv(family_dir / "figure_5_source.csv")
        results.append(
            (
                "figure_5.source",
                [row["tag"] for row in figure]
                == ["A_DROOP", "A_RH", "B_DROOP", "B_SPECTRE"]
                and all(row["timing_met"] == "True" for row in figure)
                and all(row["brams"] == "0" for row in figure)
                and all(row["power_confidence"] == "Low" for row in figure)
                and [round(float(row["luts_pct"]), 1) for row in figure]
                == [0.6, 0.6, 0.7, 0.7]
                and [round(float(row["ffs_pct"]), 1) for row in figure]
                == [0.1, 0.1, 0.1, 0.1]
                and [round(float(row["dsp_pct"]), 1) for row in figure]
                == [5.1, 5.0, 5.1, 5.0]
                and [round(float(row["iob_pct"]), 1) for row in figure]
                == [73.5, 73.5, 73.5, 73.5],
                "Figure 5 source contains all four cases and printed utilization percentages",
            )
        )
        rendered = family_dir / "figure_5.png"
        rendered_facts = _png_facts(rendered)
        rendered_record = manifest.get("rendered_figure", {})
        results.append(
            (
                "figure_5.raster",
                rendered_facts["decoded"] is True
                and rendered_facts["nonuniform"] is True
                and rendered_facts["width_px"] >= 1000
                and rendered_facts["height_px"] >= 900
                and rendered_record.get("decoded_png") is True
                and rendered_record.get("composition")
                == "timing_slack_panel_plus_four_case_resource_summary"
                and rendered_record.get("separate_legend_present") is True,
                "Figure 5 is a decoded timing/resource raster with its legend",
            )
        )
        manifest_checks = manifest.get("checks", {})
        required_checks = {
            "archived_summary_matches_reports",
            "figure_5_source_rows_complete",
            "figure_5_rendered_composition",
            "strict_archived_report_contract",
            "synthesis_source_matches_report_commit",
            "table_xi_matches_manuscript_values",
        }
        alignment = manifest.get("synthesis_source_alignment", [])
        results.append(
            (
                "rtl.internal_checks",
                manifest.get("status") == "PASS"
                and required_checks.issubset(manifest_checks)
                and all(manifest_checks.get(key) == "PASS" for key in required_checks)
                and manifest_checks.get("raw_report_byte_identity_required_for_future_runs") is False
                and isinstance(alignment, list)
                and len(alignment) == 2
                and all(item.get("match") is True for item in alignment),
                "RTL parser, report-contract, and source-alignment checks passed",
            )
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        results.append(("rtl.claim_files", False, f"could not audit RTL claims: {exc}"))
    return results


SENSITIVITY_RANGES = {
    "graph_parameter": {
        "mcc": ("0.940", "0.992"),
        "fpr_percent": ("0.77", "1.71"),
        "feature_jaccard_percent": ("37.9", "100.0"),
    },
    "ranking_term": {
        "mcc": ("0.798", "0.992"),
        "fpr_percent": ("0.77", "1.64"),
        "feature_jaccard_percent": ("53.8", "100.0"),
    },
}


def _find_sensitivity_claims(
    repo_root: Path, family_dir: Path, manifest: dict[str, Any]
) -> Path | None:
    candidates = [
        family_dir / "graph_sensitivity_claims.json",
        family_dir / "claims.json",
    ]
    audit = manifest.get("claim_audit")
    if isinstance(audit, dict) and isinstance(audit.get("path"), str):
        candidates.append(family_dir / audit["path"])
    for key in ("claims_path", "source_claims_path"):
        relative = manifest.get(key)
        if isinstance(relative, str):
            candidates.append(repo_root / relative)
    source = manifest.get("source_files")
    if isinstance(source, list):
        for record in source:
            if isinstance(record, dict) and str(record.get("path", "")).endswith(
                "graph_sensitivity_claims.json"
            ):
                candidates.append(repo_root / record["path"])
    candidates.append(
        repo_root
        / "results"
        / "notebook_run"
        / "graph_sensitivity"
        / "graph_sensitivity_claims.json"
    )
    return next((path for path in candidates if path.is_file()), None)


def _sensitivity_claim_checks(
    repo_root: Path, family_dir: Path, manifest: dict[str, Any]
) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    path = _find_sensitivity_claims(repo_root, family_dir, manifest)
    if path is None:
        return [
            (
                "sensitivity.claims_file",
                False,
                "no graph_sensitivity_claims.json payload could be resolved",
            )
        ]
    try:
        claims = _json(path)
        ranges_payload = claims.get("ranges")
        compact_schema = isinstance(ranges_payload, list)
        results.append(
            (
                "sensitivity.claim_status",
                claims.get("status") == "PASS"
                and (
                    all(
                        item.get("matches_paper_at_reported_precision") is True
                        for item in ranges_payload
                    )
                    if compact_schema
                    else claims.get("draft_claims_match_at_reported_precision") is True
                    and claims.get("complete_case_set") is True
                    and claims.get("variant_rows_complete_and_unique") is True
                ),
                "sensitivity completeness and manuscript-precision checks passed",
            )
        )
        invariance = claims.get("stability_threshold_invariance", {})
        comparisons = _csv(
            family_dir / "section_vd_stability_threshold_invariance.csv"
        )
        tolerance = invariance.get("comparison_policy", {}).get(
            "numeric_tolerance", {}
        )
        excluded_metrics = invariance.get("scope", {}).get(
            "excluded_from_decision_metric_claim", []
        )
        results.append(
            (
                "sensitivity.stability_threshold_invariance",
                invariance.get("claim_supported") is True
                and invariance.get("all_within_declared_tolerance") is True
                and invariance.get("all_numeric_values_strictly_equal") is True
                and [item.get("name") for item in invariance.get("decision_metrics", [])]
                == ["mcc", "fpr"]
                and invariance.get("parameter", {}).get("name") == "pi_min"
                and invariance.get("parameter", {}).get("baseline") == 0.5
                and invariance.get("parameter", {}).get("tested_values")
                == [0.375, 0.5, 0.625]
                and tolerance.get("relative_tolerance") == 0.0
                and tolerance.get("absolute_tolerance") == 1e-15
                and excluded_metrics
                == [
                    {
                        "metric": "feature_jaccard",
                        "reason": (
                            "Selected-feature overlap is a structural sensitivity output, "
                            "not a classifier decision metric; it changes for A_RH at "
                            "pi_min=0.625 even though MCC and FPR do not."
                        ),
                    }
                ]
                and len(comparisons) == 8
                and {
                    (row["case_id"], float(row["compared_pi_min"]))
                    for row in comparisons
                }
                == {
                    (case_id, pi_min)
                    for case_id in ("A_DROOP", "A_RH", "B_DROOP", "B_SPECTRE")
                    for pi_min in (0.375, 0.625)
                }
                and all(float(row["baseline_pi_min"]) == 0.5 for row in comparisons)
                and all(float(row["mcc_delta_raw"]) == 0.0 for row in comparisons)
                and all(float(row["fpr_delta_raw"]) == 0.0 for row in comparisons)
                and all(
                    row["all_decision_metrics_within_declared_tolerance"] == "True"
                    for row in comparisons
                ),
                "Changing pi_min from 0.5 to 0.375 or 0.625 preserves workload-aggregated MCC and benign FPR in all four cases",
            )
        )
        for family, expected_metrics in SENSITIVITY_RANGES.items():
            for metric, expected in expected_metrics.items():
                if compact_schema:
                    matching = [
                        item
                        for item in ranges_payload
                        if item.get("study_family") == family
                        and item.get("metric") == metric.removesuffix("_percent")
                    ]
                    payload = matching[0] if len(matching) == 1 else {}
                    observed = (
                        payload.get("paper_minimum_display"),
                        payload.get("paper_maximum_display"),
                    )
                    observed_extrema = (
                        payload.get("minimum_display"),
                        payload.get("maximum_display"),
                    )
                    precision_match = payload.get("matches_paper_at_reported_precision") is True
                else:
                    payload = claims["ranges"][family][metric]
                    observed = tuple(payload["draft_reference_display"])
                    observed_extrema = (
                        payload["observed"]["minimum"]["display"],
                        payload["observed"]["maximum"]["display"],
                    )
                    precision_match = payload.get("matches_draft_at_reported_precision") is True
                results.append(
                    (
                        f"sensitivity.{family}.{metric}",
                        observed == expected
                        and observed_extrema == expected
                        and precision_match,
                        f"{family} {metric} range is {expected[0]}--{expected[1]}",
                    )
                )
        reductions = claims.get("paper_specific_reduction_claims")
        if isinstance(reductions, list):
            observed_reductions = {
                item.get("case_id"): item.get("largest_reduction_variant")
                for item in reductions
                if item.get("matches") is True
            }
            results.append(
                (
                    "sensitivity.ranking_reduction_claims",
                    observed_reductions.get("A_DROOP") == "remove_centrality"
                    and observed_reductions.get("A_RH") == "remove_alignment",
                    "the two manuscript-specific largest-reduction statements match",
                )
            )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        results.append(
            ("sensitivity.claims", False, f"could not audit sensitivity claims: {exc}")
        )
    return results


def _fresh_clean_status(
    family: str,
    manifest: dict[str, Any],
    *,
    repo_root: Path,
    family_dir: Path,
) -> tuple[bool, str, str]:
    """Return (verified, evidence_class, explanation), conservatively."""

    declared_class = manifest.get("evidence_class")
    evidence_class = (
        str(declared_class)
        if isinstance(declared_class, str) and declared_class
        else "unspecified"
    )

    if family in {"core", "apple"}:
        if (
            manifest.get("fresh_clean_rerun_verified") is True
            and manifest.get("archival_status") not in {"REFERENCE_ONLY", None}
        ):
            return True, evidence_class, "manifest explicitly records a fresh clean rerun"
        return (
            False,
            evidence_class,
            f"archival_status={manifest.get('archival_status', 'UNSPECIFIED')}; "
            "a paper projection is not itself a fresh clean rerun",
        )

    if family == "rtl":
        fresh = manifest.get("fresh_vivado_synthesis") is True and manifest.get("status") == "PASS"
        return (
            fresh,
            evidence_class,
            "fresh Vivado synthesis is explicitly recorded"
            if fresh
            else "bundle is an archived report reanalysis, not a fresh Vivado synthesis",
        )

    if family == "intel":
        runs = manifest.get("clean_run_evidence")
        repeated = manifest.get("repeat_verification")
        clean = (
            manifest.get("status") == "COMPLETE_CLEAN_REPEAT_VERIFIED"
            and isinstance(runs, dict)
            and {"primary", "repeat"}.issubset(runs)
            and all(
                isinstance(run, dict)
                and run.get("clean_checkout_at_start") is True
                and run.get("repository_snapshot_unchanged_during_run") is True
                and run.get("git_status_at_finish") == []
                for run in runs.values()
            )
            and isinstance(repeated, dict)
            and repeated.get("status") == "PASS"
            and repeated.get("verification_coverage") == "COMPLETE"
        )
        return (
            clean,
            "clean_repeat_verified" if evidence_class == "unspecified" else evidence_class,
            "two clean, unchanged runs passed complete scientific comparison"
            if clean
            else "complete clean repeat evidence was not established",
        )

    if family == "sensitivity":
        clean_evidence = manifest.get("clean_run_evidence")
        embedded_clean = (
            isinstance(clean_evidence, dict)
            and clean_evidence.get("git_dirty_at_start") is False
            and clean_evidence.get("git_status_at_start") == []
            and clean_evidence.get("git_status_at_finish") == []
            and clean_evidence.get("source_and_inputs_unchanged_during_run") is True
            and clean_evidence.get("repository_commit")
            == clean_evidence.get("repository_commit_at_finish")
            and clean_evidence.get("archival_provenance_status") == "PASS"
            and clean_evidence.get("claim_status") == "PASS"
        )
        run_candidates = [family_dir / "run_manifest.json"]
        for key in ("run_manifest_path", "source_run_manifest_path"):
            relative = manifest.get(key)
            if isinstance(relative, str):
                run_candidates.append(repo_root / relative)
        for record in manifest.get("source_run_manifests", []):
            if isinstance(record, dict) and isinstance(record.get("path"), str):
                run_candidates.append(repo_root / record["path"])
        run_candidates.append(
            repo_root / "results" / "notebook_run" / "graph_sensitivity" / "run_manifest.json"
        )
        run_path = next((path for path in run_candidates if path.is_file()), None)
        explicit = manifest.get("fresh_clean_rerun_verified") is True
        run_clean = False
        if run_path is not None:
            try:
                run = _json(run_path)
                run_clean = (
                    run.get("git_dirty_at_start") is False
                    and run.get("git_status_at_start") == []
                    and run.get("git_status_at_finish") == []
                    and run.get("source_and_inputs_unchanged_during_run") is True
                    and run.get("repository_commit")
                    == run.get("repository_commit_at_finish")
                    and run.get("archival_provenance_status") == "PASS"
                    and run.get("claim_status") == "PASS"
                )
            except (OSError, ValueError):
                run_clean = False
        verification_scope = manifest.get("verification_scope", {})
        scope_confirms = (
            isinstance(verification_scope, dict)
            and verification_scope.get("fresh_clean_run_recorded") is True
            and verification_scope.get("source_archive_hashes_verified") is True
        )
        clean = explicit or (embedded_clean and scope_confirms) or run_clean
        derived_class = evidence_class
        if derived_class == "unspecified" and clean:
            derived_class = "clean_archival_run"
        return (
            clean,
            derived_class,
            "clean, unchanged sensitivity run and claim audit are recorded"
            if clean
            else "clean sensitivity-run provenance was not established",
        )

    return False, evidence_class, "no fresh-clean evidence rule is defined"


def audit_family(repo_root: Path, bundle_root: Path, family: str) -> dict[str, Any]:
    family_dir = bundle_root / family
    coverage_checks: list[dict[str, str]] = []
    traceability_checks: list[dict[str, str]] = []
    claim_checks: list[dict[str, str]] = []

    if not family_dir.is_dir():
        _add_check(
            coverage_checks,
            "bundle.present",
            False,
            f"missing bundle directory: reproducibility/paper_results/{family}",
        )
        return {
            "family": family,
            "present": False,
            "paper_items": [],
            "evidence_class": "missing",
            "archival_status": "MISSING",
            "coverage_status": "FAIL",
            "traceability_status": "FAIL",
            "paper_claims_status": "FAIL",
            "fresh_clean_rerun_verified": False,
            "fresh_clean_rerun_status": "NOT_ESTABLISHED",
            "fresh_clean_rerun_explanation": "bundle is missing",
            "status": "FAIL",
            "checks": {
                "coverage": coverage_checks,
                "traceability": traceability_checks,
                "paper_claims": claim_checks,
            },
        }

    _add_check(coverage_checks, "bundle.present", True, "bundle directory is present")
    manifest_path = _manifest_path(family_dir, family)
    if manifest_path is None:
        _add_check(
            coverage_checks,
            "manifest.present",
            False,
            "no evidence_manifest.json or evidence.json is present",
        )
        manifest: dict[str, Any] = {}
    else:
        _add_check(
            coverage_checks,
            "manifest.present",
            True,
            f"using {manifest_path.name}",
        )
        try:
            manifest = _json(manifest_path)
            _add_check(
                traceability_checks,
                "manifest.schema",
                manifest.get("schema_version") == 1,
                "manifest schema_version is 1",
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            manifest = {}
            _add_check(
                traceability_checks,
                "manifest.parse",
                False,
                f"manifest could not be parsed: {exc}",
            )

    required_ok, required_message = _required_file_check(family_dir, family)
    _add_check(coverage_checks, "bundle.required_files", required_ok, required_message)

    paper_items = _manifest_items(manifest)
    expected_items = EXPECTED_PAPER_ITEMS[family]
    items_ok = bool(paper_items) and expected_items.issubset(paper_items)
    if family == "sensitivity" and not paper_items:
        # A sensitivity manifest may encode the paper sections in its claims
        # payload.  Exact range validation below remains mandatory.
        items_ok = _find_sensitivity_claims(repo_root, family_dir, manifest) is not None
    _add_check(
        coverage_checks,
        "bundle.paper_items",
        items_ok,
        "manifest covers all expected paper items"
        if items_ok
        else "manifest paper-item scope is absent or incomplete",
    )

    record_key, records = _declared_output_records(manifest)
    _add_check(
        traceability_checks,
        "outputs.declared",
        bool(records),
        f"manifest declares {len(records)} compact artifacts via {record_key}",
    )
    declared_paths = _declared_relative_paths(records, family)
    missing_declarations = sorted(REQUIRED_FILES[family] - declared_paths)
    _add_check(
        traceability_checks,
        "outputs.declaration_coverage",
        not missing_declarations,
        "every required paper-facing file has a declared hash"
        if not missing_declarations
        else "required files without declared hashes: " + ", ".join(missing_declarations),
    )
    for index, record in enumerate(records):
        passed, message = _check_record(
            record,
            base=_output_base(
                bundle_root=bundle_root,
                family_dir=family_dir,
                family=family,
                record=record,
            ),
            record_name=f"{record_key}[{index}]",
        )
        _add_check(
            traceability_checks,
            f"outputs.{index}.identity",
            passed,
            message,
        )
        if isinstance(record, dict) and "status" in record:
            _add_check(
                traceability_checks,
                f"outputs.{index}.status",
                record.get("status") == "PASS",
                f"{record.get('path', 'output')} declares status=PASS",
            )
        if passed and isinstance(record, dict) and record.get("row_count") is not None:
            try:
                path = _relative_target(
                    _output_base(
                        bundle_root=bundle_root,
                        family_dir=family_dir,
                        family=family,
                        record=record,
                    ),
                    record["path"],
                )
                row_count = len(_csv(path))
                count_ok = row_count == record["row_count"]
                count_message = (
                    f"{record['path']} has declared row_count={record['row_count']}"
                )
            except (KeyError, OSError, TypeError, ValueError) as exc:
                count_ok = False
                count_message = f"could not verify declared row count: {exc}"
            _add_check(
                traceability_checks,
                f"outputs.{index}.row_count",
                count_ok,
                count_message,
            )

    claim_audit = manifest.get("claim_audit")
    if isinstance(claim_audit, dict):
        passed, message = _check_record(
            claim_audit,
            base=family_dir,
            record_name="claim_audit",
        )
        _add_check(
            traceability_checks,
            "claim_audit.identity",
            passed,
            message,
        )
        _add_check(
            traceability_checks,
            "claim_audit.status",
            claim_audit.get("status") == "PASS",
            "claim audit declares status=PASS",
        )

    for field in (
        "source_files",
        "source_run_manifests",
        "sources",
        "inputs",
        "environment_files",
        "rendered_figures",
    ):
        source_records = manifest.get(field)
        if not isinstance(source_records, list):
            continue
        for index, record in enumerate(source_records):
            passed, message = _check_record(
                record,
                base=repo_root,
                record_name=f"{field}[{index}]",
            )
            _add_check(
                traceability_checks,
                f"{field}.{index}.metadata",
                passed,
                message,
            )

    if family == "core":
        raw_claims = _core_claim_checks(family_dir)
    elif family == "apple":
        raw_claims = _apple_claim_checks(family_dir)
    elif family == "intel":
        raw_claims = _intel_claim_checks(family_dir, manifest)
    elif family == "rtl":
        raw_claims = _rtl_claim_checks(family_dir, manifest)
    else:
        raw_claims = _sensitivity_claim_checks(repo_root, family_dir, manifest)
    for check_id, passed, message in raw_claims:
        _add_check(claim_checks, check_id, passed, message)

    fresh, evidence_class, fresh_explanation = _fresh_clean_status(
        family,
        manifest,
        repo_root=repo_root,
        family_dir=family_dir,
    )
    coverage_status = "PASS" if _all_pass(coverage_checks) else "FAIL"
    traceability_status = "PASS" if _all_pass(traceability_checks) else "FAIL"
    paper_claims_status = "PASS" if claim_checks and _all_pass(claim_checks) else "FAIL"
    status = (
        "PASS"
        if coverage_status == traceability_status == paper_claims_status == "PASS"
        else "FAIL"
    )
    archival_status = manifest.get("archival_status")
    if not isinstance(archival_status, str):
        archival_status = (
            "CLEAN_REPEAT_VERIFIED"
            if fresh
            else "ARCHIVED_REANALYSIS"
            if family == "rtl"
            else "UNSPECIFIED"
        )
    return {
        "family": family,
        "present": True,
        "paper_items": paper_items,
        "evidence_class": evidence_class,
        "archival_status": archival_status,
        "coverage_status": coverage_status,
        "traceability_status": traceability_status,
        "paper_claims_status": paper_claims_status,
        "fresh_clean_rerun_verified": fresh,
        "fresh_clean_rerun_status": "PASS" if fresh else "NOT_ESTABLISHED",
        "fresh_clean_rerun_explanation": fresh_explanation,
        "status": status,
        "checks": {
            "coverage": coverage_checks,
            "traceability": traceability_checks,
            "paper_claims": claim_checks,
        },
    }


def audit_repository(
    repo_root: Path = REPO_ROOT,
    *,
    bundle_root: Path | None = None,
    families: Sequence[str] | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    if bundle_root is None:
        bundle_root = repo_root / "reproducibility" / "paper_results"
    else:
        bundle_root = bundle_root.resolve()
    selected = tuple(families or EXPECTED_FAMILIES)
    invalid = sorted(set(selected) - set(EXPECTED_FAMILIES))
    if invalid:
        raise ValueError(f"unknown paper-result families: {', '.join(invalid)}")

    results = [audit_family(repo_root, bundle_root, family) for family in selected]
    coverage_pass = all(item["coverage_status"] == "PASS" for item in results)
    traceability_pass = all(
        item["traceability_status"] == "PASS"
        and item["paper_claims_status"] == "PASS"
        for item in results
    )
    all_fresh = bool(results) and all(
        item["fresh_clean_rerun_verified"] is True for item in results
    )
    artifact_status = "PASS" if coverage_pass and traceability_pass else "FAIL"
    limitations = [
        f"{item['family']}: {item['fresh_clean_rerun_explanation']}"
        for item in results
        if not item["fresh_clean_rerun_verified"]
    ]
    return {
        "schema_version": 1,
        "audit_scope": "paper-facing compact result bundles",
        "families_requested": list(selected),
        "families_present": [item["family"] for item in results if item["present"]],
        "coverage_status": "PASS" if coverage_pass else "FAIL",
        "traceability_status": "PASS" if traceability_pass else "FAIL",
        "fresh_clean_rerun_status": "PASS" if all_fresh else "NOT_ESTABLISHED",
        "all_results_fresh_clean_rerun_verified": all_fresh,
        "status": artifact_status,
        "status_interpretation": (
            "PASS certifies compact-bundle coverage, declared artifact integrity, and "
            "paper-claim checks only. It does not certify fresh clean reruns unless "
            "fresh_clean_rerun_status is also PASS."
        ),
        "families": {item["family"]: item for item in results},
        "fresh_clean_rerun_limitations": limitations,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="repository root (default: inferred from this script)",
    )
    parser.add_argument(
        "--bundle-root",
        type=Path,
        help="paper-results directory (default: <repo>/reproducibility/paper_results)",
    )
    parser.add_argument(
        "--family",
        action="append",
        choices=EXPECTED_FAMILIES,
        help="audit only this family; repeat to select several (default: all five)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="also write the JSON report to this path",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = audit_repository(
        args.repo_root,
        bundle_root=args.bundle_root,
        families=args.family,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
