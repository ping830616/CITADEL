#!/usr/bin/env python3
"""Analyze continuous Intel PCM workload transition campaign traces."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import types
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_mpl_config = Path(tempfile.gettempdir()) / "citadel-matplotlib"
_mpl_config.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_config))
os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


NOTEBOOK_CELL_IDS = ("0bbebb9d", "3d1f98fe", "integrated-utilities-code")
NOTEBOOK_UTILITY_LOADER = {
    "mode": "validation-free",
    "profile": "smoke",
    "data_mode": "sample",
    "tcad_preset": "smoke",
    "seed": 123,
    "threads": 1,
    "strict_runtime": False,
    "experiment_sections_enabled": False,
}
DATE_PATTERN = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$")


@dataclass(frozen=True)
class AnalysisConfig:
    top_k: int = 8
    window_size: int = 50
    lambda_res: float = 0.50
    persistence_blocks: int = 2
    transition_window_blocks: int = 1
    stabilization_blocks: int = 2
    eta: float = 0.01
    reference_alpha: float = 0.05
    correlation_threshold: float = 0.35
    bootstrap_resamples: int = 10_000
    seed: int = 123


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()
    except Exception:
        return "unknown"


def _git_dirty(repo_root: Path) -> bool | None:
    try:
        return bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=repo_root, text=True
            ).strip()
        )
    except Exception:
        return None


def _portable_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze one complete continuous Intel transition campaign."
    )
    parser.add_argument("--campaign-dir", type=Path, default=None)
    parser.add_argument(
        "--campaign-root",
        type=Path,
        default=_repo_root()
        / "data"
        / "telemetry"
        / "raw"
        / "intel_transition_campaigns",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=_repo_root()
        / "results"
        / "notebook_run"
        / "intel_transition_campaigns",
    )
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--window-size", type=int, default=50)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument(
        "--pcm-timezone",
        default=None,
        help=(
            "IANA timezone for legacy PCM CSV Date/Time columns. New CITADEL "
            "collections record UTC and do not require this option."
        ),
    )
    return parser


def _latest_complete_campaign(root: Path) -> Path | None:
    candidates = []
    for manifest_path in root.glob("*/campaign_manifest.json"):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("status") == "complete":
            candidates.append(manifest_path.parent)
    # Campaign directory names are UTC identifiers. Lexical selection is stable
    # across clones; filesystem mtimes are not preserved by Git or rsync.
    return sorted(candidates, key=lambda path: path.name)[-1] if candidates else None


def _load_notebook_namespace(repo_root: Path) -> dict[str, object]:
    notebook_path = repo_root / "notebooks" / "exact_tcad_all_experiments.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    cells = {cell.get("id"): cell for cell in notebook["cells"]}
    missing = [cell_id for cell_id in NOTEBOOK_CELL_IDS if cell_id not in cells]
    if missing:
        raise RuntimeError(f"Required notebook cells are missing: {missing}")
    module_name = "_citadel_intel_transition_notebook"
    module = types.ModuleType(module_name)
    module.__file__ = str(notebook_path)
    sys.modules[module_name] = module
    namespace = module.__dict__
    progress_log = repo_root / "results" / "notebook_run" / "notebook_progress.log"
    saved_progress = progress_log.read_bytes() if progress_log.is_file() else None
    saved_environment = dict(os.environ)
    temporary_parent = repo_root / "results" / "reproduced"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".intel-transition-utility-loader-", dir=temporary_parent
    ) as temporary_directory:
        utility_root = Path(temporary_directory)
        os.environ.update(
            {
                "CITADEL_SEED": "123",
                "CITADEL_THREADS": "1",
                "CITADEL_PROFILE": "smoke",
                "CITADEL_DATA_MODE": "sample",
                "CITADEL_TCAD_PRESET": "smoke",
                "CITADEL_RUN_LIFECYCLE": "0",
                "CITADEL_RUN_INTEL_WORKLOAD_ORDERS": "0",
                "CITADEL_RUN_APPLE_OBSERVABILITY": "0",
                "CITADEL_STRICT_RUNTIME": "0",
                "CITADEL_RESULTS_ROOT": str(utility_root / "notebook_run"),
                "CITADEL_SAMPLE_ROOT": str(utility_root / "sample_data"),
            }
        )
        try:
            for cell_id in NOTEBOOK_CELL_IDS:
                source = "".join(cells[cell_id].get("source", []))
                exec(compile(source, f"{notebook_path.name}:{cell_id}", "exec"), namespace)
        finally:
            os.environ.clear()
            os.environ.update(saved_environment)
            if saved_progress is not None:
                progress_log.write_bytes(saved_progress)
            elif progress_log.exists():
                progress_log.unlink()
    return namespace


def _create_new_output_directory(output: Path) -> None:
    if output.exists():
        raise FileExistsError(
            f"Campaign analysis output already exists: {output}. Choose a fresh "
            "--output-root so stale and regenerated evidence cannot be mixed."
        )
    output.mkdir(parents=True)


def _detect_delimiter(lines: list[str]) -> str:
    sample = "\n".join(lines[:6])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;").delimiter
    except csv.Error:
        return "," if sample.count(",") >= sample.count(";") else ";"


def _looks_like_data(row: list[str]) -> bool:
    if not row:
        return False
    first = row[0].strip().strip('"')
    return bool(DATE_PATTERN.match(first))


def _unique_columns(header_rows: list[list[str]], width: int) -> list[str]:
    base_names = []
    for column_index in range(width):
        pieces = []
        for row in header_rows:
            value = row[column_index].strip() if column_index < len(row) else ""
            if value and value not in pieces:
                pieces.append(value)
        base_names.append("_".join(pieces) or f"column_{column_index}")
    counts: dict[str, int] = {}
    names = []
    for base in base_names:
        count = counts.get(base, 0)
        counts[base] = count + 1
        names.append(base if count == 0 else f"{base}.{count}")
    return names


def read_pcm_csv(
    path: Path, *, pcm_timezone: str
) -> tuple[pd.DataFrame, dict[str, object]]:
    lines = [
        line.rstrip("\r\n")
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    if len(lines) < 3:
        raise RuntimeError(f"PCM CSV is incomplete: {path}")
    delimiter = _detect_delimiter(lines)
    rows = list(csv.reader(lines, delimiter=delimiter))
    data_start = next(
        (index for index, row in enumerate(rows) if _looks_like_data(row)), None
    )
    if data_start is None or data_start == 0:
        raise RuntimeError(
            "Could not locate dated PCM data rows. Keep the unmodified PCM CSV and "
            "verify that Date and Time output are enabled."
        )
    data_rows = rows[data_start:]
    width = max(len(row) for row in data_rows)
    header_rows = [row for row in rows[:data_start] if len(row) > 1][-2:]
    if not header_rows:
        raise RuntimeError("PCM CSV header rows are missing")
    columns = _unique_columns(header_rows, width)
    normalized = [row[:width] + [""] * max(0, width - len(row)) for row in data_rows]
    frame = pd.DataFrame(normalized, columns=columns)
    date_column = columns[0]
    time_column = columns[1] if len(columns) > 1 else ""
    if "DATE" not in date_column.upper() or "TIME" not in time_column.upper():
        raise RuntimeError(
            f"PCM timestamp columns were not recognized: {date_column}, {time_column}"
        )
    parsed = pd.to_datetime(
        frame[date_column].astype(str).str.strip()
        + " "
        + frame[time_column].astype(str).str.strip(),
        errors="coerce",
    )
    if parsed.isna().any():
        raise RuntimeError("One or more PCM Date and Time values could not be parsed")
    try:
        timezone_info = ZoneInfo(pcm_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown PCM timezone: {pcm_timezone!r}") from exc
    try:
        parsed = parsed.dt.tz_localize(
            timezone_info,
            ambiguous="raise",
            nonexistent="raise",
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"PCM timestamps could not be localized with timezone {pcm_timezone!r}"
        ) from exc
    frame.insert(
        0,
        "timestamp_unix_s",
        parsed.map(lambda value: value.to_pydatetime().timestamp()),
    )
    frame = frame.drop(columns=[date_column, time_column])
    for column in frame.columns:
        if column != "timestamp_unix_s":
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.sort_values("timestamp_unix_s").drop_duplicates(
        "timestamp_unix_s", keep="last"
    )
    frame = frame.reset_index(drop=True)
    intervals = np.diff(frame["timestamp_unix_s"].to_numpy(dtype=float))
    audit = {
        "delimiter": delimiter,
        "header_row_count": len(header_rows),
        "data_rows": len(frame),
        "feature_columns": len(frame.columns) - 1,
        "median_observed_interval_seconds": (
            float(np.median(intervals)) if len(intervals) else None
        ),
        "maximum_observed_interval_seconds": (
            float(np.max(intervals)) if len(intervals) else None
        ),
        "timestamp_source": f"{date_column} plus {time_column} from Intel PCM",
        "pcm_timezone": pcm_timezone,
    }
    return frame, audit


def _align_phases(pcm: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    required = {
        "phase_index",
        "cycle_index",
        "cycle_position",
        "workload",
        "start_ts_unix_s",
        "end_ts_unix_s",
    }
    missing = sorted(required - set(events.columns))
    if missing:
        raise RuntimeError(f"Phase event columns are missing: {missing}")
    parts = []
    for event in events.sort_values("phase_index").itertuples(index=False):
        mask = (
            (pcm["timestamp_unix_s"] >= float(event.start_ts_unix_s))
            & (pcm["timestamp_unix_s"] < float(event.end_ts_unix_s))
        )
        part = pcm.loc[mask].copy()
        if part.empty:
            raise RuntimeError(f"No PCM samples aligned to phase {event.phase_index}")
        part.insert(0, "workload", str(event.workload))
        part.insert(0, "cycle_position", int(event.cycle_position))
        part.insert(0, "cycle_index", int(event.cycle_index))
        part.insert(0, "phase_index", int(event.phase_index))
        parts.append(part)
    trace = pd.concat(parts, ignore_index=True)
    trace.insert(0, "idx", np.arange(len(trace)))
    trace["scenario"] = "BENIGN"
    return trace


def _preprocess_trace(
    trace: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    metadata = {
        "idx",
        "phase_index",
        "cycle_index",
        "cycle_position",
        "workload",
        "timestamp_unix_s",
        "scenario",
    }
    numeric = sorted(
        set(trace.select_dtypes(include=[np.number]).columns) - metadata
    )
    metadata_columns = [
        "idx",
        "phase_index",
        "cycle_index",
        "cycle_position",
        "workload",
        "timestamp_unix_s",
        "scenario",
    ]
    output = trace[metadata_columns].copy()
    columns: dict[str, pd.Series] = {}
    audit_rows = []
    for feature in numeric:
        values = pd.to_numeric(trace[feature], errors="coerce")
        if "TEMP" in feature.upper() or "VOLTAGE" in feature.upper():
            output_feature = f"{feature}__delta"
            columns[output_feature] = values.diff()
            action = "converted_to_continuous_first_difference"
            reason = "absolute operating state can drift slowly"
        else:
            output_feature = feature
            columns[output_feature] = values
            action = "retained_interval_metric"
            reason = "Intel PCM reports the value for the sampling interval"
        audit_rows.append(
            {
                "source_feature": feature,
                "output_feature": output_feature,
                "action": action,
                "reason": reason,
            }
        )
    feature_frame = pd.DataFrame(columns, index=trace.index)
    output = pd.concat([output, feature_frame], axis=1)
    return output, pd.DataFrame(audit_rows), list(columns)


def _aggregate_score(values: np.ndarray) -> float:
    return float(np.mean(values))


def _score_blocks(frame: pd.DataFrame, model, cfg: AnalysisConfig, score_samples) -> pd.DataFrame:
    rows = []
    for (cycle, phase, workload), group in frame.groupby(
        ["cycle_index", "phase_index", "workload"], sort=True
    ):
        group = group.sort_values("timestamp_unix_s").reset_index(drop=True)
        scores = score_samples(group, model)
        block_count = len(scores) // cfg.window_size
        for block_index in range(block_count):
            start = block_index * cfg.window_size
            stop = start + cfg.window_size
            rows.append(
                {
                    "cycle_index": int(cycle),
                    "phase_index": int(phase),
                    "workload": str(workload),
                    "block_index_in_phase": block_index,
                    "start_timestamp_unix_s": float(
                        group["timestamp_unix_s"].iloc[start]
                    ),
                    "end_timestamp_unix_s": float(
                        group["timestamp_unix_s"].iloc[stop - 1]
                    ),
                    "score": _aggregate_score(scores[start:stop]),
                }
            )
    if not rows:
        raise RuntimeError("No complete decision blocks were available")
    return pd.DataFrame(rows).sort_values("start_timestamp_unix_s").reset_index(drop=True)


def _persistence_alarm(raw: np.ndarray, required: int) -> np.ndarray:
    run_length = 0
    output = np.zeros(len(raw), dtype=int)
    for index, alarm in enumerate(np.asarray(raw, dtype=int)):
        run_length = run_length + 1 if alarm else 0
        output[index] = int(run_length >= required)
    return output


def _binomial_upper_tail(successes: int, trials: int, probability: float) -> float:
    if trials <= 0:
        return float("nan")
    if successes <= 0:
        return 1.0
    return float(
        sum(
            math.comb(trials, count)
            * probability**count
            * (1.0 - probability) ** (trials - count)
            for count in range(successes, trials + 1)
        )
    )


def _finite_sample_upper_threshold(
    scores: np.ndarray, target_fpr: float
) -> tuple[float, int]:
    values = np.sort(np.asarray(scores, dtype=float))
    values = values[np.isfinite(values)]
    if len(values) == 0:
        raise ValueError("Calibration scores are empty or nonfinite")
    rank = min(len(values), math.ceil((len(values) + 1) * (1.0 - target_fpr)))
    return float(values[rank - 1]), int(rank)


def _stabilization(blocks: pd.DataFrame, cfg: AnalysisConfig) -> pd.DataFrame:
    rows = []
    for phase, group in blocks.groupby("phase_index", sort=True):
        group = group.sort_values("block_index_in_phase")
        below = (group["alarm_raw"].to_numpy(dtype=int) == 0).astype(int)
        stable = None
        for index in range(max(0, len(below) - cfg.stabilization_blocks + 1)):
            if np.all(below[index : index + cfg.stabilization_blocks]):
                stable = index
                break
        rows.append(
            {
                "phase_index": int(phase),
                "workload": str(group["workload"].iloc[0]),
                "blocks_to_stabilize": stable,
                "stabilized": int(stable is not None),
            }
        )
    return pd.DataFrame(rows)


def _analyze_run(
    run_dir: Path,
    run_index: int,
    campaign: dict[str, object],
    cfg: AnalysisConfig,
    output: Path,
    notebook: dict[str, object],
    pcm_timezone_override: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    manifest_path = run_dir / "collection_manifest.json"
    collection = json.loads(manifest_path.read_text(encoding="utf-8"))
    if collection.get("status") != "complete":
        raise RuntimeError(f"Run is not complete: {manifest_path}")
    protocol = collection.get("protocol", {})
    pcm_timezone = pcm_timezone_override or protocol.get("pcm_timezone")
    if not pcm_timezone:
        raise RuntimeError(
            "The collection manifest does not identify the timezone used by the "
            "PCM Date/Time columns. Pass --pcm-timezone with an IANA name when "
            "analyzing this legacy campaign."
        )
    pcm, parse_audit = read_pcm_csv(
        run_dir / "pcm_raw.csv", pcm_timezone=str(pcm_timezone)
    )
    events = pd.read_csv(run_dir / "phase_events.csv")
    trace = _align_phases(pcm, events)
    processed, preprocessing_audit, candidate_features = _preprocess_trace(trace)
    calibration_cycles = int(campaign["calibration_cycles"])
    calibration = processed[processed["cycle_index"] < calibration_cycles].copy()
    evaluation = processed[processed["cycle_index"] >= calibration_cycles].copy()
    means = calibration[candidate_features].replace([np.inf, -np.inf], np.nan).mean()
    finite = [feature for feature in candidate_features if np.isfinite(means[feature])]
    for frame in (calibration, evaluation):
        frame[finite] = frame[finite].replace([np.inf, -np.inf], np.nan)
        frame[finite] = frame[finite].fillna(means[finite])
    variable = [
        feature
        for feature in finite
        if calibration[feature].nunique(dropna=True) > 1
        and float(calibration[feature].std(ddof=1)) > 0
    ]
    if len(variable) < 2:
        raise RuntimeError(f"Run {run_index + 1} has too few usable PCM features")
    preprocessing_audit["calibration_quality"] = preprocessing_audit[
        "output_feature"
    ].map(lambda feature: "usable" if feature in variable else "removed_nonfinite_or_constant")
    fit_cintas = notebook["fit_cintas_from_benign"]
    score_samples = notebook["score_samples"]
    rank_features = notebook["_rank_features_from_benign_only"]
    select_features = notebook["_selected_features"]
    base_model = fit_cintas(calibration, variable, lambda_res=cfg.lambda_res, weight_mode="uniform")
    rank_input = calibration.copy()
    rank_input["cias_sample_score"] = score_samples(rank_input, base_model)
    ranks = rank_features(
        setup=str(campaign["setup"]),
        df_benign=rank_input,
        feature_cols=variable,
        out_root=output,
        corr_threshold=cfg.correlation_threshold,
        tag=f"continuous_run_{run_index + 1:02d}",
    )
    selected = select_features(ranks, min(cfg.top_k, len(variable)), variable)
    model = fit_cintas(calibration, selected, lambda_res=cfg.lambda_res, weight_mode="uniform")
    reference_blocks = _score_blocks(calibration, model, cfg, score_samples)
    threshold, threshold_rank = _finite_sample_upper_threshold(
        reference_blocks["score"].to_numpy(dtype=float), cfg.eta
    )
    blocks = _score_blocks(evaluation, model, cfg, score_samples)
    blocks["threshold"] = threshold
    blocks["alarm_raw"] = (blocks["score"] > threshold).astype(int)
    blocks["alarm_persistence"] = _persistence_alarm(
        blocks["alarm_raw"].to_numpy(dtype=int), cfg.persistence_blocks
    )
    blocks["is_transition_window"] = (
        blocks["block_index_in_phase"] < cfg.transition_window_blocks
    )
    stabilization = _stabilization(blocks, cfg)
    transition = blocks["is_transition_window"].to_numpy(dtype=bool)
    rule_rows = []
    for rule, column in (("current", "alarm_raw"), ("persistence", "alarm_persistence")):
        alarms = blocks[column].to_numpy(dtype=int)
        alarm_count = int(np.sum(alarms))
        pvalue = _binomial_upper_tail(alarm_count, len(alarms), cfg.eta)
        rule_rows.append(
            {
                "setup": campaign["setup"],
                "run_index": run_index + 1,
                "seed": collection["protocol"]["seed"],
                "decision_rule": rule,
                "n_blocks": len(blocks),
                "n_alarms": alarm_count,
                "calibration_threshold_rank": threshold_rank,
                "calibration_block_count": len(reference_blocks),
                "overall_benign_fpr": float(np.mean(alarms)),
                "transition_window_fpr": float(np.mean(alarms[transition])),
                "steady_window_fpr": float(np.mean(alarms[~transition])),
                "reference_compatibility_pvalue": pvalue,
                "reference_stale": int(pvalue < cfg.reference_alpha),
                "reference_stale_naive": int(np.mean(alarms) > cfg.eta),
                "threshold": threshold,
                "threshold_rule": (
                    "finite_sample_upper_rank_with_strict_exceedance"
                ),
            }
        )
    selected_frame = ranks[ranks["feature"].isin(selected)].copy()
    selected_frame["selected_order"] = selected_frame["feature"].map(
        {feature: index + 1 for index, feature in enumerate(selected)}
    )
    selected_frame.insert(0, "run_index", run_index + 1)
    run_output = output / "runs" / f"run_{run_index + 1:02d}"
    run_output.mkdir(parents=True, exist_ok=True)
    trace.to_csv(run_output / "aligned_pcm_trace.csv", index=False)
    blocks.to_csv(run_output / "evaluation_block_scores.csv", index=False)
    reference_blocks.to_csv(run_output / "calibration_block_scores.csv", index=False)
    stabilization.to_csv(run_output / "transition_stabilization.csv", index=False)
    preprocessing_audit.to_csv(run_output / "preprocessing_audit.csv", index=False)
    selected_frame.sort_values("selected_order").to_csv(
        run_output / "selected_features.csv", index=False
    )
    pd.DataFrame(rule_rows).to_csv(run_output / "rule_summary.csv", index=False)
    (run_output / "pcm_parse_audit.json").write_text(
        json.dumps(parse_audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return pd.DataFrame(rule_rows), stabilization, selected_frame, parse_audit


def _bootstrap(values: np.ndarray, resamples: int, seed: int) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    if len(values) == 1:
        return float(values[0]), float(values[0])
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(resamples, len(values)))
    means = values[indices].mean(axis=1)
    return tuple(float(value) for value in np.quantile(means, [0.025, 0.975]))


def _aggregate(results: pd.DataFrame, cfg: AnalysisConfig) -> pd.DataFrame:
    metrics = (
        "overall_benign_fpr",
        "transition_window_fpr",
        "steady_window_fpr",
        "reference_stale",
        "reference_stale_naive",
    )
    rows = []
    for rule, group in results.groupby("decision_rule", sort=True):
        for index, metric in enumerate(metrics):
            values = pd.to_numeric(group[metric], errors="coerce").dropna().to_numpy(dtype=float)
            low, high = _bootstrap(values, cfg.bootstrap_resamples, cfg.seed + 1009 * index)
            rows.append(
                {
                    "decision_rule": rule,
                    "metric": metric,
                    "n_runs": len(values),
                    "mean": float(np.mean(values)),
                    "sample_sd": float(np.std(values, ddof=1)) if len(values) > 1 else float("nan"),
                    "minimum": float(np.min(values)),
                    "maximum": float(np.max(values)),
                    "bootstrap_95_low": low,
                    "bootstrap_95_high": high,
                }
            )
    return pd.DataFrame(rows)


def _plot(results: pd.DataFrame, summary: pd.DataFrame, path: Path, setup: str) -> None:
    metrics = (
        ("overall_benign_fpr", "Overall"),
        ("transition_window_fpr", "First block after switch"),
        ("steady_window_fpr", "Later blocks within phase"),
    )
    colors = {"current": "#0B4F9C", "persistence": "#D94801"}
    labels = {"current": "Current rule", "persistence": "Two block persistence"}
    fig, axes = plt.subplots(1, 3, figsize=(14.4, 5.0), dpi=220, sharey=True)
    rng = np.random.default_rng(123)
    for axis, (metric, title) in zip(axes, metrics, strict=True):
        for rule_index, rule in enumerate(("current", "persistence")):
            subset = results[results["decision_rule"] == rule].sort_values("run_index")
            values = 100 * subset[metric].to_numpy(dtype=float)
            axis.scatter(
                np.full(len(values), rule_index) + rng.uniform(-0.05, 0.05, len(values)),
                values,
                s=58,
                color=colors[rule],
                edgecolor="white",
                linewidth=0.8,
                zorder=3,
            )
            row = summary[
                (summary["decision_rule"] == rule) & (summary["metric"] == metric)
            ].iloc[0]
            axis.errorbar(
                rule_index,
                100 * row["mean"],
                yerr=100 * row["sample_sd"],
                fmt="D",
                color="#111827",
                markerfacecolor="#FACC15",
                markersize=8,
                capsize=6,
                linewidth=2,
                zorder=4,
            )
        axis.set_title(title, fontsize=13.5, fontweight="bold")
        axis.set_xticks((0, 1), (labels["current"], labels["persistence"]))
        axis.tick_params(labelsize=10.5)
        axis.grid(axis="y", alpha=0.25)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Benign false positive rate (%)", fontsize=12.5, fontweight="bold")
    fig.suptitle(
        f"Continuous Intel Workload Transitions, Setup {setup}",
        fontsize=18,
        fontweight="bold",
        y=0.99,
    )
    fig.text(
        0.5,
        0.01,
        "Circles are independent continuous runs; yellow diamonds show the mean and sample standard deviation.",
        ha="center",
        fontsize=10,
        color="#475569",
    )
    fig.subplots_adjust(top=0.82, bottom=0.20, left=0.075, right=0.99, wspace=0.17)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    args = _parser().parse_args()
    if args.bootstrap_resamples < 1000:
        raise ValueError("--bootstrap-resamples must be at least 1000")
    cfg = AnalysisConfig(
        top_k=args.top_k,
        window_size=args.window_size,
        bootstrap_resamples=args.bootstrap_resamples,
        seed=args.seed,
    )
    repo_root = _repo_root()
    campaign_dir = (
        args.campaign_dir.expanduser().resolve()
        if args.campaign_dir
        else _latest_complete_campaign(args.campaign_root.expanduser().resolve())
    )
    if campaign_dir is None:
        raise FileNotFoundError("No complete Intel transition campaign was found")
    campaign_manifest = campaign_dir / "campaign_manifest.json"
    campaign = json.loads(campaign_manifest.read_text(encoding="utf-8"))
    if campaign.get("status") != "complete":
        raise RuntimeError(f"Campaign is not complete: {campaign_manifest}")
    completed_runs = campaign.get("run_results", [])
    if len(completed_runs) < 3:
        raise RuntimeError("At least three completed physical runs are required")
    output = args.output_root.expanduser().resolve() / campaign_dir.name
    _create_new_output_directory(output)
    notebook = _load_notebook_namespace(repo_root)
    rules = []
    stabilizations = []
    selected = []
    parse_audits = []
    for run in completed_runs:
        if run.get("collection_status") != "complete" or int(run.get("returncode", 1)) != 0:
            raise RuntimeError(f"Campaign contains an incomplete run: {run}")
        run_index = int(run["run_index"])
        run_dir = Path(run["run_dir"])
        if not run_dir.is_absolute():
            run_dir = repo_root / run_dir
        print(f"Analyzing continuous Intel run {run_index + 1}", flush=True)
        rule, stabilization, selected_frame, parse_audit = _analyze_run(
            run_dir,
            run_index,
            campaign,
            cfg,
            output,
            notebook,
            args.pcm_timezone,
        )
        rules.append(rule)
        stabilization.insert(0, "run_index", run_index + 1)
        stabilizations.append(stabilization)
        selected.append(selected_frame)
        parse_audits.append({"run_index": run_index + 1, **parse_audit})
    rule_results = pd.concat(rules, ignore_index=True)
    stabilization_results = pd.concat(stabilizations, ignore_index=True)
    selected_results = pd.concat(selected, ignore_index=True)
    summary = _aggregate(rule_results, cfg)
    feature_frequency = (
        selected_results.groupby("feature", as_index=False)
        .agg(
            n_runs_selected=("run_index", "nunique"),
            mean_selected_order=("selected_order", "mean"),
        )
        .sort_values(["n_runs_selected", "mean_selected_order", "feature"], ascending=[False, True, True])
    )
    rule_path = output / "all_run_rule_results.csv"
    summary_path = output / "campaign_metric_summary.csv"
    stabilization_path = output / "all_run_transition_stabilization.csv"
    selected_path = output / "all_run_selected_features.csv"
    frequency_path = output / "campaign_feature_selection_frequency.csv"
    parse_path = output / "pcm_parse_audits.csv"
    figure_path = output / "fig_intel_transition_campaign_variation.png"
    rule_results.to_csv(rule_path, index=False)
    summary.to_csv(summary_path, index=False)
    stabilization_results.to_csv(stabilization_path, index=False)
    selected_results.to_csv(selected_path, index=False)
    feature_frequency.to_csv(frequency_path, index=False)
    pd.DataFrame(parse_audits).to_csv(parse_path, index=False)
    _plot(rule_results, summary, figure_path, str(campaign["setup"]))
    current = summary[summary["decision_rule"] == "current"].set_index("metric")
    current_runs = rule_results[rule_results["decision_rule"] == "current"]
    stale_count = int(current_runs["reference_stale"].sum())
    phases_per_run = len(campaign["workloads"]) * (
        int(campaign["calibration_cycles"]) + int(campaign["evaluation_cycles"])
    )
    measured_switches = len(rules) * max(0, phases_per_run - 1)
    paper_text = (
        f"Across {len(rules)} independent continuous Intel Setup {campaign['setup']} runs, "
        f"one uninterrupted PCM stream per run recorded {measured_switches} workload switches. "
        "A finite sample corrected upper calibration rank set the 1 percent decision threshold. "
        f"The mean benign false positive rate was {100 * current.loc['overall_benign_fpr', 'mean']:.2f} "
        f"percent with a sample standard deviation of {100 * current.loc['overall_benign_fpr', 'sample_sd']:.2f} "
        f"percentage points. The first decision block after each measured workload switch averaged "
        f"{100 * current.loc['transition_window_fpr', 'mean']:.2f} percent, compared with "
        f"{100 * current.loc['steady_window_fpr', 'mean']:.2f} percent for later blocks within a phase. "
        f"The one sided exact binomial compatibility check marked {stale_count} of {len(rules)} runs stale. "
        "This experiment evaluates rapid benign workload changes and does not claim controlled voltage, "
        "frequency, thermal, firmware, or aging transitions."
    )
    paper_path = output / "campaign_paper_ready_result.txt"
    paper_path.write_text(paper_text + "\n", encoding="utf-8")
    artifacts = (
        rule_path,
        summary_path,
        stabilization_path,
        selected_path,
        frequency_path,
        parse_path,
        figure_path,
        paper_path,
    )
    manifest_path = output / "campaign_analysis_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "status": "complete",
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "git_commit": _git_commit(repo_root),
                "git_dirty": _git_dirty(repo_root),
                "config": cfg.__dict__,
                "notebook_utility_loader": NOTEBOOK_UTILITY_LOADER,
                "campaign_manifest": {
                    "path": _portable_path(campaign_manifest, repo_root),
                    "sha256": _sha256(campaign_manifest),
                },
                "artifacts": [
                    {
                        "path": _portable_path(path, repo_root),
                        "sha256": _sha256(path),
                    }
                    for path in artifacts
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "complete", "output": str(output), "paper_text": paper_text}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
