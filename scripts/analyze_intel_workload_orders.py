#!/usr/bin/env python3
"""Run an Intel benign workload order stress test from preserved telemetry.

The preserved DDR4 and DDR5 files were collected separately for each PAMPAR
workload. This analysis constructs abrupt workload-order sequences from
nonoverlapping row blocks. It measures held-out workload distribution changes,
not the physical transient of a continuously collected hardware switch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
import types
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

_mpl_config = Path(tempfile.gettempdir()) / "citadel-matplotlib"
_mpl_config.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_config))
os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


WORKLOADS = (
    "DFT",
    "DJ",
    "DP",
    "GL",
    "GS",
    "HA",
    "JA",
    "MM",
    "NI",
    "OE",
    "PI",
    "SH",
    "TR",
)
SETUP_PREFIX = {"A": "DDR4", "B": "DDR5"}
NOTEBOOK_CELL_IDS = ("0bbebb9d", "3d1f98fe", "integrated-utilities-code")


@dataclass(frozen=True)
class IntelWorkloadOrderConfig:
    setups: tuple[str, ...] = ("A", "B")
    workloads: tuple[str, ...] = WORKLOADS
    recording_block_rows: int = 1_000
    replicates: int = 10
    calibration_cycles: int = 2
    evaluation_cycles: int = 3
    top_k: int = 8
    window_size: int = 50
    lambda_res: float = 0.50
    weight_mode: str = "uniform"
    aggregation: str = "mean"
    threshold_quantile: float = 0.99
    persistence_blocks: int = 2
    boundary_window_blocks: int = 1
    eta: float = 0.01
    correlation_threshold: float = 0.35
    bootstrap_resamples: int = 10_000
    seed: int = 123

    @property
    def total_cycles(self) -> int:
        return self.calibration_cycles + self.evaluation_cycles

    @property
    def samples_per_phase(self) -> int:
        return self.recording_block_rows // self.total_cycles


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
        output = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo_root, text=True
        )
        return bool(output.strip())
    except Exception:
        return None


def _portable_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze randomized workload orders in preserved Intel benign telemetry."
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=_repo_root() / "data" / "telemetry" / "processed" / "ddr_data",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_repo_root() / "results" / "notebook_run" / "intel_workload_orders",
    )
    parser.add_argument("--setups", nargs="+", choices=("A", "B"), default=["A", "B"])
    parser.add_argument("--replicates", type=int, default=10)
    parser.add_argument("--recording-block-rows", type=int, default=1_000)
    parser.add_argument("--calibration-cycles", type=int, default=2)
    parser.add_argument("--evaluation-cycles", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--window-size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    return parser


def _validate_config(cfg: IntelWorkloadOrderConfig) -> None:
    if cfg.replicates <= 0:
        raise ValueError("replicates must be positive")
    if cfg.calibration_cycles < 2:
        raise ValueError("calibration_cycles must be at least two")
    if cfg.evaluation_cycles <= 0:
        raise ValueError("evaluation_cycles must be positive")
    if cfg.recording_block_rows % cfg.total_cycles:
        raise ValueError("recording_block_rows must be divisible by the total cycle count")
    if cfg.samples_per_phase < cfg.window_size:
        raise ValueError("each phase must contain at least one complete decision block")
    if cfg.samples_per_phase % cfg.window_size:
        raise ValueError("samples_per_phase must be divisible by window_size")
    if cfg.bootstrap_resamples < 1_000:
        raise ValueError("bootstrap_resamples must be at least 1000")


def _load_notebook_namespace(repo_root: Path) -> dict[str, object]:
    notebook_path = repo_root / "notebooks" / "exact_tcad_all_experiments.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    cells = {cell.get("id"): cell for cell in notebook["cells"]}
    missing = [cell_id for cell_id in NOTEBOOK_CELL_IDS if cell_id not in cells]
    if missing:
        raise RuntimeError(f"Required notebook cells are missing: {missing}")

    module_name = "_citadel_intel_workload_order_notebook"
    module = types.ModuleType(module_name)
    module.__file__ = str(notebook_path)
    sys.modules[module_name] = module
    namespace = module.__dict__
    progress_log = repo_root / "results" / "notebook_run" / "notebook_progress.log"
    saved_progress = progress_log.read_bytes() if progress_log.is_file() else None
    try:
        for cell_id in NOTEBOOK_CELL_IDS:
            source = "".join(cells[cell_id].get("source", []))
            exec(compile(source, f"{notebook_path.name}:{cell_id}", "exec"), namespace)
    finally:
        if saved_progress is not None:
            progress_log.write_bytes(saved_progress)
        elif progress_log.exists():
            progress_log.unlink()
    return namespace


def _phase_orders(workloads: tuple[str, ...], cycles: int, seed: int) -> list[list[str]]:
    rng = random.Random(int(seed))
    orders: list[list[str]] = []
    used: set[tuple[str, ...]] = set()
    previous: str | None = None
    for _ in range(cycles):
        for _attempt in range(10_000):
            candidate = list(workloads)
            rng.shuffle(candidate)
            key = tuple(candidate)
            if (previous is None or candidate[0] != previous) and key not in used:
                break
        else:
            raise RuntimeError("Could not create a unique boundary-safe workload order")
        orders.append(candidate)
        used.add(tuple(candidate))
        previous = candidate[-1]
    return orders


def _input_path(data_root: Path, setup: str, workload: str) -> Path:
    return data_root / f"{SETUP_PREFIX[setup]}_benign_{workload.lower()}.csv"


def _read_recording_block(path: Path, block_index: int, rows: int) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("rb") as handle:
        if handle.read(64).startswith(b"version https://git-lfs.github.com/spec"):
            raise RuntimeError(f"Git LFS object is not available: {path}")
    start = block_index * rows
    frame = pd.read_csv(path, skiprows=range(1, start + 1), nrows=rows)
    if len(frame) != rows:
        raise RuntimeError(
            f"{path.name} has only {len(frame)} rows for recording block {block_index}; "
            f"expected {rows}."
        )
    return frame


def _is_slow_pvt(feature: str) -> bool:
    upper = str(feature).upper()
    return "TEMP" in upper or "VOLTAGE" in upper


def _preprocess_recording(
    frame: pd.DataFrame,
    sanitize_columns,
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    clean = sanitize_columns(frame)
    audit: list[dict[str, str]] = []
    output_columns: dict[str, pd.Series] = {}
    for feature in clean.columns:
        values = pd.to_numeric(clean[feature], errors="coerce")
        if _is_slow_pvt(feature):
            output_feature = f"{feature}__delta"
            output_columns[output_feature] = values.diff()
            audit.append(
                {
                    "source_feature": str(feature),
                    "output_feature": output_feature,
                    "action": "converted_to_within_recording_first_difference",
                    "reason": "absolute PVT state can drift slowly; differencing is completed before sequence construction",
                }
            )
        else:
            output_columns[str(feature)] = values
            audit.append(
                {
                    "source_feature": str(feature),
                    "output_feature": str(feature),
                    "action": "retained_interval_metric",
                    "reason": "Intel PCM field is an interval count, interval energy, ratio, or occupancy value",
                }
            )
    return pd.DataFrame(output_columns, index=clean.index), audit


def _construct_sequence(
    recordings: dict[str, pd.DataFrame],
    orders: list[list[str]],
    cfg: IntelWorkloadOrderConfig,
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    phase_index = 0
    global_index = 0
    for cycle_index, order in enumerate(orders):
        source_start = cycle_index * cfg.samples_per_phase
        source_stop = source_start + cfg.samples_per_phase
        for cycle_position, workload in enumerate(order):
            part = recordings[workload].iloc[source_start:source_stop].copy()
            if len(part) != cfg.samples_per_phase:
                raise RuntimeError(f"Incomplete source segment for {workload}, cycle {cycle_index}")
            part.insert(0, "source_sample_index", np.arange(source_start, source_stop))
            part.insert(0, "sample_in_phase", np.arange(len(part)))
            part.insert(0, "cycle_position", cycle_position)
            part.insert(0, "cycle_index", cycle_index)
            part.insert(0, "phase_index", phase_index)
            part.insert(0, "workload", workload)
            part.insert(0, "idx", np.arange(global_index, global_index + len(part)))
            parts.append(part)
            phase_index += 1
            global_index += len(part)
    sequence = pd.concat(parts, ignore_index=True)
    sequence["scenario"] = "BENIGN"
    return sequence


def _aggregate_score(values: np.ndarray, mode: str) -> float:
    if mode == "mean":
        return float(np.mean(values))
    if mode == "median":
        return float(np.median(values))
    return float(np.max(values))


def _score_blocks(frame: pd.DataFrame, model, cfg: IntelWorkloadOrderConfig, score_samples) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (cycle, phase, workload), group in frame.groupby(
        ["cycle_index", "phase_index", "workload"], sort=True
    ):
        group = group.sort_values("idx").reset_index(drop=True)
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
                    "start_sequence_index": int(group["idx"].iloc[start]),
                    "end_sequence_index": int(group["idx"].iloc[stop - 1]),
                    "score": _aggregate_score(scores[start:stop], cfg.aggregation),
                }
            )
    return pd.DataFrame(rows).sort_values("start_sequence_index").reset_index(drop=True)


def _persistence_alarm(raw_alarm: np.ndarray, required: int) -> np.ndarray:
    run_length = 0
    output = np.zeros(len(raw_alarm), dtype=int)
    for index, alarm in enumerate(np.asarray(raw_alarm, dtype=int)):
        run_length = run_length + 1 if alarm else 0
        output[index] = int(run_length >= required)
    return output


def _bootstrap_interval(values: np.ndarray, resamples: int, seed: int) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan"), float("nan")
    if len(values) == 1:
        return float(values[0]), float(values[0])
    rng = np.random.default_rng(int(seed))
    indices = rng.integers(0, len(values), size=(resamples, len(values)))
    bootstrap_means = values[indices].mean(axis=1)
    low, high = np.quantile(bootstrap_means, [0.025, 0.975])
    return float(low), float(high)


def _summarize_replicates(
    results: pd.DataFrame, cfg: IntelWorkloadOrderConfig
) -> pd.DataFrame:
    metrics = (
        "overall_benign_fpr",
        "boundary_block_fpr",
        "within_phase_fpr",
        "reference_stale",
    )
    rows: list[dict[str, object]] = []
    for (setup, rule), group in results.groupby(["setup", "decision_rule"], sort=True):
        for metric_index, metric in enumerate(metrics):
            values = pd.to_numeric(group[metric], errors="coerce").to_numpy(dtype=float)
            finite = values[np.isfinite(values)]
            low, high = _bootstrap_interval(
                finite,
                cfg.bootstrap_resamples,
                cfg.seed + 1009 * metric_index + (0 if setup == "A" else 100_003),
            )
            rows.append(
                {
                    "setup": setup,
                    "decision_rule": rule,
                    "metric": metric,
                    "n_recording_block_replicates": len(finite),
                    "mean": float(np.mean(finite)) if len(finite) else float("nan"),
                    "sample_sd": float(np.std(finite, ddof=1)) if len(finite) > 1 else float("nan"),
                    "minimum": float(np.min(finite)) if len(finite) else float("nan"),
                    "maximum": float(np.max(finite)) if len(finite) else float("nan"),
                    "bootstrap_95_low": low,
                    "bootstrap_95_high": high,
                }
            )
    return pd.DataFrame(rows)


def _plot_variation(
    results: pd.DataFrame, summary: pd.DataFrame, path: Path
) -> None:
    metrics = (
        ("overall_benign_fpr", "Overall"),
        ("boundary_block_fpr", "First block after boundary"),
        ("within_phase_fpr", "Later blocks within phase"),
    )
    setup_order = [setup for setup in ("A", "B") if setup in set(results["setup"])]
    rule_order = ("current", "persistence")
    rule_colors = {"current": "#0B4F9C", "persistence": "#D94801"}
    rule_labels = {"current": "Current rule", "persistence": "Two block persistence"}
    offsets = {"current": -0.13, "persistence": 0.13}
    rng = np.random.default_rng(123)
    fig, axes = plt.subplots(1, 3, figsize=(14.4, 5.0), dpi=220, sharey=True)
    for axis, (metric, title) in zip(axes, metrics, strict=True):
        for setup_index, setup in enumerate(setup_order):
            for rule in rule_order:
                group = results[
                    (results["setup"] == setup) & (results["decision_rule"] == rule)
                ].sort_values("replicate_index")
                values = 100.0 * pd.to_numeric(group[metric], errors="coerce").to_numpy(dtype=float)
                center = setup_index + offsets[rule]
                jitter = rng.uniform(-0.045, 0.045, size=len(values))
                axis.scatter(
                    np.full(len(values), center) + jitter,
                    values,
                    s=52,
                    color=rule_colors[rule],
                    edgecolor="white",
                    linewidth=0.7,
                    alpha=0.82,
                    zorder=3,
                )
                row = summary[
                    (summary["setup"] == setup)
                    & (summary["decision_rule"] == rule)
                    & (summary["metric"] == metric)
                ].iloc[0]
                mean = 100.0 * float(row["mean"])
                sd = 100.0 * float(row["sample_sd"])
                axis.errorbar(
                    center,
                    mean,
                    yerr=sd,
                    fmt="D",
                    markersize=7.5,
                    color="#111827",
                    markerfacecolor="#FACC15",
                    markeredgewidth=1.1,
                    capsize=5,
                    linewidth=1.8,
                    zorder=4,
                )
        axis.set_title(title, fontsize=13, fontweight="bold", pad=10)
        axis.set_xticks(
            range(len(setup_order)),
            [f"Setup {setup}\n({SETUP_PREFIX[setup]})" for setup in setup_order],
        )
        axis.tick_params(axis="both", labelsize=10.5)
        axis.grid(axis="y", alpha=0.25, linewidth=0.8)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Benign false positive rate (%)", fontsize=12.5, fontweight="bold")
    legend_handles = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markersize=8,
            markerfacecolor=rule_colors[rule],
            markeredgecolor="white",
            label=rule_labels[rule],
        )
        for rule in rule_order
    ]
    legend_handles.append(
        plt.Line2D(
            [0],
            [0],
            marker="D",
            linestyle="none",
            markersize=8,
            markerfacecolor="#FACC15",
            markeredgecolor="#111827",
            label="Mean with sample SD",
        )
    )
    fig.legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.93),
        ncol=3,
        frameon=False,
        fontsize=10.5,
    )
    fig.suptitle(
        "Intel Benign Workload Order Stress Test",
        fontsize=18,
        fontweight="bold",
        y=0.995,
    )
    fig.text(
        0.5,
        0.005,
        "Points are nonoverlapping recording block replicates; workload boundaries are constructed, not continuously collected switches.",
        ha="center",
        fontsize=9.7,
        color="#475569",
    )
    fig.subplots_adjust(top=0.77, bottom=0.18, left=0.075, right=0.99, wspace=0.17)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _paper_text(summary: pd.DataFrame, cfg: IntelWorkloadOrderConfig) -> str:
    def _variation_phrase(value: float) -> str:
        if np.isfinite(value):
            return f"the sample standard deviation was {100 * value:.2f} percentage points"
        return "variation was not estimated from a single recording block"

    sentences = []
    for setup in ("A", "B"):
        subset = summary[
            (summary["setup"] == setup)
            & (summary["decision_rule"] == "current")
        ].set_index("metric")
        if subset.empty:
            continue
        overall = subset.loc["overall_benign_fpr"]
        boundary = subset.loc["boundary_block_fpr"]
        later = subset.loc["within_phase_fpr"]
        sentences.append(
            f"For Setup {setup}, the mean overall benign false positive rate was "
            f"{100 * overall['mean']:.2f} percent and "
            f"{_variation_phrase(float(overall['sample_sd']))}; the first block after a "
            f"constructed workload boundary averaged {100 * boundary['mean']:.2f} percent, "
            f"compared with {100 * later['mean']:.2f} percent for later within phase blocks."
        )
    replicate_label = (
        "one nonoverlapping recording block replicate"
        if cfg.replicates == 1
        else f"{cfg.replicates} nonoverlapping recording block replicates"
    )
    prefix = (
        f"Across {replicate_label}, workload orders were randomized, "
        "two cycles were used for calibration, and the frozen detector was evaluated on three held out cycles. "
    )
    limitation = (
        "Because the preserved workload files were collected separately and the original trial event mapping is unavailable, "
        "this is an offline workload order stress test and does not measure a physical workload switch transient."
    )
    return prefix + " ".join(sentences) + " " + limitation


def main() -> int:
    args = _parser().parse_args()
    cfg = IntelWorkloadOrderConfig(
        setups=tuple(args.setups),
        recording_block_rows=int(args.recording_block_rows),
        replicates=int(args.replicates),
        calibration_cycles=int(args.calibration_cycles),
        evaluation_cycles=int(args.evaluation_cycles),
        top_k=int(args.top_k),
        window_size=int(args.window_size),
        bootstrap_resamples=int(args.bootstrap_resamples),
        seed=int(args.seed),
    )
    _validate_config(cfg)
    repo_root = _repo_root()
    data_root = args.data_root.expanduser().resolve()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    namespace = _load_notebook_namespace(repo_root)
    sanitize_columns = namespace["_sanitize_telemetry_columns"]
    fit_cintas = namespace["fit_cintas_from_benign"]
    score_samples = namespace["score_samples"]
    rank_features = namespace["_rank_features_from_benign_only"]
    select_features = namespace["_selected_features"]

    input_paths = [
        _input_path(data_root, setup, workload)
        for setup in cfg.setups
        for workload in cfg.workloads
    ]
    missing = [path for path in input_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing Intel benign telemetry files: {missing}")

    all_rule_results: list[pd.DataFrame] = []
    all_block_results: list[pd.DataFrame] = []
    all_selected_features: list[pd.DataFrame] = []
    all_workload_results: list[pd.DataFrame] = []
    run_manifests: list[Path] = []
    for setup in cfg.setups:
        for replicate_index in range(cfg.replicates):
            run_seed = cfg.seed + 10_007 * replicate_index
            run_output = output / "runs" / f"setup_{setup}_block_{replicate_index + 1:02d}"
            run_output.mkdir(parents=True, exist_ok=True)
            print(
                f"Setup {setup}: recording block {replicate_index + 1}/{cfg.replicates}",
                flush=True,
            )
            recordings: dict[str, pd.DataFrame] = {}
            setup_audit: list[dict[str, str]] = []
            for workload in cfg.workloads:
                path = _input_path(data_root, setup, workload)
                raw = _read_recording_block(path, replicate_index, cfg.recording_block_rows)
                recordings[workload], audit = _preprocess_recording(raw, sanitize_columns)
                if not setup_audit:
                    setup_audit = audit

            orders = _phase_orders(cfg.workloads, cfg.total_cycles, run_seed)
            sequence = _construct_sequence(recordings, orders, cfg)
            metadata_columns = {
                "idx",
                "workload",
                "phase_index",
                "cycle_index",
                "cycle_position",
                "sample_in_phase",
                "source_sample_index",
                "scenario",
            }
            candidate_features = sorted(
                set(sequence.select_dtypes(include=[np.number]).columns) - metadata_columns
            )
            calibration = sequence[sequence["cycle_index"] < cfg.calibration_cycles].copy()
            evaluation = sequence[sequence["cycle_index"] >= cfg.calibration_cycles].copy()
            means = (
                calibration[candidate_features]
                .replace([np.inf, -np.inf], np.nan)
                .mean()
            )
            finite_features = [
                feature for feature in candidate_features if np.isfinite(means[feature])
            ]
            for frame in (calibration, evaluation):
                frame[finite_features] = frame[finite_features].replace(
                    [np.inf, -np.inf], np.nan
                )
                frame[finite_features] = frame[finite_features].fillna(means[finite_features])
            variable_features = [
                feature
                for feature in finite_features
                if calibration[feature].nunique(dropna=True) > 1
                and float(calibration[feature].std(ddof=1)) > 0.0
            ]
            if len(variable_features) < 2:
                raise RuntimeError(f"Setup {setup} block {replicate_index} has too few features")

            audit_frame = pd.DataFrame(setup_audit)
            audit_frame["calibration_quality"] = audit_frame["output_feature"].map(
                lambda feature: "usable" if feature in variable_features else "removed_nonfinite_or_constant"
            )
            audit_path = run_output / "preprocessing_audit.csv"
            audit_frame.to_csv(audit_path, index=False)

            base_model = fit_cintas(
                calibration,
                variable_features,
                lambda_res=cfg.lambda_res,
                weight_mode=cfg.weight_mode,
            )
            rank_input = calibration.copy()
            rank_input["cias_sample_score"] = score_samples(rank_input, base_model)
            ranks = rank_features(
                setup=setup,
                df_benign=rank_input,
                feature_cols=variable_features,
                out_root=run_output,
                corr_threshold=cfg.correlation_threshold,
                tag="two_cycle_calibration",
            )
            selected = select_features(ranks, min(cfg.top_k, len(variable_features)), variable_features)
            model = fit_cintas(
                calibration,
                selected,
                lambda_res=cfg.lambda_res,
                weight_mode=cfg.weight_mode,
            )
            reference_blocks = _score_blocks(
                calibration, model, cfg, score_samples
            )
            threshold = float(
                np.quantile(reference_blocks["score"], cfg.threshold_quantile)
            )
            blocks = _score_blocks(evaluation, model, cfg, score_samples)
            blocks["threshold"] = threshold
            blocks["alarm_raw"] = (blocks["score"] >= threshold).astype(int)
            blocks["alarm_persistence"] = _persistence_alarm(
                blocks["alarm_raw"].to_numpy(dtype=int), cfg.persistence_blocks
            )
            blocks["is_boundary_window"] = (
                blocks["block_index_in_phase"] < cfg.boundary_window_blocks
            )
            blocks.insert(0, "replicate_index", replicate_index + 1)
            blocks.insert(0, "setup", setup)
            all_block_results.append(blocks.copy())

            rule_rows: list[dict[str, object]] = []
            workload_rows: list[dict[str, object]] = []
            boundary_mask = blocks["is_boundary_window"].to_numpy(dtype=bool)
            for rule, alarm_column in (
                ("current", "alarm_raw"),
                ("persistence", "alarm_persistence"),
            ):
                alarms = blocks[alarm_column].to_numpy(dtype=int)
                overall = float(np.mean(alarms))
                boundary = float(np.mean(alarms[boundary_mask]))
                within = float(np.mean(alarms[~boundary_mask]))
                rule_rows.append(
                    {
                        "setup": setup,
                        "replicate_index": replicate_index + 1,
                        "seed": run_seed,
                        "decision_rule": rule,
                        "n_blocks": len(blocks),
                        "overall_benign_fpr": overall,
                        "boundary_block_fpr": boundary,
                        "within_phase_fpr": within,
                        "reference_stale": int(overall > cfg.eta),
                        "threshold": threshold,
                        "workload_orders": json.dumps(orders),
                    }
                )
                for workload, group in blocks.groupby("workload", sort=True):
                    workload_rows.append(
                        {
                            "setup": setup,
                            "replicate_index": replicate_index + 1,
                            "decision_rule": rule,
                            "workload": workload,
                            "n_blocks": len(group),
                            "benign_fpr": float(np.mean(group[alarm_column])),
                        }
                    )
            rule_frame = pd.DataFrame(rule_rows)
            rule_frame.to_csv(run_output / "rule_summary.csv", index=False)
            blocks.to_csv(run_output / "evaluation_block_scores.csv", index=False)
            reference_blocks.to_csv(run_output / "calibration_block_scores.csv", index=False)
            selected_frame = ranks[ranks["feature"].isin(selected)].copy()
            selected_frame["selected_order"] = selected_frame["feature"].map(
                {feature: index + 1 for index, feature in enumerate(selected)}
            )
            selected_frame.insert(0, "replicate_index", replicate_index + 1)
            selected_frame.insert(0, "setup", setup)
            selected_frame.sort_values("selected_order").to_csv(
                run_output / "selected_features.csv", index=False
            )
            all_rule_results.append(rule_frame)
            all_workload_results.append(pd.DataFrame(workload_rows))
            all_selected_features.append(selected_frame)

            run_manifest = run_output / "run_manifest.json"
            run_manifest.write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "setup": setup,
                        "recording_block_index": replicate_index,
                        "source_row_start": replicate_index * cfg.recording_block_rows,
                        "source_row_stop_exclusive": (replicate_index + 1)
                        * cfg.recording_block_rows,
                        "seed": run_seed,
                        "phase_orders": orders,
                        "selected_features": selected,
                        "threshold": threshold,
                        "source_boundary_status": (
                            "constructed from separately recorded workload files; "
                            "not a continuously observed hardware transition"
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            run_manifests.append(run_manifest)

    rule_results = pd.concat(all_rule_results, ignore_index=True)
    block_results = pd.concat(all_block_results, ignore_index=True)
    workload_results = pd.concat(all_workload_results, ignore_index=True)
    selected_results = pd.concat(all_selected_features, ignore_index=True)
    summary = _summarize_replicates(rule_results, cfg)
    workload_summary = (
        workload_results.groupby(["setup", "decision_rule", "workload"], as_index=False)
        .agg(
            n_replicates=("replicate_index", "nunique"),
            mean_benign_fpr=("benign_fpr", "mean"),
            sample_sd_benign_fpr=("benign_fpr", "std"),
            minimum_benign_fpr=("benign_fpr", "min"),
            maximum_benign_fpr=("benign_fpr", "max"),
        )
        .sort_values(["setup", "decision_rule", "workload"])
    )
    feature_frequency = (
        selected_results.groupby(["setup", "feature"], as_index=False)
        .agg(
            n_replicates_selected=("replicate_index", "nunique"),
            mean_selected_order=("selected_order", "mean"),
            minimum_selected_order=("selected_order", "min"),
            maximum_selected_order=("selected_order", "max"),
        )
        .sort_values(
            ["setup", "n_replicates_selected", "mean_selected_order", "feature"],
            ascending=[True, False, True, True],
        )
    )
    feature_frequency["fraction_of_replicates_selected"] = (
        feature_frequency["n_replicates_selected"] / cfg.replicates
    )

    rule_path = output / "intel_workload_order_run_results.csv"
    block_path = output / "intel_workload_order_block_results.csv"
    summary_path = output / "intel_workload_order_summary.csv"
    workload_path = output / "intel_workload_order_by_workload.csv"
    selected_path = output / "intel_workload_order_selected_features.csv"
    frequency_path = output / "intel_workload_order_feature_frequency.csv"
    figure_path = output / "fig_intel_workload_order_variation.png"
    paper_path = output / "intel_workload_order_paper_text.txt"
    rule_results.to_csv(rule_path, index=False)
    block_results.to_csv(block_path, index=False)
    summary.to_csv(summary_path, index=False)
    workload_summary.to_csv(workload_path, index=False)
    selected_results.to_csv(selected_path, index=False)
    feature_frequency.to_csv(frequency_path, index=False)
    _plot_variation(rule_results, summary, figure_path)
    paper_text = _paper_text(summary, cfg)
    paper_path.write_text(paper_text + "\n", encoding="utf-8")

    artifacts = (
        rule_path,
        block_path,
        summary_path,
        workload_path,
        selected_path,
        frequency_path,
        figure_path,
        paper_path,
    )
    manifest_path = output / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "status": "complete",
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "git_commit": _git_commit(repo_root),
                "git_dirty": _git_dirty(repo_root),
                "config": asdict(cfg),
                "interpretation_boundary": (
                    "The preserved workload files were collected separately. Constructed "
                    "boundaries test held-out workload-order sensitivity but do not contain "
                    "the physical transient of a continuously collected workload switch."
                ),
                "recording_block_boundary_status": (
                    "The original scripts requested ten 1000-row trials per workload, and each "
                    "preserved file contains 10000 rows. Original trial event identifiers are not "
                    "available, so the analysis reports nonoverlapping recording blocks rather "
                    "than independently verified trials."
                ),
                "inputs": [
                    {
                        "path": _portable_path(path, repo_root),
                        "sha256": _sha256(path),
                        "size_bytes": path.stat().st_size,
                    }
                    for path in input_paths
                ],
                "run_manifests": [
                    {
                        "path": _portable_path(path, repo_root),
                        "sha256": _sha256(path),
                    }
                    for path in run_manifests
                ],
                "artifacts": [
                    {
                        "path": _portable_path(path, repo_root),
                        "sha256": _sha256(path),
                        "size_bytes": path.stat().st_size,
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
