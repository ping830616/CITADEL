#!/usr/bin/env python3
"""Reproduce CITADEL graph/ranking sensitivity with archived baseline gates."""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


BASE_WEIGHTS: dict[str, float] = {}
TAU_VALUES: tuple[float, ...] = ()
PI_VALUES: tuple[float, ...] = ()
BASE_TAU = 0.0
BASE_PI = 0.0
SEED = 0
THREADS = 1
GRAPH_BOOTSTRAPS = 0
GRAPH_SUBSAMPLE_FRAC = 0.0
MAX_EDGES_PER_BOOT_FACTOR = 0
GRAPH_SETUP_SEEDS: dict[str, int] = {}


@dataclass(frozen=True)
class Case:
    setup: str
    scenario: str
    view: str
    top_k: int
    window_size: int
    agg_mode: str
    lambda_res: float
    weight_mode: str
    fixed_point_q: int
    p_quantile: float
    n_splits: int
    candidate_rank_path: str

    @property
    def case_id(self) -> str:
        return f"{self.setup}_{self.scenario}"


CASES: tuple[Case, ...] = ()

EXPECTED_CASES: dict[str, dict[str, Any]] = {
    "A_DROOP": {
        "setup": "A", "scenario": "DROOP", "view": "transient", "top_k": 15,
        "window_size": 1000, "agg_mode": "median", "lambda_res": 0.0,
        "weight_mode": "inv_var", "fixed_point_q": 15, "p_quantile": 0.99,
        "n_splits": 3,
        "candidate_rank_path": "results/notebook_run/droop_adaptive_ablation/p0_99/causal/SETUP_A_feature_ranks.csv",
    },
    "A_RH": {
        "setup": "A", "scenario": "RH", "view": "standard", "top_k": 20,
        "window_size": 550, "agg_mode": "median", "lambda_res": 1.0,
        "weight_mode": "uniform", "fixed_point_q": 8, "p_quantile": 0.99,
        "n_splits": 5,
        "candidate_rank_path": "results/notebook_run/tcad_ablation/causal/SETUP_A_feature_ranks.csv",
    },
    "B_DROOP": {
        "setup": "B", "scenario": "DROOP", "view": "transient", "top_k": 15,
        "window_size": 200, "agg_mode": "median", "lambda_res": 0.5,
        "weight_mode": "inv_var", "fixed_point_q": 15, "p_quantile": 0.99,
        "n_splits": 3,
        "candidate_rank_path": "results/notebook_run/droop_adaptive_ablation/p0_99/causal/SETUP_B_feature_ranks.csv",
    },
    "B_SPECTRE": {
        "setup": "B", "scenario": "SPECTRE", "view": "standard", "top_k": 30,
        "window_size": 700, "agg_mode": "median", "lambda_res": 0.75,
        "weight_mode": "uniform", "fixed_point_q": 8, "p_quantile": 0.99,
        "n_splits": 5,
        "candidate_rank_path": "results/notebook_run/tcad_ablation/causal/SETUP_B_feature_ranks.csv",
    },
}


def _configure(protocol: dict[str, Any]) -> None:
    global BASE_WEIGHTS, TAU_VALUES, PI_VALUES, BASE_TAU, BASE_PI
    global SEED, THREADS, GRAPH_BOOTSTRAPS, GRAPH_SUBSAMPLE_FRAC
    global MAX_EDGES_PER_BOOT_FACTOR, GRAPH_SETUP_SEEDS, CASES

    graph = protocol["graph"]
    ranking = protocol["ranking"]
    BASE_WEIGHTS = {key: float(value) for key, value in ranking["baseline_weights"].items()}
    TAU_VALUES = tuple(float(value) for value in graph["tau_c_values"])
    PI_VALUES = tuple(float(value) for value in graph["pi_min_values"])
    BASE_TAU = float(graph["baseline_tau_c"])
    BASE_PI = float(graph["baseline_pi_min"])
    SEED = int(protocol["seed"])
    THREADS = int(protocol["threads"])
    GRAPH_BOOTSTRAPS = int(graph["bootstraps"])
    GRAPH_SUBSAMPLE_FRAC = float(graph["workload_stratified_subsample_fraction"])
    MAX_EDGES_PER_BOOT_FACTOR = int(graph["max_edges_per_bootstrap_factor"])
    GRAPH_SETUP_SEEDS = {
        str(setup): int(seed) for setup, seed in graph["setup_bootstrap_seeds"].items()
    }
    CASES = tuple(Case(**case) for case in protocol["cases"])

    expected_weights = {
        "centrality": 0.35,
        "edge_stability": 0.25,
        "conditional_dependence": 0.20,
        "alignment": 0.20,
    }
    if BASE_WEIGHTS != expected_weights or abs(sum(BASE_WEIGHTS.values()) - 1.0) > 1e-12:
        raise ValueError("Ranking weights must be the disclosed c/e/d/a=(0.35,0.25,0.20,0.20)")
    removed_terms = list(ranking["removed_terms"])
    if len(removed_terms) != 4 or set(removed_terms) != set(expected_weights):
        raise ValueError("Ranking sensitivity must remove each c/e/d/a term exactly once")
    if (
        BASE_TAU != 0.35
        or BASE_PI != 0.50
        or len(TAU_VALUES) != 3
        or set(TAU_VALUES) != {0.25, 0.35, 0.45}
        or len(PI_VALUES) != 3
        or set(PI_VALUES) != {0.375, 0.50, 0.625}
    ):
        raise ValueError("Graph sensitivity axes must match the disclosed one-at-a-time protocol")
    if (
        SEED != 123
        or THREADS != 1
        or GRAPH_BOOTSTRAPS != 8
        or GRAPH_SUBSAMPLE_FRAC != 0.70
        or MAX_EDGES_PER_BOOT_FACTOR != 4
        or GRAPH_SETUP_SEEDS != {"A": 123, "B": 1132}
    ):
        raise ValueError("Seed, thread count, bootstrap protocol, or edge cap differs from the disclosed protocol")
    observed_cases = {case.case_id: asdict(case) for case in CASES}
    if len(CASES) != len(observed_cases) or observed_cases != EXPECTED_CASES:
        raise ValueError("Cases must match the four frozen Table VI configurations exactly")


def _runtime_versions() -> dict[str, str]:
    names = ["numpy", "pandas", "scikit-learn", "scipy", "matplotlib", "networkx"]
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def _check_runtime(protocol: dict[str, Any], *, allow_mismatch: bool) -> dict[str, Any]:
    observed = _runtime_versions()
    expected = {key: str(value) for key, value in protocol["runtime_versions"].items()}
    mismatches = {
        name: {"expected": version, "observed": observed.get(name, "not-installed")}
        for name, version in expected.items()
        if observed.get(name) != version
    }
    if mismatches and not allow_mismatch:
        details = ", ".join(
            f"{name}={item['observed']} (expected {item['expected']})"
            for name, item in mismatches.items()
        )
        raise RuntimeError(
            "Pinned numerical environment required for archive-compatible graph coefficients: "
            + details
            + ". Create/update the environment from environment.yml or use --allow-version-mismatch for diagnostics only."
        )
    return {"expected": expected, "observed": observed, "mismatches": mismatches}


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def _notebook_namespace(repo_root: Path) -> dict[str, Any]:
    notebook_path = repo_root / "notebooks" / "exact_tcad_all_experiments.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    results_root = repo_root / "results" / "notebook_run"
    data_root = repo_root / "data" / "telemetry" / "processed" / "ddr_data"
    namespace: dict[str, Any] = {
        "REPO_ROOT": repo_root,
        "SEED": SEED,
        "THREADS": THREADS,
        "SAMPLE_ROWS": 600,
        "DDR_DATA_ROOT": data_root,
        "APPLE_DATA_ROOT": repo_root / "data" / "telemetry" / "raw" / "apple_data",
        "REAL_DATA_ROOT": data_root,
        "APPLE_TIER_DATA_ROOT": repo_root / "data" / "telemetry" / "raw" / "apple_data",
        "DATA_SOURCE_CONFIG": repo_root / "data" / "external_sources.json",
        "DATA_MODE": "real",
        "TCAD_PRESET": "full",
        "RUN_REPEAT_CHECK": True,
        "RESULTS_ROOT": results_root,
        "DATA_ROOT": data_root,
        "TCAD_OUT": results_root / "tcad_ablation",
        "TCAD_REPEAT_OUT": results_root / "tcad_ablation_repeat",
        "LIFECYCLE_OUT": results_root / "lifecycle_drift",
        "FPGA_OUT": results_root / "fpga",
        "RTL_SWEEP_OUT": results_root / "rtl_sweep",
        "PROGRESS_LOG": results_root / "notebook_progress.log",
    }
    utility_cells = [
        cell for cell in notebook["cells"]
        if cell.get("id") == "integrated-utilities-code"
    ]
    if len(utility_cells) != 1:
        raise RuntimeError(
            "Expected exactly one notebook cell with id='integrated-utilities-code'"
        )
    exec("".join(utility_cells[0]["source"]), namespace)
    return namespace


def _is_lfs_pointer(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(64).startswith(b"version https://git-lfs.github.com/spec")


def _candidate_features(repo_root: Path, case: Case, pd) -> list[str]:
    path = repo_root / case.candidate_rank_path
    if _is_lfs_pointer(path):
        raise RuntimeError(f"Git LFS object is not materialized: {path}")
    features = sorted(pd.read_csv(path, usecols=["feature"])["feature"].astype(str).tolist())
    if not features:
        raise RuntimeError(f"No candidate features in {path}")
    if len(features) != len(set(features)):
        raise RuntimeError(f"Candidate feature names are not unique in {path}")
    return features


def _parse_scenario_workload(path: Path) -> tuple[str, str]:
    parts = path.stem.split("_")
    if len(parts) < 3:
        raise ValueError(f"Unexpected telemetry filename: {path.name}")
    return parts[1].upper(), parts[2].upper()


def _load_standard_frame(repo_root: Path, case: Case, features: list[str], pd, np):
    data_root = repo_root / "data" / "telemetry" / "processed" / "ddr_data"
    prefix = "DDR4_" if case.setup == "A" else "DDR5_"
    frames = []
    feature_set = set(features)
    source_paths = sorted(data_root.glob(f"{prefix}*.csv"))
    for index, path in enumerate(source_paths, 1):
        if _is_lfs_pointer(path):
            raise RuntimeError(f"Git LFS object is not materialized: {path}")
        frame = pd.read_csv(path, usecols=lambda col: str(col).strip() in feature_set)
        frame = frame.rename(columns={col: str(col).strip() for col in frame.columns})
        missing = feature_set.difference(frame.columns)
        if missing:
            raise RuntimeError(f"{path.name} is missing {len(missing)} candidate features")
        scenario, workload = _parse_scenario_workload(path)
        frame["setup"] = case.setup
        frame["scenario"] = scenario
        frame["workload"] = workload
        frame["time_idx"] = np.arange(len(frame), dtype=int)
        frame["is_anom"] = 0 if scenario == "BENIGN" else 1
        frame["label"] = frame["is_anom"]
        frames.append(frame)
        if index % 13 == 0:
            log(f"{case.case_id}: loaded {index}/{len(source_paths)} standard files")
    full = pd.concat(frames, ignore_index=True)
    return full.sort_values(["workload", "scenario", "time_idx"]).reset_index(drop=True), source_paths


def _load_droop_frame(repo_root: Path, case: Case, features: list[str], pd, np):
    data_root = repo_root / "results" / "notebook_run" / "droop_adaptive_data"
    prefix = "DDR4_" if case.setup == "A" else "DDR5_"
    source_paths = [
        path for path in sorted(data_root.glob(f"{prefix}*.csv"))
        if "_benign_" in path.name.lower() or "_droop_" in path.name.lower()
    ]
    if not source_paths:
        raise RuntimeError(f"No archived DROOP-adaptive files for Setup {case.setup}")
    frames = []
    feature_set = set(features)
    for index, path in enumerate(source_paths, 1):
        if _is_lfs_pointer(path):
            raise RuntimeError(
                f"Git LFS object is not materialized: {path}. "
                "Run git lfs pull --include='results/notebook_run/droop_adaptive_data/*.csv' --exclude=''"
            )
        frame = pd.read_csv(path, usecols=lambda col: str(col).strip() in feature_set)
        frame = frame.rename(columns={col: str(col).strip() for col in frame.columns})
        missing = feature_set.difference(frame.columns)
        if missing:
            raise RuntimeError(f"{path.name} is missing {len(missing)} DROOP candidate features")
        frame = frame[features].copy()
        scenario, workload = _parse_scenario_workload(path)
        frame["setup"] = case.setup
        frame["scenario"] = scenario
        frame["workload"] = workload
        frame["time_idx"] = np.arange(len(frame), dtype=int)
        frame["is_anom"] = 0 if scenario == "BENIGN" else 1
        frame["label"] = frame["is_anom"]
        frames.append(frame)
        if index % 13 == 0:
            log(f"{case.case_id}: loaded {index}/{len(source_paths)} archived DROOP files")
    full = pd.concat(frames, ignore_index=True)
    return full.sort_values(["workload", "scenario", "time_idx"]).reset_index(drop=True), source_paths


def _graph_stats_by_tau(df_benign, features: list[str], namespace: dict[str, Any]):
    np = namespace["np"]
    subsample = namespace["_workload_stratified_subsample"]
    gaussianize = namespace["_rank_gaussianize"]
    n_features = len(features)
    max_edges = max(n_features, MAX_EDGES_PER_BOOT_FACTOR * n_features)
    setup = str(df_benign["setup"].iloc[0])
    rng = np.random.default_rng(GRAPH_SETUP_SEEDS[setup])
    accumulators = {
        tau: {"count": {}, "signed": {}, "absolute": {}} for tau in TAU_VALUES
    }
    sample_hashes = []
    for bootstrap in range(GRAPH_BOOTSTRAPS):
        sub = subsample(df_benign, rng, GRAPH_SUBSAMPLE_FRAC)
        indices = np.asarray(sub.index, dtype=np.int64)
        sample_hashes.append({
            "bootstrap": bootstrap,
            "row_count": int(len(indices)),
            "index_sha256": hashlib.sha256(indices.tobytes()).hexdigest(),
        })
        x_frame = sub[features].astype(float).replace([np.inf, -np.inf], np.nan)
        x_frame = x_frame.fillna(x_frame.median(numeric_only=True)).fillna(0.0)
        if len(x_frame) < max(8, min(2 * n_features, 32)):
            x_frame = df_benign[features].astype(float).replace([np.inf, -np.inf], np.nan)
            x_frame = x_frame.fillna(x_frame.median(numeric_only=True)).fillna(0.0)
        z = gaussianize(x_frame)
        covariance = np.atleast_2d(np.cov(z, rowvar=False))
        average_variance = float(np.nanmean(np.diag(covariance))) if covariance.size else 1.0
        ridge = max(1e-4, 0.05 * average_variance)
        precision = np.linalg.pinv(covariance + ridge * np.eye(n_features))
        diagonal = np.sqrt(np.maximum(np.diag(precision), 1e-12))
        partial = -precision / np.outer(diagonal, diagonal)
        np.fill_diagonal(partial, 0.0)
        partial[~np.isfinite(partial)] = 0.0
        for tau in TAU_VALUES:
            d_min = max(0.08, 0.35 * tau)
            candidates = []
            for i in range(n_features):
                for j in range(i + 1, n_features):
                    value = float(partial[i, j])
                    absolute = abs(value)
                    if absolute >= d_min:
                        candidates.append((absolute, i, j, value))
            candidates.sort(reverse=True, key=lambda item: item[0])
            acc = accumulators[tau]
            for absolute, i, j, value in candidates[:max_edges]:
                key = (features[i], features[j]) if features[i] <= features[j] else (features[j], features[i])
                signed = value if key == (features[i], features[j]) else -value
                acc["count"][key] = acc["count"].get(key, 0) + 1
                acc["signed"][key] = acc["signed"].get(key, 0.0) + signed
                acc["absolute"][key] = acc["absolute"].get(key, 0.0) + absolute
        log(f"graph bootstrap {bootstrap + 1}/{GRAPH_BOOTSTRAPS} ({n_features} features)")
    return accumulators, sample_hashes


def _materialize_graph(
    features: list[str],
    accumulator: dict[str, dict],
    tau_c: float,
    pi_min: float,
    namespace: dict[str, Any],
):
    pd = namespace["pd"]
    assign_domain = namespace["assign_feature_domain"]
    telemetry_cost = namespace["feature_telemetry_cost"]
    d_min = max(0.08, 0.35 * tau_c)
    domains = {feature: assign_domain(feature) for feature in features}
    domain_order = {"CORE": 0, "MEMORY": 1, "SENSOR": 2, "OTHER": 3}
    candidate_records = []
    retained_records = []
    for (left, right), count in accumulator["count"].items():
        stability = float(count) / GRAPH_BOOTSTRAPS
        mean_abs = accumulator["absolute"][(left, right)] / max(count, 1)
        mean_signed = accumulator["signed"][(left, right)] / max(count, 1)
        retained = stability >= pi_min and mean_abs >= d_min
        dom_left, dom_right = domains[left], domains[right]
        if domain_order.get(dom_left, 99) < domain_order.get(dom_right, 99):
            src, dst, signed = left, right, mean_signed
        elif domain_order.get(dom_right, 99) < domain_order.get(dom_left, 99):
            src, dst, signed = right, left, -mean_signed
        else:
            src, dst, signed = (left, right, mean_signed) if left <= right else (right, left, -mean_signed)
        record = {
            "src": src,
            "dst": dst,
            "admitted_bootstraps": int(count),
            "rho": float(signed),
            "abs_rho": float(abs(mean_signed)),
            "mean_admitted_abs_partial": float(mean_abs),
            "edge_stability": float(stability),
            "dependence_score": float(mean_abs * stability),
            "retained_by_thresholds": bool(retained),
            "fallback_selected": False,
        }
        candidate_records.append(record)
        if retained:
            retained_records.append(record.copy())
    if not retained_records and candidate_records:
        fallback = sorted(
            candidate_records,
            reverse=True,
            key=lambda row: row["edge_stability"] * row["mean_admitted_abs_partial"],
        )[:max(1, min(len(candidate_records), len(features)))]
        fallback_pairs = {(row["src"], row["dst"]) for row in fallback}
        for row in candidate_records:
            if (row["src"], row["dst"]) in fallback_pairs:
                row["fallback_selected"] = True
        retained_records = [dict(row, fallback_selected=True) for row in fallback]
        graph_method = "stable_rank_precision_fallback"
    else:
        graph_method = "stable_rank_precision"
    for row in retained_records:
        row["graph_method"] = graph_method
    edges = pd.DataFrame(retained_records)
    if not edges.empty:
        edges = edges.sort_values(
            ["dependence_score", "src", "dst"],
            ascending=[False, True, True],
            kind="mergesort",
        ).reset_index(drop=True)
    weighted_degree = {feature: 0.0 for feature in features}
    stability_sum = {feature: 0.0 for feature in features}
    dependence_sum = {feature: 0.0 for feature in features}
    for row in edges.itertuples():
        weighted_degree[row.src] += float(row.dependence_score)
        weighted_degree[row.dst] += float(row.dependence_score)
        stability_sum[row.src] += float(row.edge_stability)
        stability_sum[row.dst] += float(row.edge_stability)
        dependence_sum[row.src] += float(row.abs_rho)
        dependence_sum[row.dst] += float(row.abs_rho)
    max_degree = max(max(weighted_degree.values()), 1e-8)
    max_stability = max(max(stability_sum.values()), 1e-8)
    max_dependence = max(max(dependence_sum.values()), 1e-8)
    nodes = pd.DataFrame({
        "feature": features,
        "domain": [domains[feature] for feature in features],
        "graph_centrality": [weighted_degree[feature] / max_degree for feature in features],
        "edge_stability": [stability_sum[feature] / max_stability for feature in features],
        "conditional_dependence": [dependence_sum[feature] / max_dependence for feature in features],
        "telemetry_cost": [telemetry_cost(feature) for feature in features],
        "graph_method": "stable_rank_precision",
    })
    candidates = pd.DataFrame(candidate_records)
    return edges, nodes, candidates, graph_method


def _effective_weights(removed_term: str | None) -> dict[str, float]:
    weights = BASE_WEIGHTS.copy()
    if removed_term:
        weights[removed_term] = 0.0
        total = sum(weights.values())
        weights = {name: value / total for name, value in weights.items()}
    return weights


def _rank_features(df, features, nodes, weights, droop_only: bool, namespace):
    pd = namespace["pd"]
    np = namespace["np"]
    alignment_fn = namespace["compute_feature_cias_alignment"]
    anchor_fn = namespace["droop_physics_anchor_score"]
    alignment = alignment_fn(df, features, score_col="cias_sample_score")
    align = np.array([alignment[feature] for feature in features], dtype=float)
    align = align / max(float(np.max(align)), 1e-8)
    indexed = nodes.set_index("feature")
    cost = indexed["telemetry_cost"].reindex(features).fillna(1.0).to_numpy(dtype=float)
    cost_norm = cost / max(float(np.max(cost)), 1e-8)
    centrality = indexed["graph_centrality"].reindex(features).fillna(0.0).to_numpy(dtype=float)
    stability = indexed["edge_stability"].reindex(features).fillna(0.0).to_numpy(dtype=float)
    dependence = indexed["conditional_dependence"].reindex(features).fillna(0.0).to_numpy(dtype=float)
    anchor = np.array([anchor_fn(feature) for feature in features], dtype=float)
    structural = (
        weights["centrality"] * centrality
        + weights["edge_stability"] * stability
        + weights["conditional_dependence"] * dependence
        + weights["alignment"] * align
    )
    if droop_only:
        raw = (0.30 * structural + 2.20 * anchor) / np.maximum(cost_norm, 1e-8)
    else:
        raw = structural / np.maximum(cost_norm, 1e-8)
    importance = raw / max(float(np.max(raw)), 1e-8)
    ranked = pd.DataFrame({
        "feature": features,
        "domain": indexed["domain"].reindex(features).tolist(),
        "graph_centrality": centrality,
        "edge_stability": stability,
        "conditional_dependence": dependence,
        "cias_alignment": align,
        "telemetry_cost": cost,
        "hardware_cost_penalty": cost_norm,
        "droop_anchor_score": anchor,
        "importance_score": importance,
        "importance_sort_score": np.round(importance, 12),
        "ranking_method": "stable_rank_precision_droop_anchor" if droop_only else "stable_rank_precision",
    })
    ranked = ranked.sort_values(
        ["importance_sort_score", "feature"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    return ranked


def _evaluate(case: Case, frame, selected: list[str], namespace):
    fit_model = namespace["fit_cintas_from_benign"]
    run_eval = namespace["run_exact_eval_for_setup"]
    model = fit_model(
        frame,
        selected,
        lambda_res=case.lambda_res,
        weight_mode=case.weight_mode,
    )
    return run_eval(
        setup=case.setup,
        df=frame,
        model=model,
        scenarios_eval=(case.scenario,),
        window_sizes=(case.window_size,),
        n_splits_list=(case.n_splits,),
        default_p_quantile=case.p_quantile,
        agg_mode=case.agg_mode,
        droop_cfg=None,
        seed=SEED,
    )


def _metric_summary(evaluation, pd) -> dict[str, Any]:
    global_rows = evaluation[evaluation["workload"].astype(str).str.upper() == "ALL"]
    metrics = ["auc_roc", "auc_pr", "f1", "bal_acc", "mcc", "fpr", "brier", "ece"]
    return {name: float(global_rows[name].mean()) for name in metrics}


def _jaccard(left: Iterable[str], right: Iterable[str]) -> tuple[int, int, float]:
    left_set, right_set = set(left), set(right)
    intersection = len(left_set.intersection(right_set))
    union = len(left_set.union(right_set))
    return intersection, union, float(intersection / union) if union else 1.0


def _baseline_expected(repo_root: Path, case: Case, pd) -> tuple[float, float]:
    summary = pd.read_csv(repo_root / "results/notebook_run/tcad_ablation/tcad_ablation_summary.csv", low_memory=False)
    mask = (
        (summary["setup"].astype(str) == case.setup)
        & (summary["scenario"].astype(str).str.upper() == case.scenario)
        & (summary["top_k"] == case.top_k)
        & (summary["window_size"] == case.window_size)
        & (summary["agg_mode"] == case.agg_mode)
        & (summary["lambda_res"] == case.lambda_res)
        & (summary["weight_mode"] == case.weight_mode)
        & (summary["fixed_point_q"] == case.fixed_point_q)
        & (summary["p_quantile"] == case.p_quantile)
    )
    rows = summary.loc[mask]
    if len(rows) != 1:
        raise RuntimeError(f"Expected one archived baseline row for {case.case_id}; found {len(rows)}")
    return float(rows.iloc[0]["mcc"]), float(rows.iloc[0]["fpr"])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_text(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()


def _parameter_label(value: float) -> str:
    return format(float(value), "g")


def _variant_specs(protocol: dict[str, Any]) -> list[tuple[str, str, float, float, str | None]]:
    specs: list[tuple[str, str, float, float, str | None]] = [
        ("graph_parameter", "baseline", BASE_TAU, BASE_PI, None)
    ]
    specs.extend(
        ("graph_parameter", f"tau_c_{_parameter_label(tau)}", tau, BASE_PI, None)
        for tau in TAU_VALUES
        if tau != BASE_TAU
    )
    specs.extend(
        ("graph_parameter", f"pi_min_{_parameter_label(pi)}", BASE_TAU, pi, None)
        for pi in PI_VALUES
        if pi != BASE_PI
    )
    specs.append(("ranking_term", "baseline", BASE_TAU, BASE_PI, None))
    specs.extend(
        ("ranking_term", f"remove_{term}", BASE_TAU, BASE_PI, term)
        for term in protocol["ranking"]["removed_terms"]
    )
    return specs


def _max_abs_delta(left, right, np) -> float:
    if left.size == 0:
        return 0.0
    return float(np.max(np.abs(left - right)))


def _endpoint_rows(frame, metric: str, value: float, scale: float, np) -> list[dict[str, Any]]:
    rows = frame[np.isclose(frame[metric].astype(float), value, rtol=0.0, atol=1e-15)]
    return [
        {
            "case_id": str(row.case_id),
            "setup": str(row.setup),
            "scenario": str(row.scenario),
            "variant": str(row.variant),
            "variant_id": str(row.variant_id),
            "raw_value": float(getattr(row, metric)),
            "reported_unit_value": float(getattr(row, metric)) * scale,
        }
        for row in rows.itertuples()
    ]


def _range_claim(frame, metric: str, *, scale: float, digits: int, expected: list[float], np) -> dict[str, Any]:
    raw_min = float(frame[metric].min())
    raw_max = float(frame[metric].max())
    observed = [raw_min * scale, raw_max * scale]
    observed_display = [f"{value:.{digits}f}" for value in observed]
    expected_display = [f"{float(value):.{digits}f}" for value in expected]
    return {
        "metric": metric,
        "scale_from_csv": scale,
        "display_decimal_places": digits,
        "observed": {
            "minimum": {
                "raw_value": raw_min,
                "reported_unit_value": observed[0],
                "display": observed_display[0],
                "source_rows": _endpoint_rows(frame, metric, raw_min, scale, np),
            },
            "maximum": {
                "raw_value": raw_max,
                "reported_unit_value": observed[1],
                "display": observed_display[1],
                "source_rows": _endpoint_rows(frame, metric, raw_max, scale, np),
            },
        },
        "draft_reference_display": expected_display,
        "matches_draft_at_reported_precision": observed_display == expected_display,
    }


def _build_claims(summary, protocol: dict[str, Any], baseline_validations: list[dict[str, Any]], np) -> dict[str, Any]:
    expected_cases = {case.case_id for case in CASES}
    observed_cases = set(summary["case_id"].astype(str))
    expected_variant_ids = {
        f"{case.case_id}:{family}:{variant}"
        for case in CASES
        for family, variant, _, _, _ in _variant_specs(protocol)
    }
    observed_variant_ids = summary["variant_id"].astype(str).tolist()
    variant_rows_complete = bool(
        len(observed_variant_ids) == len(expected_variant_ids)
        and len(observed_variant_ids) == len(set(observed_variant_ids))
        and set(observed_variant_ids) == expected_variant_ids
    )
    complete = bool(observed_cases == expected_cases and variant_rows_complete)
    ranges: dict[str, Any] = {}
    metric_specs = {
        "mcc": ("mcc", 1.0, 3),
        "fpr_percent": ("fpr", 100.0, 2),
        "feature_jaccard_percent": ("feature_jaccard", 100.0, 1),
    }
    for family in ("graph_parameter", "ranking_term"):
        included = summary[
            (summary["experiment_family"] == family)
            & summary["range_included"].astype(bool)
        ].copy()
        family_ranges: dict[str, Any] = {
            "row_count": int(len(included)),
            "membership_rule": protocol["range_membership"][family],
        }
        for output_name, (column, scale, digits) in metric_specs.items():
            family_ranges[output_name] = _range_claim(
                included,
                column,
                scale=scale,
                digits=digits,
                expected=protocol["draft_reference"][family][output_name],
                np=np,
            )
        family_ranges["matches_draft_at_reported_precision"] = all(
            family_ranges[name]["matches_draft_at_reported_precision"]
            for name in metric_specs
        )
        ranges[family] = family_ranges

    stability_checks = []
    for case_id, group in summary[summary["experiment_family"] == "graph_parameter"].groupby("case_id"):
        baseline = group[group["variant"] == "baseline"].iloc[0]
        changed = group[group["variant"].astype(str).str.startswith("pi_min_")]
        for row in changed.itertuples():
            exact = bool(
                np.isclose(float(row.mcc), float(baseline["mcc"]), rtol=0.0, atol=1e-15)
                and np.isclose(float(row.fpr), float(baseline["fpr"]), rtol=0.0, atol=1e-15)
            )
            reported = (
                f"{float(row.mcc):.3f}" == f"{float(baseline['mcc']):.3f}"
                and f"{100.0 * float(row.fpr):.2f}" == f"{100.0 * float(baseline['fpr']):.2f}"
            )
            stability_checks.append({
                "case_id": str(case_id),
                "variant": str(row.variant),
                "mcc": float(row.mcc),
                "fpr": float(row.fpr),
                "baseline_mcc": float(baseline["mcc"]),
                "baseline_fpr": float(baseline["fpr"]),
                "decision_metrics_exactly_preserved": exact,
                "decision_metrics_preserved_at_reported_precision": bool(reported),
            })

    worst_by_case: dict[str, Any] = {}
    ranking = summary[summary["experiment_family"] == "ranking_term"]
    for case_id, group in ranking.groupby("case_id"):
        baseline_mcc = float(group[group["variant"] == "baseline"].iloc[0]["mcc"])
        removals = group[group["variant"] != "baseline"].copy()
        removals["mcc_delta_from_baseline"] = removals["mcc"].astype(float) - baseline_mcc
        minimum_delta = float(removals["mcc_delta_from_baseline"].min())
        worst = removals[
            np.isclose(removals["mcc_delta_from_baseline"], minimum_delta, rtol=0.0, atol=1e-15)
        ]
        worst_by_case[str(case_id)] = {
            "baseline_mcc": baseline_mcc,
            "minimum_mcc_delta": minimum_delta,
            "variants": [str(value) for value in worst["variant"].tolist()],
        }

    expected_worst = protocol["draft_reference"].get("expected_largest_reduction", {})
    worst_checks = {
        case_id: {
            "expected": variant,
            "observed": worst_by_case.get(case_id, {}).get("variants", []),
            "matches": variant in worst_by_case.get(case_id, {}).get("variants", []),
        }
        for case_id, variant in expected_worst.items()
    }
    fallback_rows = summary[summary["fallback_used"].astype(bool)]
    tied_rows = summary[summary["top_k_boundary_tied_at_1e_12"].astype(bool)]
    baselines_pass = all(item["all_checks_pass"] for item in baseline_validations)
    ranges_pass = all(item["matches_draft_at_reported_precision"] for item in ranges.values())
    stability_pass = bool(
        len(stability_checks) == 2 * len(expected_cases)
        and all(item["decision_metrics_exactly_preserved"] for item in stability_checks)
    )
    worst_pass = all(item["matches"] for item in worst_checks.values())
    no_fallback = fallback_rows.empty
    tie_break_rule = str(protocol["ranking"].get("tie_break_rule", "")).strip()
    boundary_ties_resolved = bool(tie_break_rule)
    overall = bool(
        complete
        and baselines_pass
        and ranges_pass
        and stability_pass
        and worst_pass
        and no_fallback
        and boundary_ties_resolved
    )
    return {
        "schema_version": 1,
        "status": "PASS" if overall else ("INCOMPLETE" if not complete else "FAIL"),
        "complete_case_set": complete,
        "expected_cases": sorted(expected_cases),
        "observed_cases": sorted(observed_cases),
        "expected_variant_row_count": len(expected_variant_ids),
        "observed_variant_row_count": len(observed_variant_ids),
        "variant_rows_complete_and_unique": variant_rows_complete,
        "calculation_basis": "Extrema of arithmetic mean workload=ALL cross-validation fold metrics at the four frozen operating points.",
        "range_membership": protocol["range_membership"],
        "ranges": ranges,
        "stability_threshold_checks": stability_checks,
        "stability_threshold_metrics_preserved_exactly": stability_pass,
        "ranking_largest_mcc_reduction_by_case": worst_by_case,
        "draft_largest_reduction_checks": worst_checks,
        "baseline_validations": baseline_validations,
        "all_baseline_validations_pass": baselines_pass,
        "fallback_variant_ids": [str(value) for value in fallback_rows["variant_id"].tolist()],
        "no_graph_fallback_used": no_fallback,
        "top_k_boundary_tie_variant_ids": [str(value) for value in tied_rows["variant_id"].tolist()],
        "top_k_boundary_tie_break_rule": tie_break_rule,
        "all_top_k_boundary_ties_resolved": boundary_ties_resolved,
        "draft_claims_match_at_reported_precision": overall,
        "interpretation_limits": [
            "This is one-at-a-time sensitivity, not a joint parameter grid or seed-robustness study.",
            "Feature Jaccard is selected top-k set overlap, not graph-edge overlap, rank correlation, or a confidence interval.",
            "MCC and FPR ranges are extrema of mean cross-validation metrics, not uncertainty intervals or field guarantees.",
            "Feature discovery precedes cross-validation, matching the disclosed rank-before-fold design.",
        ],
    }


def _source_label(endpoint: dict[str, Any]) -> str:
    return "; ".join(
        f"{row['case_id']} / {row['variant']}"
        for row in endpoint["source_rows"]
    )


def _render_readme(claims: dict[str, Any]) -> str:
    lines = [
        "# Graph and ranking sensitivity evidence",
        "",
        f"**Scientific claim check: {claims['status']}. Archival provenance: {claims['archival_provenance_status']}.** The values below are calculated from the generated summary; the manuscript ranges are comparison targets only.",
        "",
        "## Reproduced ranges",
        "",
        "| Study family | MCC | Benign FPR | Baseline top-k Jaccard | Matches draft precision |",
        "|---|---:|---:|---:|:---:|",
    ]
    labels = {
        "graph_parameter": "Graph parameters",
        "ranking_term": "Ranking-term removals",
    }
    for family in ("graph_parameter", "ranking_term"):
        item = claims["ranges"][family]
        mcc = item["mcc"]["observed"]
        fpr = item["fpr_percent"]["observed"]
        jac = item["feature_jaccard_percent"]["observed"]
        lines.append(
            f"| {labels[family]} | {mcc['minimum']['display']}–{mcc['maximum']['display']} | "
            f"{fpr['minimum']['display']}%–{fpr['maximum']['display']}% | "
            f"{jac['minimum']['display']}%–{jac['maximum']['display']}% | "
            f"{'yes' if item['matches_draft_at_reported_precision'] else 'no'} |"
        )
    lines.extend([
        "",
        "Graph ranges include the shared baseline. Ranking ranges include only the four removal variants; their baseline rows are archived as references.",
        "",
        "## Endpoint provenance",
        "",
        "| Family / metric | Minimum source | Maximum source |",
        "|---|---|---|",
    ])
    for family in ("graph_parameter", "ranking_term"):
        for metric_name, label in (
            ("mcc", "MCC"),
            ("fpr_percent", "benign FPR"),
            ("feature_jaccard_percent", "top-k Jaccard"),
        ):
            observed = claims["ranges"][family][metric_name]["observed"]
            lines.append(
                f"| {labels[family]} / {label} | {_source_label(observed['minimum'])} | {_source_label(observed['maximum'])} |"
            )
    lines.extend([
        "",
        "## Baseline gates",
        "",
        "| Case | Graph edges | Rank values | Top-k set | MCC/FPR |",
        "|---|:---:|:---:|:---:|:---:|",
    ])
    for item in claims["baseline_validations"]:
        yn = lambda value: "yes" if value else "no"
        lines.append(
            f"| {item['case_id']} | {yn(item['edge_identities_match'] and item['edge_values_match'])} | "
            f"{yn(item['rank_values_match'])} | {yn(item['top_k_set_match'])} | {yn(item['metrics_match'])} |"
        )
    lines.extend([
        "",
        "Every baseline gate must pass before the sensitivity outputs are accepted. No graph fallback is allowed. Primary-score ties at a top-k boundary are resolved with the protocol's variant-neutral rounded-score/lexical rule and listed in the claim audit.",
        "",
        "## Files",
        "",
        "- `graph_sensitivity_summary.csv`: one row per case and variant with mean global CV metrics and overlap counts.",
        "- `graph_sensitivity_fold_results.csv`: fold and workload rows underlying every summary value.",
        "- `graph_sensitivity_selected_features.csv`: one row per selected feature and variant.",
        "- `graph_sensitivity_feature_ranks.csv`: complete feature rankings and term values.",
        "- `graph_sensitivity_graph_edges.csv`: admitted graph-edge audit rows, including retention and fallback flags.",
        "- `graph_sensitivity_claims.json`: machine-readable extrema, source rows, and pass/fail checks.",
        "- `protocol.json`: exact one-at-a-time protocol copied into the evidence bundle.",
        "- `selected_operating_points.json`: the four frozen Table VI configurations.",
        "- `run_manifest.json`: code/data/output hashes, runtime versions, graph subsample hashes, and baseline validations.",
        "",
        "## Reproduce",
        "",
        "From the repository root, materialize Git LFS data and run:",
        "",
        "```bash",
        "git lfs pull --include='data/telemetry/processed/ddr_data/*.csv,results/notebook_run/droop_adaptive_data/*.csv,results/notebook_run/tcad_ablation/tcad_ablation_summary.csv,results/notebook_run/tcad_ablation/causal/*.csv,results/notebook_run/droop_adaptive_ablation/p0_99/causal/*.csv' --exclude=''",
        "conda env update -f environment.yml --prune",
        "conda activate citadel-slm",
        "export PYTHONHASHSEED=123",
        "python scripts/run_graph_sensitivity.py",
        "```",
        "",
        "The direct command requires a clean checkout for archival provenance. The notebook contains a matching display cell that explicitly permits a dirty development run because notebook autosave changes execution metadata; such a manifest is marked `DEVELOPMENT_DIRTY_WORKTREE` and must not replace the committed archival bundle.",
        "",
    ])
    return "\n".join(lines)


def _display_path(repo_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _file_record(repo_root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": _display_path(repo_root, path),
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def run(
    repo_root: Path,
    output_root: Path,
    protocol: dict[str, Any],
    config_path: Path,
    runtime_check: dict[str, Any],
    only_case: str | None = None,
    allow_dirty: bool = False,
) -> dict[str, Any]:
    run_started = time.time()
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ[name] = str(THREADS)
    os.environ.setdefault("MPLBACKEND", "Agg")

    repository_commit = _git_text(repo_root, "rev-parse", "HEAD")
    git_status_at_start = _git_text(repo_root, "status", "--porcelain")
    runtime_archival_ok = bool(
        not runtime_check["mismatches"]
        and os.environ.get("PYTHONHASHSEED") == str(SEED)
    )
    canonical_config_path = (repo_root / "configs" / "graph_sensitivity.json").resolve()
    if git_status_at_start:
        archival_provenance_status = "DEVELOPMENT_DIRTY_WORKTREE"
    elif not runtime_archival_ok:
        archival_provenance_status = "DIAGNOSTIC_RUNTIME_MISMATCH"
    elif config_path.resolve() != canonical_config_path:
        archival_provenance_status = "DIAGNOSTIC_NONCANONICAL_CONFIG"
    else:
        archival_provenance_status = "PASS"
    if git_status_at_start and not only_case and not allow_dirty:
        raise RuntimeError(
            "A complete archival sensitivity run requires a clean git checkout so its "
            "manifest identifies the exact executable code. Commit or stash the listed "
            f"changes first:\n{git_status_at_start}\nFor an explicitly non-archival notebook/development "
            "run, pass --allow-dirty; the manifest will mark its provenance accordingly."
        )
    canonical_output_root = (repo_root / "results" / "notebook_run" / "graph_sensitivity").resolve()
    if (
        (only_case or archival_provenance_status != "PASS")
        and output_root.resolve() == canonical_output_root
    ):
        raise RuntimeError(
            "A partial or non-archival run cannot overwrite the canonical graph_sensitivity bundle. "
            "Choose a separate --output-root such as results/notebook_run/graph_sensitivity_development."
        )
    try:
        repository_remote = _git_text(repo_root, "config", "--get", "remote.origin.url")
    except subprocess.CalledProcessError:
        repository_remote = ""

    namespace = _notebook_namespace(repo_root)
    pd, np = namespace["pd"], namespace["np"]
    output_root.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, Any]] = []
    fold_frames = []
    selected_rows: list[dict[str, Any]] = []
    rank_frames = []
    edge_frames = []
    case_manifests = []
    baseline_validations: list[dict[str, Any]] = []
    input_paths = {
        config_path,
        repo_root / "notebooks" / "exact_tcad_all_experiments.ipynb",
        repo_root / "scripts" / "run_graph_sensitivity.py",
        repo_root / "results/notebook_run/tcad_ablation/tcad_ablation_summary.csv",
        repo_root / "requirements.txt",
        repo_root / "environment.yml",
    }
    selected_cases = [case for case in CASES if not only_case or case.case_id == only_case]
    if not selected_cases:
        raise ValueError(f"Unknown case id: {only_case}")

    for case in selected_cases:
        case_start = time.time()
        log(f"starting {case.case_id} ({case.view})")
        rank_archive_path = repo_root / case.candidate_rank_path
        edge_archive_path = repo_root / case.candidate_rank_path.replace("feature_ranks", "causal_edges")
        input_paths.update({rank_archive_path, edge_archive_path})
        features = _candidate_features(repo_root, case, pd)
        if case.view == "transient":
            raw_frame, source_paths = _load_droop_frame(repo_root, case, features, pd, np)
        else:
            raw_frame, source_paths = _load_standard_frame(repo_root, case, features, pd, np)
        input_paths.update(source_paths)
        frame = namespace["clean_and_debias_telemetry"](raw_frame)
        del raw_frame
        gc.collect()
        base_model = namespace["fit_cintas_from_benign"](
            frame, features, lambda_res=0.5, weight_mode="uniform"
        )
        provisional_score, _, _ = base_model.score_dataframe(frame)
        frame = pd.concat(
            [frame.copy(), pd.Series(provisional_score, index=frame.index, name="cias_sample_score")],
            axis=1,
        ).copy()
        benign = frame[frame["scenario"].astype(str).str.upper() == "BENIGN"]
        accumulators, subsample_hashes = _graph_stats_by_tau(benign, features, namespace)

        graph_pairs = [(BASE_TAU, BASE_PI)]
        graph_pairs.extend((tau, BASE_PI) for tau in TAU_VALUES if tau != BASE_TAU)
        graph_pairs.extend((BASE_TAU, pi) for pi in PI_VALUES if pi != BASE_PI)
        graph_cache = {
            pair: _materialize_graph(features, accumulators[pair[0]], pair[0], pair[1], namespace)
            for pair in graph_pairs
        }

        baseline_edges, baseline_nodes, _, _ = graph_cache[(BASE_TAU, BASE_PI)]
        archived_edges = pd.read_csv(edge_archive_path)
        edge_keys = ["src", "dst"]
        edge_ids_match = set(map(tuple, baseline_edges[edge_keys].to_numpy())) == set(
            map(tuple, archived_edges[edge_keys].to_numpy())
        )
        edge_max_delta = None
        edge_values_match = False
        if edge_ids_match:
            edge_numeric = ["rho", "abs_rho", "edge_stability", "dependence_score"]
            observed_edge_values = baseline_edges.set_index(edge_keys)[edge_numeric].sort_index().to_numpy(dtype=float)
            archived_edge_values = archived_edges.set_index(edge_keys)[edge_numeric].sort_index().to_numpy(dtype=float)
            edge_max_delta = _max_abs_delta(observed_edge_values, archived_edge_values, np)
            edge_values_match = bool(
                np.allclose(observed_edge_values, archived_edge_values, rtol=1e-10, atol=1e-12)
            )

        base_ranks = _rank_features(
            frame, features, baseline_nodes, BASE_WEIGHTS, case.view == "transient", namespace
        )
        baseline_selected = base_ranks.head(case.top_k)["feature"].tolist()
        archived_ranks = pd.read_csv(rank_archive_path)
        feature_universe_match = set(base_ranks["feature"]) == set(
            archived_ranks["feature"].astype(str)
        )
        rank_max_delta = None
        rank_values_match = False
        if feature_universe_match:
            rank_numeric = [
                "importance_score",
                "graph_centrality",
                "edge_stability",
                "conditional_dependence",
                "cias_alignment",
                "telemetry_cost",
                "hardware_cost_penalty",
                "droop_anchor_score",
            ]
            observed_rank_values = base_ranks.set_index("feature")[rank_numeric].sort_index().to_numpy(dtype=float)
            archived_rank_values = archived_ranks.set_index("feature")[rank_numeric].sort_index().to_numpy(dtype=float)
            rank_max_delta = _max_abs_delta(observed_rank_values, archived_rank_values, np)
            rank_values_match = bool(
                np.allclose(observed_rank_values, archived_rank_values, rtol=1e-10, atol=1e-12)
            )
        archived_selected = archived_ranks.head(case.top_k)["feature"].astype(str).tolist()
        top_k_set_match = set(baseline_selected) == set(archived_selected)
        rank_order_match = base_ranks["feature"].tolist() == archived_ranks["feature"].astype(str).tolist()

        structural_checks = {
            "edge_identities_match": edge_ids_match,
            "edge_values_match": edge_values_match,
            "feature_universe_match": feature_universe_match,
            "rank_values_match": rank_values_match,
            "top_k_set_match": top_k_set_match,
        }
        if not all(structural_checks.values()):
            detail = ", ".join(f"{name}={value}" for name, value in structural_checks.items())
            raise AssertionError(
                f"{case.case_id}: archived baseline structural validation failed ({detail}); "
                "use the versions pinned in environment.yml"
            )

        evaluation_cache = {}
        for family, variant, tau_c, pi_min, removed_term in _variant_specs(protocol):
            edges, nodes, candidates, graph_method = graph_cache[(tau_c, pi_min)]
            weights = _effective_weights(removed_term)
            ranks = _rank_features(
                frame, features, nodes, weights, case.view == "transient", namespace
            )
            ranking_method = str(ranks["ranking_method"].iloc[0])
            selected = ranks.head(case.top_k)["feature"].tolist()
            selection_key = tuple(selected)
            if selection_key not in evaluation_cache:
                evaluation_cache[selection_key] = _evaluate(case, frame, selected, namespace)
            evaluation = evaluation_cache[selection_key].copy()
            metrics = _metric_summary(evaluation, pd)
            intersection, union, jaccard = _jaccard(baseline_selected, selected)
            gap = None
            sort_gap = None
            tied_at_boundary = False
            if len(ranks) > case.top_k:
                gap = float(
                    ranks.iloc[case.top_k - 1]["importance_score"]
                    - ranks.iloc[case.top_k]["importance_score"]
                )
                sort_gap = float(
                    ranks.iloc[case.top_k - 1]["importance_sort_score"]
                    - ranks.iloc[case.top_k]["importance_sort_score"]
                )
                tied_at_boundary = sort_gap == 0.0
            variant_id = f"{case.case_id}:{family}:{variant}"
            range_included = family == "graph_parameter" or variant != "baseline"
            common = {
                "variant_id": variant_id,
                "case_id": case.case_id,
                "setup": case.setup,
                "scenario": case.scenario,
                "view": case.view,
                "experiment_family": family,
                "variant": variant,
                "is_reference_baseline": variant == "baseline",
                "range_included": range_included,
                "removed_term": removed_term or "",
                "tau_c": tau_c,
                "d_min": max(0.08, 0.35 * tau_c),
                "pi_min": pi_min,
                "top_k": case.top_k,
                "window_size": case.window_size,
                "agg_mode": case.agg_mode,
                "lambda_res": case.lambda_res,
                "weight_mode": case.weight_mode,
                "fixed_point_q": case.fixed_point_q,
                "p_quantile": case.p_quantile,
                "n_splits": case.n_splits,
                "centrality_weight": weights["centrality"],
                "edge_stability_weight": weights["edge_stability"],
                "conditional_dependence_weight": weights["conditional_dependence"],
                "alignment_weight": weights["alignment"],
                "droop_structural_weight": 0.30 if case.view == "transient" else 0.0,
                "droop_prior_weight": 2.20 if case.view == "transient" else 0.0,
                "graph_method": graph_method,
                "ranking_method": ranking_method,
                "retained_edge_count": len(edges),
                "fallback_used": graph_method.endswith("fallback"),
                "selected_feature_count": len(selected),
                "baseline_intersection_count": intersection,
                "baseline_union_count": union,
                "feature_jaccard": jaccard,
                "top_k_boundary_importance_gap": gap,
                "top_k_boundary_importance_sort_gap": sort_gap,
                "top_k_boundary_tied_at_1e_12": tied_at_boundary,
                "top_k_boundary_tie_break_rule": protocol["ranking"]["tie_break_rule"],
                "selected_features": "|".join(selected),
            }
            summary_rows.append({**common, **metrics})
            for key, value in common.items():
                evaluation[key] = value
            fold_frames.append(evaluation)
            for selection_rank, feature in enumerate(selected, 1):
                feature_row = ranks[ranks["feature"] == feature].iloc[0]
                selected_rows.append({
                    **{key: value for key, value in common.items() if key != "selected_features"},
                    "selection_rank": selection_rank,
                    "feature": feature,
                    "importance_score": float(feature_row["importance_score"]),
                    "in_baseline_top_k": feature in set(baseline_selected),
                })
            rank_copy = ranks.copy()
            for key, value in common.items():
                if key != "selected_features":
                    rank_copy[key] = value
            rank_copy["selected"] = rank_copy["rank"] <= case.top_k
            rank_frames.append(rank_copy)
            if family == "graph_parameter":
                candidate_copy = candidates.copy()
                for key, value in common.items():
                    if key != "selected_features":
                        candidate_copy[key] = value
                edge_frames.append(candidate_copy)
            log(
                f"{case.case_id} {family}/{variant}: MCC={metrics['mcc']:.6f} "
                f"FPR={100 * metrics['fpr']:.3f}% J={100 * jaccard:.1f}% features={len(selected)}"
            )

        observed_baseline = next(
            row for row in summary_rows
            if row["case_id"] == case.case_id
            and row["experiment_family"] == "graph_parameter"
            and row["variant"] == "baseline"
        )
        expected_mcc, expected_fpr = _baseline_expected(repo_root, case, pd)
        mcc_delta = abs(observed_baseline["mcc"] - expected_mcc)
        fpr_delta = abs(observed_baseline["fpr"] - expected_fpr)
        metrics_match = mcc_delta <= 1e-12 and fpr_delta <= 1e-12
        validation = {
            "case_id": case.case_id,
            "edge_identities_match": edge_ids_match,
            "edge_values_match": edge_values_match,
            "edge_numeric_max_abs_delta": edge_max_delta,
            "feature_universe_match": feature_universe_match,
            "rank_values_match": rank_values_match,
            "rank_numeric_max_abs_delta": rank_max_delta,
            "rank_order_match": rank_order_match,
            "top_k_set_match": top_k_set_match,
            "archived_mcc": expected_mcc,
            "observed_mcc": observed_baseline["mcc"],
            "mcc_abs_delta": mcc_delta,
            "archived_fpr": expected_fpr,
            "observed_fpr": observed_baseline["fpr"],
            "fpr_abs_delta": fpr_delta,
            "metrics_match": metrics_match,
        }
        validation["all_checks_pass"] = all(structural_checks.values()) and metrics_match
        baseline_validations.append(validation)
        if not metrics_match:
            raise AssertionError(
                f"{case.case_id}: baseline metrics do not reproduce the archived selected operating point"
            )
        case_manifests.append({
            **asdict(case),
            "case_id": case.case_id,
            "candidate_feature_count": len(features),
            "row_count": len(frame),
            "benign_row_count": len(benign),
            "candidate_rank_archive": str(rank_archive_path.relative_to(repo_root)),
            "edge_archive": str(edge_archive_path.relative_to(repo_root)),
            "source_files": [str(path.relative_to(repo_root)) for path in source_paths],
            "graph_subsamples": subsample_hashes,
            "baseline_validation": validation,
            "runtime_seconds": time.time() - case_start,
        })
        del frame, benign, accumulators, graph_cache, evaluation_cache
        gc.collect()

    summary = pd.DataFrame(summary_rows)
    folds = pd.concat(fold_frames, ignore_index=True, sort=False)
    selected = pd.DataFrame(selected_rows)
    ranks = pd.concat(rank_frames, ignore_index=True, sort=False)
    edges = pd.concat(edge_frames, ignore_index=True, sort=False)

    output_paths = {
        "summary": output_root / "graph_sensitivity_summary.csv",
        "fold_results": output_root / "graph_sensitivity_fold_results.csv",
        "selected_features": output_root / "graph_sensitivity_selected_features.csv",
        "feature_ranks": output_root / "graph_sensitivity_feature_ranks.csv",
        "graph_edges": output_root / "graph_sensitivity_graph_edges.csv",
        "claims": output_root / "graph_sensitivity_claims.json",
        "protocol": output_root / "protocol.json",
        "selected_operating_points": output_root / "selected_operating_points.json",
        "readme": output_root / "README.md",
    }
    summary.to_csv(output_paths["summary"], index=False)
    folds.to_csv(output_paths["fold_results"], index=False)
    selected.to_csv(output_paths["selected_features"], index=False)
    ranks.to_csv(output_paths["feature_ranks"], index=False)
    edges.to_csv(output_paths["graph_edges"], index=False)
    protocol_copy = {
        **protocol,
        "source_config": _display_path(repo_root, config_path),
        "source_config_sha256": _sha256_file(config_path),
    }
    _write_json(output_paths["protocol"], protocol_copy)
    _write_json(output_paths["selected_operating_points"], {
        "schema_version": 1,
        "selection_policy": "Frozen Table VI configurations; no DSE re-selection occurs in this sensitivity study.",
        "cases": [{**asdict(case), "case_id": case.case_id} for case in selected_cases],
    })
    claims = _build_claims(summary, protocol, baseline_validations, np)
    claims["archival_provenance_status"] = archival_provenance_status
    claims["archival_evidence_accepted"] = bool(
        claims["status"] == "PASS" and archival_provenance_status == "PASS"
    )
    _write_json(output_paths["claims"], claims)
    output_paths["readme"].write_text(_render_readme(claims), encoding="utf-8")

    log("hashing input and output artifacts")
    input_records = [_file_record(repo_root, path) for path in sorted(input_paths)]
    combined_input = hashlib.sha256(
        "".join(f"{item['path']} {item['sha256']}\n" for item in input_records).encode("utf-8")
    ).hexdigest()
    output_records = [_file_record(repo_root, path) for path in output_paths.values()]
    finished_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        manifest_output_root = str(output_root.relative_to(repo_root))
    except ValueError:
        manifest_output_root = str(output_root)
    manifest = {
        "schema_version": 1,
        "started_utc": started_utc,
        "finished_utc": finished_utc,
        "runtime_seconds": time.time() - run_started,
        "repository_commit": repository_commit,
        "repository_remote": repository_remote,
        "git_dirty_at_start": bool(git_status_at_start),
        "git_status_at_start": git_status_at_start.splitlines(),
        "archival_provenance_status": archival_provenance_status,
        "python": platform.python_version(),
        "runtime_versions": runtime_check,
        "seed": SEED,
        "threads": THREADS,
        "python_hash_seed_at_process_start": os.environ.get("PYTHONHASHSEED", ""),
        "config": _display_path(repo_root, config_path),
        "output_root": manifest_output_root,
        "only_case": only_case,
        "input_files": input_records,
        "combined_input_sha256": combined_input,
        "output_files": output_records,
        "cases": case_manifests,
        "baseline_validations": baseline_validations,
        "claim_status": claims["status"],
        "draft_claims_match_at_reported_precision": claims["draft_claims_match_at_reported_precision"],
    }
    manifest_path = output_root / "run_manifest.json"
    _write_json(manifest_path, manifest)
    log(f"wrote evidence to {output_root}")
    log(f"claim audit status: {claims['status']}")
    return {
        "summary": summary,
        "claims": claims,
        "manifest": manifest,
        "manifest_path": manifest_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reproduce graph/ranking sensitivity at the four frozen Table VI operating points."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (defaults to the parent of scripts/).",
    )
    parser.add_argument("--config", type=Path, help="Protocol JSON (defaults to configs/graph_sensitivity.json).")
    parser.add_argument("--output-root", type=Path, help="Evidence directory (defaults to results/notebook_run/graph_sensitivity).")
    parser.add_argument("--only-case", help="Development-only case id such as A_RH; incomplete runs cannot pass the draft claim audit.")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Permit a non-archival full run from a dirty checkout; the manifest records DEVELOPMENT_DIRTY_WORKTREE.",
    )
    parser.add_argument(
        "--allow-version-mismatch",
        action="store_true",
        help="Allow a diagnostic run outside the pinned numerical environment; baseline archive gates still apply.",
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    config_path = (args.config or repo_root / "configs" / "graph_sensitivity.json").resolve()
    output_root = (
        args.output_root or repo_root / "results" / "notebook_run" / "graph_sensitivity"
    ).resolve()
    protocol = json.loads(config_path.read_text(encoding="utf-8"))
    _configure(protocol)
    if args.only_case and args.only_case not in {case.case_id for case in CASES}:
        parser.error(f"unknown --only-case {args.only_case!r}")
    process_hash_seed = os.environ.get("PYTHONHASHSEED")
    if process_hash_seed != str(SEED) and not args.allow_version_mismatch:
        raise RuntimeError(
            f"Set PYTHONHASHSEED={SEED} before starting Python for an archival run "
            f"(observed {process_hash_seed!r}). The variable cannot change hash "
            "randomization after interpreter startup."
        )
    runtime_check = _check_runtime(protocol, allow_mismatch=args.allow_version_mismatch)
    result = run(
        repo_root,
        output_root,
        protocol,
        config_path,
        runtime_check,
        args.only_case,
        args.allow_dirty,
    )
    if not args.only_case and result["claims"]["status"] != "PASS":
        raise SystemExit("Generated evidence, but one or more draft-claim checks failed; inspect graph_sensitivity_claims.json")


if __name__ == "__main__":
    main()
