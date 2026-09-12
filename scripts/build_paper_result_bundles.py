#!/usr/bin/env python3
"""Build compact, paper-facing result bundles from notebook outputs.

The notebook intentionally emits detailed fold, graph, and diagnostic records.
Reviewers should not have to compare every intermediate file to decide whether
the results printed in the paper were reproduced.  This utility projects the
notebook outputs into small tables that correspond directly to Section V.

The projected numeric tables are comparison targets.  Rendered PNG hashes are
recorded only as provenance because fonts and renderers can change PNG bytes
without changing the scientific result.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import tempfile
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Sequence

from PIL import Image, ImageStat


CORE_OUTPUTS = (
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
    "evidence_manifest.json",
)

APPLE_OUTPUTS = (
    "figure_8_portability_envelope.csv",
    "section_vj_workload_averages.csv",
    "section_vj_study_scope.csv",
    "evidence_manifest.json",
)

PAPER_EVENT_ORDER = {
    ("A", "DROOP"): 0,
    ("A", "RH"): 1,
    ("B", "DROOP"): 2,
    ("B", "SPECTRE"): 3,
}
APPLE_SCENARIO_ORDER = {
    "CACHE": 0,
    "ATOMIC": 1,
    "MEMBW": 2,
    "BRANCH": 3,
    "TLB": 4,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size > 1024:
        return False
    return path.read_bytes().startswith(b"version https://git-lfs.github.com/spec/v1")


def require_materialized(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"Required paper-result source is missing: {path}")
    if is_lfs_pointer(path):
        raise RuntimeError(
            f"Paper-result source is still a Git LFS pointer: {path}. "
            "Fetch the matching reproduction scope first."
        )
    return path


def read_csv(path: Path) -> list[dict[str, str]]:
    require_materialized(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    require_materialized(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def number(row: dict[str, str], name: str) -> float:
    value = row.get(name, "")
    if value is None or str(value).strip() == "":
        return math.nan
    return float(value)


def integer(row: dict[str, str], name: str) -> int:
    value = number(row, name)
    if not math.isfinite(value) or not value.is_integer():
        raise ValueError(f"Expected integer-valued column {name!r}, got {row.get(name)!r}")
    return int(value)


def same_number(left: str, right: str) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)


def source_record(repo_root: Path, path: Path, *, role: str) -> dict[str, Any]:
    require_materialized(path)
    try:
        relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        relative = path.resolve().as_posix()
    return {
        "path": relative,
        "role": role,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def rendered_figure_record(repo_root: Path, path: Path, *, role: str) -> dict[str, Any]:
    require_materialized(path)
    try:
        with Image.open(path) as opened:
            if opened.format != "PNG":
                raise ValueError(f"Expected PNG paper figure: {path}")
            opened.verify()
        with Image.open(path) as opened:
            width, height = opened.size
            sample = opened.convert("L")
            sample.thumbnail((256, 256))
            variance = float(ImageStat.Stat(sample).var[0])
    except OSError as exc:
        raise ValueError(f"Paper figure cannot be decoded: {path}") from exc
    if width < 100 or height < 40 or variance <= 1.0:
        raise ValueError(
            f"Paper figure is too small or visually uniform: {path} "
            f"({width}x{height}, variance={variance})"
        )
    return {
        **source_record(repo_root, path, role=role),
        "width_px": width,
        "height_px": height,
        "decoded_png": True,
        "nonuniform": True,
    }


def notebook_code(repo_root: Path) -> str:
    notebook_path = repo_root / "notebooks" / "exact_tcad_all_experiments.ipynb"
    notebook = read_json(notebook_path)
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook.get("cells", [])
        if cell.get("cell_type") == "code"
    )


def validate_figure_3_wording(repo_root: Path) -> None:
    source = notebook_code(repo_root)
    required = ("Cross-validation MCC", "selected CINTAS configuration")
    forbidden = ("Deployment MCC", "selected deployable CINTAS setting")
    missing = [label for label in required if label not in source]
    stale = [label for label in forbidden if label in source]
    if missing or stale:
        raise ValueError(
            f"Figure 3 wording contract failed; missing={missing}, stale={stale}"
        )


def notebook_numeric_constants(repo_root: Path, names: Sequence[str]) -> dict[str, float]:
    values: dict[str, float] = {}
    notebook = read_json(repo_root / "notebooks" / "exact_tcad_all_experiments.ipynb")
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        tree = ast.parse("".join(cell.get("source", [])))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in names:
                    value = ast.literal_eval(node.value)
                    if not isinstance(value, (int, float)):
                        raise ValueError(f"Notebook constant {target.id} is not numeric")
                    values[target.id] = float(value)
    missing = sorted(set(names) - set(values))
    if missing:
        raise ValueError(f"Notebook constants are missing: {missing}")
    return values


def output_record(output_root: Path, path: Path, paper_items: Sequence[str]) -> dict[str, Any]:
    return {
        "path": path.relative_to(output_root).as_posix(),
        "paper_items": list(paper_items),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def manifest_provenance(repo_root: Path, path: Path) -> dict[str, Any]:
    require_materialized(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        displayed_path = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        displayed_path = path.resolve().as_posix()
    return {
        "path": displayed_path,
        "sha256": sha256_file(path),
        "git_commit": payload.get("repository_commit", payload.get("git_commit")),
        "git_dirty_at_start": payload.get("git_dirty_at_start", payload.get("git_dirty")),
    }


def evidence_class(manifests: Sequence[dict[str, Any]]) -> tuple[str, str]:
    clean = bool(manifests) and all(
        item.get("git_dirty_at_start") is False and bool(item.get("git_commit"))
        for item in manifests
    )
    if clean:
        return "clean_run_projection", "CLEAN_RUN"
    return "historical_non_archival_reference", "REFERENCE_ONLY"


def counted_feature_channels(path: Path) -> int:
    require_materialized(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        header = next(csv.reader(handle))
    return sum(
        bool(str(name).strip()) and not str(name).strip().startswith("Unnamed:")
        for name in header
    )


def event_sort(row: dict[str, Any]) -> tuple[Any, ...]:
    key = (str(row["setup"]), str(row.get("event", row.get("scenario"))))
    return (PAPER_EVENT_ORDER.get(key, 99),)


def selected_configuration_rows(
    selected_source: Path,
    available_channels: dict[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    source_rows = read_csv(selected_source)
    rows: list[dict[str, Any]] = []
    for row in source_rows:
        setup = row["setup"]
        event = row["scenario"]
        retained = integer(row, "n_selected_features")
        available = available_channels[setup]
        rows.append(
            {
                "setup": setup,
                "event": event,
                "view": "Transient" if event == "DROOP" else "Standard",
                "selected_features": retained,
                "available_channels": available,
                "retained_percent": 100.0 * retained / available,
                "block_length": integer(row, "window_size"),
                "aggregation": row["agg_mode"],
                "score_mixture": number(row, "lambda_res"),
                "weighting": "inverse" if row["weight_mode"] == "inv_var" else row["weight_mode"],
                "fixed_point_q": integer(row, "fixed_point_q"),
                "threshold_quantile": number(row, "p_quantile"),
                "roc_auc": number(row, "auc_roc"),
                "auc_pr": number(row, "auc_pr"),
                "f1": number(row, "f1"),
                "mcc": number(row, "mcc"),
                "fpr": number(row, "fpr"),
                "area_overhead_percent": number(row, "hw_setup_b_area_overhead_pct"),
                "idle_power_overhead_percent": number(row, "hw_idle_power_overhead_pct"),
            }
        )
    rows.sort(key=event_sort)
    if {(row["setup"], row["event"]) for row in rows} != set(PAPER_EVENT_ORDER):
        raise ValueError("Selected-configuration table does not contain the four paper setup/event rows.")
    return rows, source_rows


def build_dse_envelope(
    summary_source: Path,
    selected_rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    for row in read_csv(summary_source):
        key = (
            row["setup"],
            row["scenario"],
            integer(row, "top_k"),
            integer(row, "window_size"),
        )
        candidate = grouped.setdefault(
            key,
            {
                "setup": key[0],
                "event": key[1],
                "feature_budget": key[2],
                "block_length": key[3],
                "best_mcc": -math.inf,
                "best_balanced_accuracy": -math.inf,
                "best_f1": -math.inf,
                "min_fpr": math.inf,
            },
        )
        candidate["best_mcc"] = max(candidate["best_mcc"], number(row, "mcc"))
        candidate["best_balanced_accuracy"] = max(
            candidate["best_balanced_accuracy"], number(row, "bal_acc")
        )
        candidate["best_f1"] = max(candidate["best_f1"], number(row, "f1"))
        candidate["min_fpr"] = min(candidate["min_fpr"], number(row, "fpr"))

    selected_by_event = {
        (row["setup"], row["event"]): (row["selected_features"], row["block_length"])
        for row in selected_rows
    }
    rows = list(grouped.values())
    for row in rows:
        selected = selected_by_event[(row["setup"], row["event"])]
        row["selected_configuration"] = int(
            (row["feature_budget"], row["block_length"]) == selected
        )
    rows.sort(key=lambda row: (*event_sort(row), row["feature_budget"], row["block_length"]))
    if sum(row["selected_configuration"] for row in rows) != 4:
        raise ValueError("Figure 3 projection must mark exactly one selected configuration per panel.")
    return rows


def build_workload_results(source: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_csv(source):
        rows.append(
            {
                "setup": row["setup"],
                "event": row["scenario"],
                "workloads": integer(row, "workloads"),
                "mean_mcc": number(row, "mean_mcc"),
                "minimum_mcc": number(row, "min_mcc"),
                "mean_fpr": number(row, "mean_fpr"),
                "maximum_fpr": number(row, "max_fpr"),
                "mean_mcc_gap_to_workload_oracle": number(row, "mean_mcc_gap_to_oracle"),
                "maximum_mcc_gap_to_workload_oracle": number(row, "max_mcc_gap_to_oracle"),
            }
        )
    rows.sort(key=event_sort)
    return rows


def build_workload_details(source: Path) -> list[dict[str, Any]]:
    rows = [
        {
            "setup": row["setup"],
            "event": row["scenario"],
            "workload": row["workload"],
            "mcc": number(row, "mcc"),
            "fpr": number(row, "fpr"),
            "oracle_mcc": number(row, "oracle_mcc"),
            "oracle_fpr": number(row, "oracle_fpr"),
            "mcc_gap_to_workload_oracle": number(row, "mcc_gap_to_oracle"),
        }
        for row in read_csv(source)
    ]
    rows.sort(key=lambda row: (*event_sort(row), row["workload"]))
    if len(rows) != 52:
        raise ValueError(f"Expected 52 selected-setting workload rows, found {len(rows)}")
    return rows


def build_feature_budget_table(source: Path) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(source):
        grouped[(row["setup"], row["scenario"])].append(row)

    output: list[dict[str, Any]] = []
    for (setup, event), rows in grouped.items():
        by_budget = sorted(rows, key=lambda row: integer(row, "top_k"))
        best_mcc = max(number(row, "best_mcc") for row in by_budget)
        saturation = next(
            row for row in by_budget if number(row, "best_mcc") >= best_mcc - 0.01
        )
        minimum = by_budget[0]
        maximum = by_budget[-1]
        output.append(
            {
                "setup": setup,
                "event": event,
                "minimum_budget": integer(minimum, "top_k"),
                "maximum_budget": integer(maximum, "top_k"),
                "saturation_budget": integer(saturation, "top_k"),
                "mcc_at_minimum_budget": number(minimum, "best_mcc"),
                "mcc_at_saturation_budget": number(saturation, "best_mcc"),
                "mcc_at_maximum_budget": number(maximum, "best_mcc"),
                "area_at_saturation_percent": number(
                    saturation, "mean_area_overhead_pct"
                ),
                "power_at_saturation_percent": number(
                    saturation, "mean_idle_power_overhead_pct"
                ),
                "area_at_maximum_percent": number(maximum, "mean_area_overhead_pct"),
                "power_at_maximum_percent": number(
                    maximum, "mean_idle_power_overhead_pct"
                ),
            }
        )
    output.sort(key=event_sort)
    return output


def combine_graph_tables(source_root: Path, suffix: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for setup in ("A", "B"):
        path = source_root / "tcad_ablation" / "causal" / f"SETUP_{setup}_{suffix}.csv"
        for row in read_csv(path):
            output.append({"setup": setup, **row})
    identity = ("src", "dst") if suffix == "causal_edges" else ("feature",)
    output.sort(key=lambda row: (row["setup"], *(row[column] for column in identity)))
    return output


def project_rows(source: Path, columns: Sequence[str], sort_columns: Sequence[str]) -> list[dict[str, Any]]:
    rows = [{name: row[name] for name in columns} for row in read_csv(source)]
    rows.sort(key=lambda row: tuple(row[name] for name in sort_columns))
    return rows


def build_integer_error(selected_source_rows: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    rows = [
        {
            "setup": row["setup"],
            "event": row["scenario"],
            "fixed_point_q": integer(row, "fixed_point_q"),
            "mean_absolute_score_error": number(row, "fp_mae"),
            "maximum_absolute_score_error": number(row, "fp_max_abs"),
            "view": "Transient" if row["scenario"] == "DROOP" else "Standard",
            "observations_compared": 5000,
        }
        for row in selected_source_rows
    ]
    rows.sort(key=event_sort)
    return rows


def build_analytical_cost(
    summary_source: Path,
    selected_source_rows: Sequence[dict[str, str]],
    available_channels: dict[str, int],
) -> list[dict[str, Any]]:
    summary = read_csv(summary_source)
    match_columns = (
        "setup",
        "scenario",
        "top_k",
        "window_size",
        "agg_mode",
        "lambda_res",
        "p_quantile",
        "weight_mode",
        "fixed_point_q",
    )
    output: list[dict[str, Any]] = []
    for selected in selected_source_rows:
        matches = []
        for row in summary:
            equal = True
            for name in match_columns:
                if name in {"top_k", "window_size", "lambda_res", "p_quantile", "fixed_point_q"}:
                    equal = equal and same_number(row[name], selected[name])
                else:
                    equal = equal and row[name] == selected[name]
            if equal:
                matches.append(row)
        if len(matches) != 1:
            raise ValueError(
                f"Expected one analytical-cost row for {selected['setup']}/{selected['scenario']}; "
                f"found {len(matches)}."
            )
        row = matches[0]
        setup = selected["setup"]
        retained = integer(selected, "n_selected_features")
        output.append(
            {
                "setup": setup,
                "event": selected["scenario"],
                "selected_features": retained,
                "available_channels": available_channels[setup],
                "feature_reduction_percent": 100.0 * (1.0 - retained / available_channels[setup]),
                "adders": integer(row, "hw_add_count"),
                "multipliers": integer(row, "hw_mult_count"),
                "serial_cycles": integer(row, "hw_estimated_serial_cycles"),
                "area_overhead_percent": number(row, "hw_setup_b_area_overhead_pct"),
                "idle_power_overhead_percent": number(row, "hw_idle_power_overhead_pct"),
            }
        )
    output.sort(key=event_sort)
    return output


def build_table_x_citadel_row(
    selected_rows: Sequence[dict[str, Any]],
    analytical_cost: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "method": "CITADEL",
            "minimum_runtime_features": min(row["selected_features"] for row in selected_rows),
            "maximum_runtime_features": max(row["selected_features"] for row in selected_rows),
            "edge_scoring": "Fixed-point CINTAS",
            "minimum_area_overhead_percent": min(row["area_overhead_percent"] for row in analytical_cost),
            "maximum_area_overhead_percent": max(row["area_overhead_percent"] for row in analytical_cost),
            "minimum_idle_power_overhead_percent": min(
                row["idle_power_overhead_percent"] for row in analytical_cost
            ),
            "maximum_idle_power_overhead_percent": max(
                row["idle_power_overhead_percent"] for row in analytical_cost
            ),
            "drift_check": "yes",
            "deployment_scope": "Stable graph, DSE, frozen workload, and drift checks.",
        }
    ]


def build_cost_basis(repo_root: Path) -> list[dict[str, Any]]:
    constants = notebook_numeric_constants(
        repo_root,
        ("SETUP_B_AREA_MM2", "IDLE_POWER_W"),
    )
    return [
        {
            "operator_bit_width": 16,
            "area_normalization_mm2": constants["SETUP_B_AREA_MM2"],
            "idle_power_normalization_w": constants["IDLE_POWER_W"],
        }
    ]


def rolling_mean(values: Sequence[float], window: int, minimum: int) -> list[float | str]:
    current: deque[float] = deque()
    total = 0.0
    output: list[float | str] = []
    for value in values:
        current.append(value)
        total += value
        if len(current) > window:
            total -= current.popleft()
        output.append(total / len(current) if len(current) >= minimum else "")
    return output


def build_lifecycle_tables(source: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = [
        row
        for row in read_csv(source)
        if row["scenario"].upper() == "BENIGN" and "later" in row["phase"].lower()
    ]
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["setup"], row["method"])].append(row)

    trend: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    rank_jaccard_source = {
        (row["setup"], row["method"]): number(row, "rank_jaccard")
        for row in read_csv(source.parent / "lifecycle_recalibration_summary.csv")
    }
    for (setup, method), group in sorted(grouped.items()):
        ordered = sorted(group, key=lambda row: (row["workload"], integer(row, "window_idx")))
        predictions = [integer(row, "pred") for row in ordered]
        summary.append(
            {
                "setup": setup,
                "method": method,
                "benign_blocks": len(ordered),
                "false_positive_blocks": sum(predictions),
                "fpr": sum(predictions) / len(ordered),
                "rank_jaccard": rank_jaccard_source[(setup, method)],
            }
        )
        if method != "frozen":
            continue
        scores = [number(row, "score_win") for row in ordered]
        score_trend = rolling_mean(scores, window=25, minimum=6)
        fpr_trend = rolling_mean([float(value) for value in predictions], window=25, minimum=6)
        for index, (row, score_mean, fpr_mean) in enumerate(
            zip(ordered, score_trend, fpr_trend)
        ):
            trend.append(
                {
                    "setup": setup,
                    "field_window": index,
                    "workload": row["workload"],
                    "window_index_within_workload": integer(row, "window_idx"),
                    "score": number(row, "score_win"),
                    "frozen_threshold": number(row, "threshold"),
                    "false_positive": integer(row, "pred"),
                    "score_trailing_mean_25": score_mean,
                    "fpr_trailing_mean_25": fpr_mean,
                }
            )
    summary.sort(key=lambda row: (row["setup"], row["method"]))
    return trend, summary


def build_lifecycle_protocol(
    repo_root: Path,
    config_source: Path,
    lifecycle_summary: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    config = read_json(config_source)
    source = notebook_code(repo_root)
    required_snippets = (
        "n_bootstraps=6",
        '0.45 * nodes_df.get("graph_centrality"',
        '0.35 * nodes_df.get("edge_stability"',
        '0.20 * nodes_df.get("conditional_dependence"',
    )
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise ValueError(f"Lifecycle source contract is missing: {missing}")
    field_blocks = {int(row["benign_blocks"]) for row in lifecycle_summary}
    if field_blocks != {520}:
        raise ValueError(f"Unexpected lifecycle field-block counts: {field_blocks}")
    return [
        {
            "selected_features": int(config["top_k"]),
            "block_length": int(config["window_size"]),
            "aggregation": config["agg_mode"],
            "weighting": config["weight_mode"],
            "score_mixture": float(config["lambda_res"]),
            "threshold_quantile": float(config["p_quantile"]),
            "initial_reference_fraction": float(config["calibration_frac"]),
            "remaining_fraction": 1.0 - float(config["calibration_frac"]),
            "graph_subsamples": 6,
            "rank_centrality_weight": 0.45,
            "rank_stability_weight": 0.35,
            "rank_dependence_weight": 0.20,
            "rank_alignment_weight": 0.0,
            "uses_anomaly_alignment": False,
            "remaining_benign_blocks_per_setup": 520,
            "trailing_window_blocks": 25,
            "trailing_minimum_blocks": 6,
            "stale_fpr_limit": 0.01,
        }
    ]


def build_apple_envelope(source: Path) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(source):
        grouped[row["scenario"]].append(row)

    def rank(row: dict[str, str]) -> tuple[Any, ...]:
        return (
            -number(row, "mcc"),
            -number(row, "bal_acc"),
            -number(row, "auc_pr"),
            -number(row, "auc_roc"),
            -number(row, "f1"),
            number(row, "fpr"),
            row["observability"],
            row["setup"],
            integer(row, "window_size"),
            row["agg_mode"],
            number(row, "lambda_res"),
            number(row, "p_quantile"),
            integer(row, "top_k"),
            row["weight_mode"],
            integer(row, "fixed_point_q"),
        )

    output: list[dict[str, Any]] = []
    for scenario, rows in grouped.items():
        row = min(rows, key=rank)
        output.append(
            {
                "stress_condition": scenario,
                "observability_view": row["observability"],
                "available_features": integer(row, "available_features"),
                "selected_features": integer(row, "n_selected_features"),
                "block_length": integer(row, "window_size"),
                "aggregation": row["agg_mode"],
                "score_mixture": number(row, "lambda_res"),
                "threshold_quantile": number(row, "p_quantile"),
                "weighting": row["weight_mode"],
                "fixed_point_q": integer(row, "fixed_point_q"),
                "roc_auc": number(row, "auc_roc"),
                "auc_pr": number(row, "auc_pr"),
                "f1": number(row, "f1"),
                "balanced_accuracy": number(row, "bal_acc"),
                "mcc": number(row, "mcc"),
                "fpr": number(row, "fpr"),
            }
        )
    output.sort(key=lambda row: APPLE_SCENARIO_ORDER.get(row["stress_condition"], 99))
    if {row["stress_condition"] for row in output} != set(APPLE_SCENARIO_ORDER):
        raise ValueError("Figure 8 projection must contain all five paper stress conditions.")
    return output


def build_apple_workload_averages(source: Path) -> list[dict[str, Any]]:
    required = {
        ("TIER2_FULL", "CACHE"),
        ("TIER2_CORE", "CACHE"),
        ("TIER2_FULL", "ATOMIC"),
        ("TIER2_FULL", "MEMBW"),
    }
    output: list[dict[str, Any]] = []
    for row in read_csv(source):
        key = (row["observability"], row["scenario"])
        if key not in required:
            continue
        output.append(
            {
                "observability_view": key[0],
                "stress_condition": key[1],
                "workloads": integer(row, "workloads"),
                "mean_mcc": number(row, "mean_mcc"),
                "minimum_mcc": number(row, "min_mcc"),
                "mean_fpr": number(row, "mean_fpr"),
                "maximum_fpr": number(row, "max_fpr"),
            }
        )
    if {(row["observability_view"], row["stress_condition"]) for row in output} != required:
        raise ValueError("Apple workload projection is missing one or more values reported in Section V-J.")
    output.sort(key=lambda row: (row["stress_condition"], row["observability_view"]))
    return output


def build_apple_study_scope(
    best_source: Path,
    workload_detail_source: Path,
) -> list[dict[str, Any]]:
    best_rows = read_csv(best_source)
    details = read_csv(workload_detail_source)
    feature_counts = {
        row["observability"]: integer(row, "available_features")
        for row in best_rows
    }
    workloads = sorted({row["workload"] for row in details})
    stress_conditions = sorted({row["scenario"] for row in best_rows})
    if len(feature_counts) != 5 or sorted(feature_counts.values()) != [7, 8, 11, 18, 45]:
        raise ValueError(f"Unexpected Apple observability inventory: {feature_counts}")
    if len(workloads) != 4 or len(stress_conditions) != 5:
        raise ValueError("Unexpected Apple workload or stress-condition inventory")
    return [
        {
            "observability_view": view,
            "available_features": available,
            "evaluated_workloads": len(workloads),
            "workload_names": "|".join(workloads),
            "evaluated_stress_conditions": len(stress_conditions),
            "stress_condition_names": "|".join(stress_conditions),
        }
        for view, available in sorted(feature_counts.items(), key=lambda item: item[1])
    ]


def build_core(repo_root: Path, source_root: Path, output_root: Path) -> list[Path]:
    validate_figure_3_wording(repo_root)
    target = output_root / "core"
    target.mkdir(parents=True, exist_ok=True)
    selected_source = source_root / "tcad_ablation" / "paper_figures" / "gallery_table1_selected_operating_points.csv"
    summary_source = source_root / "tcad_ablation" / "tcad_ablation_summary.csv"
    workload_source = source_root / "tcad_ablation" / "paper_figures" / "gallery_table2_workload_robustness.csv"
    workload_detail_source = source_root / "tcad_ablation" / "paper_figures" / "gallery_table2_selected_setting_vs_workload_oracle.csv"
    budget_source = source_root / "tcad_ablation" / "paper_figures" / "gallery_table3_feature_budget_tradeoff.csv"
    graph_top_source = source_root / "tcad_ablation" / "paper_figures" / "gallery_fig4_top_features_by_domain.csv"
    lifecycle_source = source_root / "lifecycle_drift" / "lifecycle_recalibration_windows.csv"
    lifecycle_config_source = source_root / "lifecycle_drift" / "lifecycle_config_resolved.json"
    operator_source = repo_root / "hardware" / "cintas_operator_costs.csv"
    setup_inputs = {
        "A": repo_root / "data" / "telemetry" / "processed" / "ddr_data" / "DDR4_benign_dft.csv",
        "B": repo_root / "data" / "telemetry" / "processed" / "ddr_data" / "DDR5_benign_dft.csv",
    }
    available_channels = {setup: counted_feature_channels(path) for setup, path in setup_inputs.items()}
    if available_channels != {"A": 181, "B": 460}:
        raise ValueError(f"Unexpected recorded channel counts: {available_channels}")

    selected, selected_source_rows = selected_configuration_rows(selected_source, available_channels)
    dse = build_dse_envelope(summary_source, selected)
    workload = build_workload_results(workload_source)
    workload_details = build_workload_details(workload_detail_source)
    budgets = build_feature_budget_table(budget_source)
    graph_nodes = combine_graph_tables(source_root, "causal_nodes")
    graph_edges = combine_graph_tables(source_root, "causal_edges")
    graph_top = project_rows(
        graph_top_source,
        (
            "setup", "domain", "rank_in_domain", "feature", "importance_score",
            "node_stability", "conditional_dependence", "display_score",
        ),
        ("setup", "domain", "rank_in_domain"),
    )
    fixed_point = build_integer_error(selected_source_rows)
    analytical_cost = build_analytical_cost(summary_source, selected_source_rows, available_channels)
    operator_constants = project_rows(
        operator_source,
        ("operator", "bit_width", "area_mm2", "power_mw_at_1ghz", "delay_ps", "cycles"),
        ("operator",),
    )
    cost_basis = build_cost_basis(repo_root)
    table_x = build_table_x_citadel_row(selected, analytical_cost)
    lifecycle_trend, lifecycle_summary = build_lifecycle_tables(lifecycle_source)
    lifecycle_protocol = build_lifecycle_protocol(
        repo_root,
        lifecycle_config_source,
        lifecycle_summary,
    )

    definitions: list[tuple[str, Sequence[str], list[dict[str, Any]], Sequence[str]]] = [
        ("table_vi_selected_configurations.csv", tuple(selected[0]), selected, ("Table VI",)),
        ("figure_3_dse_envelope.csv", tuple(dse[0]), dse, ("Figure 3",)),
        ("section_vb_workload_results.csv", tuple(workload[0]), workload, ("Section V-B",)),
        ("section_vb_workload_details.csv", tuple(workload_details[0]), workload_details, ("Section V-B",)),
        ("table_vii_feature_budget_tradeoff.csv", tuple(budgets[0]), budgets, ("Table VII",)),
        ("figure_4_graph_nodes.csv", tuple(graph_nodes[0]), graph_nodes, ("Figure 4",)),
        ("figure_4_graph_edges.csv", tuple(graph_edges[0]), graph_edges, ("Figure 4",)),
        ("figure_4_top_features.csv", tuple(graph_top[0]), graph_top, ("Figure 4",)),
        ("table_viii_integer_reference_error.csv", tuple(fixed_point[0]), fixed_point, ("Table VIII",)),
        ("table_ix_analytical_cost.csv", tuple(analytical_cost[0]), analytical_cost, ("Table IX", "Table X CITADEL row")),
        ("section_vf_operator_constants.csv", tuple(operator_constants[0]), operator_constants, ("Section V-F",)),
        ("section_vf_cost_basis.csv", tuple(cost_basis[0]), cost_basis, ("Section V-F",)),
        ("table_x_citadel_row.csv", tuple(table_x[0]), table_x, ("Table X CITADEL row",)),
        ("figure_6_reference_validity_trend.csv", tuple(lifecycle_trend[0]), lifecycle_trend, ("Figure 6",)),
        ("figure_6_reference_validity_summary.csv", tuple(lifecycle_summary[0]), lifecycle_summary, ("Figure 6", "Section V-H")),
        ("section_vh_lifecycle_protocol.csv", tuple(lifecycle_protocol[0]), lifecycle_protocol, ("Section V-H",)),
    ]
    output_paths: list[Path] = []
    output_items: list[dict[str, Any]] = []
    for name, fields, rows, paper_items in definitions:
        path = target / name
        write_csv(path, fields, rows)
        output_paths.append(path)
        output_items.append(output_record(output_root, path, paper_items))

    graph_sources = [
        source_root / "tcad_ablation" / "causal" / f"SETUP_{setup}_{suffix}.csv"
        for setup in ("A", "B")
        for suffix in ("causal_nodes", "causal_edges")
    ]
    source_files = [
        source_record(repo_root, selected_source, role="Tables VI and VIII; Table IX selection"),
        source_record(repo_root, summary_source, role="Figure 3 and Table IX"),
        source_record(repo_root, workload_source, role="Section V-B"),
        source_record(repo_root, workload_detail_source, role="Section V-B per-workload statements"),
        source_record(repo_root, budget_source, role="Table VII"),
        source_record(repo_root, graph_top_source, role="Figure 4 labels"),
        *(source_record(repo_root, path, role="Figure 4 graph") for path in graph_sources),
        source_record(repo_root, lifecycle_source, role="Figure 6"),
        source_record(repo_root, lifecycle_config_source, role="Section V-H protocol"),
        source_record(
            repo_root,
            lifecycle_source.parent / "lifecycle_recalibration_summary.csv",
            role="Figure 6 summary",
        ),
        source_record(repo_root, operator_source, role="Section V-F analytical operator constants"),
        *(source_record(repo_root, path, role=f"Setup {setup} recorded channel inventory") for setup, path in setup_inputs.items()),
    ]
    rendered_figures = [
        rendered_figure_record(
            repo_root,
            source_root / "tcad_ablation" / "paper_figures" / "gallery_fig1_dse_heatmap.png",
            role="Figure 3 rendered output; hash informational",
        ),
        rendered_figure_record(
            repo_root,
            source_root / "tcad_ablation" / "paper_figures" / "gallery_fig1_dse_heatmap_legend.png",
            role="Figure 3 legend containing selected-configuration wording; hash informational",
        ),
        rendered_figure_record(
            repo_root,
            source_root / "tcad_ablation" / "paper_figures" / "gallery_fig4_full_stable_graph_network.png",
            role="Figure 4 rendered output; hash informational",
        ),
        rendered_figure_record(
            repo_root,
            source_root / "tcad_ablation" / "paper_figures" / "gallery_fig4_full_stable_graph_network_legend.png",
            role="Figure 4 legend; hash informational",
        ),
        rendered_figure_record(
            repo_root,
            source_root / "tcad_ablation" / "paper_figures" / "gallery_fig6c_lifecycle_benign_drift_trend.png",
            role="Figure 6 rendered output; hash informational",
        ),
        rendered_figure_record(
            repo_root,
            source_root / "tcad_ablation" / "paper_figures" / "gallery_fig6c_lifecycle_benign_drift_trend_legend.png",
            role="Figure 6 legend; hash informational",
        ),
    ]
    source_manifests = [
        manifest_provenance(repo_root, source_root / "tcad_ablation" / "run_manifest.json"),
        manifest_provenance(repo_root, source_root / "lifecycle_drift" / "run_manifest.json"),
    ]
    classification, archival_status = evidence_class(source_manifests)
    manifest_path = target / "evidence_manifest.json"
    write_json(
        manifest_path,
        {
            "schema_version": 1,
            "profile": "core",
            "scope": [
                "Table VI", "Figure 3", "Section V-B", "Table VII", "Figure 4",
                "Table VIII", "Section V-F", "Table IX", "Table X CITADEL row",
                "Figure 6", "Section V-H",
            ],
            "evidence_class": classification,
            "archival_status": archival_status,
            "interpretation": (
                "The CSVs are deterministic projections of paper-facing results. "
                "REFERENCE_ONLY means the preserved source run was dirty or lacks a clean commit; "
                "it becomes independent clean-run evidence only after a clean rerun compares PASS."
            ),
            "comparison_policy": {
                "csv_schema_and_categorical_values": "exact",
                "csv_numeric_values": "tolerance-based",
                "png_hashes": "informational_only",
            },
            "source_run_manifests": source_manifests,
            "source_files": source_files,
            "rendered_figures": rendered_figures,
            "outputs": output_items,
        },
    )
    output_paths.append(manifest_path)
    return output_paths


def build_apple(repo_root: Path, source_root: Path, output_root: Path) -> list[Path]:
    target = output_root / "apple"
    target.mkdir(parents=True, exist_ok=True)
    best_source = source_root / "apple_limited_observability" / "apple_observability_best_by_scenario.csv"
    workload_source = source_root / "apple_limited_observability" / "apple_workload_summary.csv"
    workload_detail_source = source_root / "apple_limited_observability" / "apple_workload_best_by_observability.csv"
    envelope = build_apple_envelope(best_source)
    averages = build_apple_workload_averages(workload_source)
    study_scope = build_apple_study_scope(best_source, workload_detail_source)
    definitions: list[tuple[str, Sequence[str], list[dict[str, Any]], Sequence[str]]] = [
        ("figure_8_portability_envelope.csv", tuple(envelope[0]), envelope, ("Figure 8", "Section V-J")),
        ("section_vj_workload_averages.csv", tuple(averages[0]), averages, ("Section V-J",)),
        ("section_vj_study_scope.csv", tuple(study_scope[0]), study_scope, ("Section V-J",)),
    ]
    output_paths: list[Path] = []
    output_items: list[dict[str, Any]] = []
    for name, fields, rows, paper_items in definitions:
        path = target / name
        write_csv(path, fields, rows)
        output_paths.append(path)
        output_items.append(output_record(output_root, path, paper_items))

    source_manifests = [
        manifest_provenance(
            repo_root,
            source_root / "apple_limited_observability" / "run_manifest.json",
        )
    ]
    classification, archival_status = evidence_class(source_manifests)
    manifest_path = target / "evidence_manifest.json"
    write_json(
        manifest_path,
        {
            "schema_version": 1,
            "profile": "apple",
            "scope": ["Figure 8", "Section V-J"],
            "evidence_class": classification,
            "archival_status": archival_status,
            "interpretation": (
                "The CSVs are deterministic projections of paper-facing results. "
                "REFERENCE_ONLY means the preserved source run was dirty or lacks a clean commit; "
                "it becomes independent clean-run evidence only after a clean rerun compares PASS."
            ),
            "comparison_policy": {
                "csv_schema_and_categorical_values": "exact",
                "csv_numeric_values": "tolerance-based",
                "png_hashes": "informational_only",
            },
            "source_run_manifests": source_manifests,
            "source_files": [
                source_record(repo_root, best_source, role="Figure 8"),
                source_record(repo_root, workload_source, role="Section V-J workload averages"),
                source_record(repo_root, workload_detail_source, role="Section V-J workload and view inventory"),
            ],
            "rendered_figures": [
                rendered_figure_record(
                    repo_root,
                    source_root / "apple_limited_observability" / "paper_figures" / "fig_apple_portability_envelope.png",
                    role="Figure 8 rendered output; hash informational",
                ),
                rendered_figure_record(
                    repo_root,
                    source_root / "apple_limited_observability" / "paper_figures" / "fig_apple_portability_envelope_legend.png",
                    role="Figure 8 legend; hash informational",
                ),
            ],
            "outputs": output_items,
        },
    )
    output_paths.append(manifest_path)
    return output_paths


def build_profiles(
    repo_root: Path,
    source_root: Path,
    output_root: Path,
    profile: str,
) -> list[Path]:
    paths: list[Path] = []
    if profile in {"core", "all"}:
        paths.extend(build_core(repo_root, source_root, output_root))
    if profile in {"apple", "all"}:
        paths.extend(build_apple(repo_root, source_root, output_root))
    return paths


def check_existing(
    repo_root: Path,
    source_root: Path,
    output_root: Path,
    profile: str,
) -> int:
    with tempfile.TemporaryDirectory(prefix="citadel-paper-results-") as temporary:
        temporary_root = Path(temporary)
        generated = build_profiles(repo_root, source_root, temporary_root, profile)
        differences: list[str] = []
        for generated_path in generated:
            relative = generated_path.relative_to(temporary_root)
            existing = output_root / relative
            if not existing.is_file():
                differences.append(f"MISSING {relative.as_posix()}")
            elif generated_path.read_bytes() != existing.read_bytes():
                differences.append(f"DIFF {relative.as_posix()}")
        if differences:
            print("Paper-result bundle check: FAIL")
            for difference in differences:
                print(difference)
            return 1
    print("Paper-result bundle check: PASS")
    return 0


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    root = repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=root)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=root / "results" / "notebook_run",
        help="Notebook output root containing the core and/or Apple result directories.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=root / "reproducibility" / "paper_results",
        help="Destination whose core/ and apple/ children receive projected evidence.",
    )
    parser.add_argument("--profile", choices=("core", "apple", "all"), default="all")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Rebuild in a temporary directory and compare with --output-root.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.repo_root.resolve()
    source = args.source_root.resolve()
    output = args.output_root.resolve()
    if args.check:
        return check_existing(root, source, output, args.profile)
    paths = build_profiles(root, source, output, args.profile)
    print(f"Wrote {len(paths)} paper-result bundle files under {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
