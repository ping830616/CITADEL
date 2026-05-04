from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_WORKLOADS = ("dft", "dj", "mm", "tr")
DEFAULT_ROWS = 2000


def _base_frame(
    *,
    n_rows: int,
    rng: np.random.Generator,
    setup_scale: float,
    workload_scale: float,
) -> pd.DataFrame:
    t = np.arange(n_rows, dtype=float)
    phase = 0.0125 * t * workload_scale
    phase_fast = 0.031 * t

    data = {
        "core_ipc": 1.60 * setup_scale + 0.08 * np.sin(phase) + rng.normal(0.0, 0.020, n_rows),
        "core_cpi": 0.82 / setup_scale + 0.03 * np.cos(phase) + rng.normal(0.0, 0.012, n_rows),
        "uops_retired": 4.10 * workload_scale + 0.18 * np.sin(phase_fast) + rng.normal(0.0, 0.060, n_rows),
        "core_cycles": 3.40 * setup_scale + 0.15 * np.cos(phase_fast / 2.0) + rng.normal(0.0, 0.050, n_rows),
        "l2_miss": 0.22 * workload_scale + 0.04 * np.sin(phase_fast) + rng.normal(0.0, 0.010, n_rows),
        "llc_miss": 0.18 * workload_scale + 0.03 * np.cos(phase_fast) + rng.normal(0.0, 0.008, n_rows),
        "dram_bw": 1.25 * workload_scale + 0.10 * np.sin(phase / 3.0) + rng.normal(0.0, 0.035, n_rows),
        "imc_reads": 0.94 * workload_scale + 0.07 * np.cos(phase / 4.0) + rng.normal(0.0, 0.025, n_rows),
        "pkg_power": 66.0 * setup_scale + 2.2 * np.sin(phase / 5.0) + rng.normal(0.0, 0.40, n_rows),
        "socket_temp": 47.0 + 1.2 * np.sin(phase / 6.0) + rng.normal(0.0, 0.25, n_rows),
        "dimm_temp": 39.0 + 0.9 * np.cos(phase / 7.0) + rng.normal(0.0, 0.20, n_rows),
        "vcc_voltage": 1.04 * setup_scale + 0.006 * np.sin(phase / 8.0) + rng.normal(0.0, 0.002, n_rows),
    }
    return pd.DataFrame(data)


def _apply_scenario_shift(df: pd.DataFrame, scenario: str) -> pd.DataFrame:
    out = df.copy()
    t = np.arange(len(out), dtype=float)
    bursts = ((t // 100) % 2).astype(float)

    if scenario == "DROOP":
        out["vcc_voltage"] -= 0.080 + 0.015 * bursts
        out["core_ipc"] -= 0.180 + 0.025 * bursts
        out["core_cpi"] += 0.160 + 0.020 * bursts
        out["pkg_power"] += 3.5 + 0.8 * bursts
        out["socket_temp"] += 1.3 + 0.2 * bursts
    elif scenario == "RH":
        out["dram_bw"] += 0.330 + 0.040 * bursts
        out["imc_reads"] += 0.260 + 0.025 * bursts
        out["llc_miss"] += 0.070 + 0.015 * bursts
        out["dimm_temp"] += 2.6 + 0.4 * bursts
        out["pkg_power"] += 2.0
    elif scenario == "SPECTRE":
        out["llc_miss"] += 0.130 + 0.025 * bursts
        out["l2_miss"] += 0.085 + 0.020 * bursts
        out["uops_retired"] += 0.320 + 0.050 * bursts
        out["core_ipc"] -= 0.120
        out["pkg_power"] += 2.8

    mins = {
        "core_ipc": 0.10,
        "core_cpi": 0.05,
        "uops_retired": 0.10,
        "core_cycles": 0.10,
        "l2_miss": 0.0,
        "llc_miss": 0.0,
        "dram_bw": 0.0,
        "imc_reads": 0.0,
        "pkg_power": 0.10,
        "socket_temp": 0.10,
        "dimm_temp": 0.10,
        "vcc_voltage": 0.10,
    }
    for column, lower in mins.items():
        out[column] = np.clip(out[column], lower, None)
    return out


def create_sample_dataset(
    out_root: Path,
    *,
    seed: int = 123,
    workloads: tuple[str, ...] = DEFAULT_WORKLOADS,
    n_rows: int = DEFAULT_ROWS,
) -> list[Path]:
    """Create a small deterministic telemetry dataset for smoke tests and demos."""
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    scenarios = ("benign", "DROOP", "RH", "SPECTRE")

    for setup_idx, setup_name in enumerate(("DDR4", "DDR5")):
        setup_scale = 1.0 + 0.06 * setup_idx
        for workload_idx, workload in enumerate(workloads):
            workload_scale = 1.0 + 0.04 * workload_idx
            for scenario_idx, scenario_name in enumerate(scenarios):
                file_seed = seed + 10_000 * setup_idx + 1_000 * scenario_idx + 10 * workload_idx
                rng = np.random.default_rng(file_seed)
                frame = _base_frame(
                    n_rows=n_rows,
                    rng=rng,
                    setup_scale=setup_scale,
                    workload_scale=workload_scale,
                )
                if scenario_name != "benign":
                    frame = _apply_scenario_shift(frame, scenario_name)

                out_path = out_root / f"{setup_name}_{scenario_name}_{workload}.csv"
                frame.to_csv(out_path, index=False)
                created.append(out_path)

    return sorted(created)
