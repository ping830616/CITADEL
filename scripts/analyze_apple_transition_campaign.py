#!/usr/bin/env python3
"""Analyze all complete Apple transition runs and summarize run variation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_mpl_config = Path(tempfile.gettempdir()) / "citadel-matplotlib"
_mpl_config.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_config))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


METRICS = (
    "overall_benign_fpr",
    "transition_window_fpr",
    "steady_window_fpr",
    "median_blocks_to_stabilize",
    "maximum_blocks_to_stabilize",
    "unresolved_switches",
)
FPR_METRICS = (
    ("overall_benign_fpr", "Overall"),
    ("transition_window_fpr", "Transition window"),
    ("steady_window_fpr", "Steady window"),
)
PER_RUN_ARTIFACTS = (
    "transition_rule_summary.csv",
    "transition_event_summary.csv",
    "transition_selected_features.csv",
    "run_manifest.json",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run per trace analysis and aggregate an Apple transition campaign."
    )
    parser.add_argument("--campaign-dir", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--bootstrap-seed", type=int, default=123)
    parser.add_argument("--skip-per-run-analysis", action="store_true")
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


def _prepare_campaign_output(
    output: Path,
    run_results: list[dict[str, object]],
    *,
    skip_per_run_analysis: bool,
) -> Path:
    """Reserve a fresh campaign root or validate an intentional reuse."""
    runs_output = output / "runs"
    if not skip_per_run_analysis:
        if output.exists():
            raise FileExistsError(
                f"Campaign analysis output already exists: {output}. Choose a new "
                "--output-root; use --skip-per-run-analysis only to aggregate "
                "previously completed per-run bundles intentionally."
            )
        runs_output.mkdir(parents=True)
        return runs_output

    if not runs_output.is_dir():
        raise FileNotFoundError(
            "--skip-per-run-analysis requires an existing campaign runs directory: "
            f"{runs_output}"
        )
    missing: list[str] = []
    for run in run_results:
        run_index = int(run["run_index"])
        seed = int(run["seed"])
        run_output = runs_output / f"run_{run_index + 1:02d}_seed_{seed}"
        missing.extend(
            str(run_output / filename)
            for filename in PER_RUN_ARTIFACTS
            if not (run_output / filename).is_file()
        )
    if missing:
        raise FileNotFoundError(
            "--skip-per-run-analysis cannot reuse an incomplete per-run bundle; "
            f"missing artifacts: {missing}"
        )
    return runs_output


def _bootstrap_interval(
    values: np.ndarray, resamples: int, seed: int
) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan"), float("nan")
    if len(values) == 1:
        return float(values[0]), float(values[0])
    rng = np.random.default_rng(int(seed))
    indices = rng.integers(0, len(values), size=(int(resamples), len(values)))
    means = values[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def _aggregate(
    frame: pd.DataFrame, resamples: int, seed: int
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for rule, group in frame.groupby("decision_rule", sort=True):
        for metric_index, metric in enumerate(METRICS):
            values = pd.to_numeric(group[metric], errors="coerce").to_numpy(dtype=float)
            finite = values[np.isfinite(values)]
            low, high = _bootstrap_interval(
                finite, resamples, seed + 1009 * metric_index
            )
            rows.append(
                {
                    "decision_rule": rule,
                    "metric": metric,
                    "n_runs": int(len(finite)),
                    "mean": float(np.mean(finite)) if len(finite) else float("nan"),
                    "sample_sd": float(np.std(finite, ddof=1)) if len(finite) > 1 else float("nan"),
                    "minimum": float(np.min(finite)) if len(finite) else float("nan"),
                    "maximum": float(np.max(finite)) if len(finite) else float("nan"),
                    "bootstrap_95_low": low,
                    "bootstrap_95_high": high,
                }
            )
    return pd.DataFrame(rows)


def _plot_run_variation(frame: pd.DataFrame, aggregate: pd.DataFrame, path: Path) -> None:
    rule_order = [rule for rule in ("current", "persistence") if rule in set(frame["decision_rule"])]
    colors = {"current": "#0B4F9C", "persistence": "#D94801"}
    labels = {"current": "Current rule", "persistence": "Two block persistence"}
    fig, axes = plt.subplots(1, 3, figsize=(13.8, 4.7), dpi=220, sharey=True)
    rng = np.random.default_rng(123)
    for axis, (metric, title) in zip(axes, FPR_METRICS, strict=True):
        for rule_index, rule in enumerate(rule_order):
            subset = frame[frame["decision_rule"] == rule].sort_values("run_index")
            values = 100.0 * pd.to_numeric(subset[metric], errors="coerce").to_numpy(dtype=float)
            jitter = rng.uniform(-0.055, 0.055, size=len(values))
            axis.scatter(
                np.full(len(values), rule_index) + jitter,
                values,
                s=62,
                color=colors[rule],
                edgecolor="white",
                linewidth=0.8,
                alpha=0.88,
                zorder=3,
                label="Independent runs" if rule_index == 0 else None,
            )
            row = aggregate[
                (aggregate["decision_rule"] == rule) & (aggregate["metric"] == metric)
            ].iloc[0]
            mean = 100.0 * float(row["mean"])
            sd = 100.0 * float(row["sample_sd"]) if np.isfinite(row["sample_sd"]) else 0.0
            axis.errorbar(
                rule_index,
                mean,
                yerr=sd,
                fmt="D",
                markersize=8,
                color="#111827",
                markerfacecolor="#FACC15",
                markeredgewidth=1.2,
                capsize=6,
                linewidth=2.0,
                zorder=4,
            )
        axis.set_title(title, fontsize=13.5, fontweight="bold", pad=10)
        axis.set_xticks(range(len(rule_order)), [labels[rule] for rule in rule_order])
        axis.tick_params(axis="x", labelsize=10)
        axis.tick_params(axis="y", labelsize=10.5)
        axis.grid(axis="y", alpha=0.25, linewidth=0.8)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Benign false positive rate (%)", fontsize=12.5, fontweight="bold")
    fig.suptitle(
        "Variation Across Independent Randomized Workload Runs",
        fontsize=17,
        fontweight="bold",
        y=1.01,
    )
    fig.text(
        0.5,
        -0.01,
        "Circles: individual runs    Yellow diamonds: mean    Error bars: sample standard deviation",
        ha="center",
        fontsize=10.5,
        color="#334155",
    )
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    args = _parser().parse_args()
    if args.bootstrap_resamples < 1_000:
        raise ValueError("--bootstrap-resamples must be at least 1000")
    repo_root = _repo_root()
    campaign_root = repo_root / "data" / "telemetry" / "raw" / "apple_transition_campaigns"
    campaign_dir = (
        args.campaign_dir.expanduser().resolve()
        if args.campaign_dir
        else _latest_complete_campaign(campaign_root)
    )
    if campaign_dir is None:
        raise FileNotFoundError(f"No complete campaign found under {campaign_root}")
    campaign_manifest_path = campaign_dir / "campaign_manifest.json"
    campaign = json.loads(campaign_manifest_path.read_text(encoding="utf-8"))
    if campaign.get("status") != "complete":
        raise RuntimeError(f"Campaign is not complete: {campaign_manifest_path}")
    calibration_cycles = int(campaign["calibration_cycles"])
    output_root = (
        args.output_root.expanduser().resolve()
        if args.output_root
        else repo_root / "results" / "notebook_run" / "apple_transition_campaigns"
    )
    output = output_root / campaign_dir.name
    run_results = campaign.get("run_results", [])
    if not run_results:
        raise RuntimeError("Campaign contains no completed runs")
    for run in run_results:
        if run.get("collection_status") != "complete" or int(run.get("returncode", 1)) != 0:
            raise RuntimeError(f"Campaign contains an incomplete run: {run}")
    runs_output = _prepare_campaign_output(
        output,
        run_results,
        skip_per_run_analysis=bool(args.skip_per_run_analysis),
    )

    runner = repo_root / "scripts" / "run_apple_transition_analysis.py"
    all_rules: list[pd.DataFrame] = []
    all_events: list[pd.DataFrame] = []
    all_selected: list[pd.DataFrame] = []
    run_manifests: list[Path] = []
    for run in run_results:
        run_index = int(run["run_index"])
        seed = int(run["seed"])
        run_dir = repo_root / str(run["run_dir"])
        trace = run_dir / "transition_trace.csv"
        collection_manifest = run_dir / "collection_manifest.json"
        collection = json.loads(collection_manifest.read_text(encoding="utf-8"))
        run_output = runs_output / f"run_{run_index + 1:02d}_seed_{seed}"
        if not args.skip_per_run_analysis:
            subprocess.run(
                [
                    sys.executable,
                    str(runner),
                    "--trace",
                    str(trace),
                    "--output",
                    str(run_output),
                    "--calibration-cycles",
                    str(calibration_cycles),
                ],
                cwd=repo_root,
                check=True,
            )
        rule_path = run_output / "transition_rule_summary.csv"
        event_path = run_output / "transition_event_summary.csv"
        selected_path = run_output / "transition_selected_features.csv"
        analysis_manifest = run_output / "run_manifest.json"
        for required in (rule_path, event_path, selected_path, analysis_manifest):
            if not required.is_file():
                raise FileNotFoundError(f"Expected per run artifact is missing: {required}")
        rule = pd.read_csv(rule_path)
        phase_orders = collection.get("protocol", {}).get("phase_orders")
        if phase_orders is None:
            cycle_count = int(collection.get("protocol", {}).get("cycles", 0))
            phase_orders = [
                [
                    str(event["workload"])
                    for event in collection.get("events", [])
                    if int(event["cycle_index"]) == cycle_index
                ]
                for cycle_index in range(cycle_count)
            ]
        rule.insert(0, "run_index", run_index + 1)
        rule.insert(1, "seed", seed)
        rule.insert(2, "workload_orders", json.dumps(phase_orders))
        all_rules.append(rule)
        event = pd.read_csv(event_path)
        event.insert(0, "run_index", run_index + 1)
        event.insert(1, "seed", seed)
        all_events.append(event)
        selected = pd.read_csv(selected_path)
        selected.insert(0, "run_index", run_index + 1)
        selected.insert(1, "seed", seed)
        all_selected.append(selected)
        run_manifests.append(analysis_manifest)

    run_rules = pd.concat(all_rules, ignore_index=True)
    run_events = pd.concat(all_events, ignore_index=True)
    selected_features = pd.concat(all_selected, ignore_index=True)
    feature_frequency = (
        selected_features.groupby("feature", as_index=False)
        .agg(
            n_runs_selected=("run_index", "nunique"),
            mean_selected_order=("selected_order", "mean"),
            minimum_selected_order=("selected_order", "min"),
            maximum_selected_order=("selected_order", "max"),
        )
        .sort_values(["n_runs_selected", "mean_selected_order", "feature"], ascending=[False, True, True])
        .reset_index(drop=True)
    )
    feature_frequency["fraction_of_runs_selected"] = (
        feature_frequency["n_runs_selected"] / run_rules["run_index"].nunique()
    )
    aggregate = _aggregate(run_rules, args.bootstrap_resamples, args.bootstrap_seed)
    rules_path = output / "all_run_rule_results.csv"
    events_path = output / "all_run_event_results.csv"
    aggregate_path = output / "campaign_metric_summary.csv"
    selected_path = output / "all_run_selected_features.csv"
    feature_frequency_path = output / "campaign_feature_selection_frequency.csv"
    figure_path = output / "fig_transition_campaign_variation.png"
    run_rules.to_csv(rules_path, index=False)
    run_events.to_csv(events_path, index=False)
    aggregate.to_csv(aggregate_path, index=False)
    selected_features.to_csv(selected_path, index=False)
    feature_frequency.to_csv(feature_frequency_path, index=False)
    _plot_run_variation(run_rules, aggregate, figure_path)

    def metric_row(rule: str, metric: str) -> pd.Series:
        return aggregate[
            (aggregate["decision_rule"] == rule) & (aggregate["metric"] == metric)
        ].iloc[0]

    current_overall = metric_row("current", "overall_benign_fpr")
    current_transition = metric_row("current", "transition_window_fpr")
    persistence_overall = metric_row("persistence", "overall_benign_fpr")
    paper_text = (
        f"Across {int(current_overall.n_runs)} independent runs with randomized workload orders, "
        f"the current rule produced a mean overall benign false positive rate of "
        f"{100 * current_overall['mean']:.2f} percent (sample standard deviation "
        f"{100 * current_overall['sample_sd']:.2f} percentage points; 95 percent bootstrap interval "
        f"{100 * current_overall['bootstrap_95_low']:.2f} to {100 * current_overall['bootstrap_95_high']:.2f} percent). "
        f"Within transition windows, the corresponding mean was {100 * current_transition['mean']:.2f} percent "
        f"(sample standard deviation {100 * current_transition['sample_sd']:.2f} percentage points). "
        f"The two block persistence rule produced a mean overall false positive rate of "
        f"{100 * persistence_overall['mean']:.2f} percent (sample standard deviation "
        f"{100 * persistence_overall['sample_sd']:.2f} percentage points)."
    )
    paper_path = output / "campaign_paper_ready_result.txt"
    paper_path.write_text(paper_text + "\n", encoding="utf-8")
    artifacts = [
        rules_path,
        events_path,
        aggregate_path,
        selected_path,
        feature_frequency_path,
        figure_path,
        paper_path,
    ]
    manifest_payload = {
        "status": "complete",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_manifest": _portable_path(campaign_manifest_path, repo_root),
        "campaign_manifest_sha256": _sha256(campaign_manifest_path),
        "n_runs": int(run_rules["run_index"].nunique()),
        "bootstrap_resamples": int(args.bootstrap_resamples),
        "bootstrap_seed": int(args.bootstrap_seed),
        "per_run_analysis_manifests": [
            {"path": _portable_path(path, repo_root), "sha256": _sha256(path)}
            for path in run_manifests
        ],
        "artifacts": [
            {"path": _portable_path(path, repo_root), "sha256": _sha256(path)}
            for path in artifacts
        ],
    }
    manifest_path = output / "campaign_analysis_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "complete", "output": str(output), "paper_text": paper_text}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
