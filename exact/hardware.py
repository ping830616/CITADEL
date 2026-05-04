from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


SETUP_B_AREA_MM2 = 215.25
IDLE_POWER_W = 35.5
DEFAULT_HARDWARE_COSTS = Path(__file__).resolve().parents[1] / "hardware" / "cintas_operator_costs.csv"

WORKLOAD_POWER_W = {
    "DFT": 139.5,
    "DJ": 64.7,
    "DP": 99.3,
    "GS": 96.55,
    "GL": 69.1,
    "HA": 87.5,
    "JA": 89.8,
    "MM": 141.5,
    "NI": 97.5,
    "OE": 114.7,
    "PI": 96.8,
    "SH": 113.0,
    "TR": 94.9,
}

SENSOR_TOKENS = ("sensor", "sen", "temp", "therm", "pkg_power", "power", "pwr", "volt", "vcc", "energy")
MEMORY_TOKENS = ("mem", "dram", "imc", "llc", "l2", "cache", "dimm", "row", "rh")
COMPUTE_TOKENS = ("com", "core", "cpu", "uops", "ipc", "cpi", "cycles", "instr", "branch")


@dataclass(frozen=True)
class OperatorCosts:
    """Add/multiply library costs from Eduardo Ortega's reference script.

    The source script reads ``hw.csv`` and divides the area row by ``1000**2``.
    We keep the same conversion here, treating the raw area entries as square
    micrometers even if the legacy CSV label says ``area (mm^2)``.
    """

    add_area_mm2: float
    add_power_mw_at_1ghz: float
    add_delay_ps: float
    add_cycles: int
    mult_area_mm2: float
    mult_power_mw_at_1ghz: float
    mult_delay_ps: float
    mult_cycles: int
    bit_width: int = 16
    source: str = "Eduardo Ortega hardware table"

    @classmethod
    def from_csv(cls, path: Path = DEFAULT_HARDWARE_COSTS) -> "OperatorCosts":
        df = pd.read_csv(path)
        columns = set(df.columns)
        if {"operator", "area_mm2", "power_mw_at_1ghz", "delay_ps", "cycles"}.issubset(columns):
            return cls._from_normalized(df)
        if {"metrics", "add", "mult"}.issubset(columns):
            return cls._from_reference_hw_csv(df)
        raise ValueError(f"Unsupported hardware cost CSV schema: {path}")

    @classmethod
    def _from_normalized(cls, df: pd.DataFrame) -> "OperatorCosts":
        by_op = df.set_index("operator")
        add = by_op.loc["add"]
        mult = by_op.loc["mult"]
        source = str(add.get("source", "Eduardo Ortega hardware table"))
        bit_width = int(add.get("bit_width", 16))
        return cls(
            add_area_mm2=float(add["area_mm2"]),
            add_power_mw_at_1ghz=float(add["power_mw_at_1ghz"]),
            add_delay_ps=float(add["delay_ps"]),
            add_cycles=int(add["cycles"]),
            mult_area_mm2=float(mult["area_mm2"]),
            mult_power_mw_at_1ghz=float(mult["power_mw_at_1ghz"]),
            mult_delay_ps=float(mult["delay_ps"]),
            mult_cycles=int(mult["cycles"]),
            bit_width=bit_width,
            source=source,
        )

    @classmethod
    def _from_reference_hw_csv(cls, df: pd.DataFrame) -> "OperatorCosts":
        def metric(prefix: str, op: str) -> float:
            mask = df["metrics"].astype(str).str.lower().str.startswith(prefix)
            if not mask.any():
                raise ValueError(f"Missing metric row with prefix {prefix!r}")
            return float(df.loc[mask, op].iloc[0])

        area_scale = float(1000**2)
        return cls(
            add_area_mm2=metric("area", "add") / area_scale,
            add_power_mw_at_1ghz=metric("power", "add"),
            add_delay_ps=metric("delay", "add"),
            add_cycles=int(metric("cycles", "add")),
            mult_area_mm2=metric("area", "mult") / area_scale,
            mult_power_mw_at_1ghz=metric("power", "mult"),
            mult_delay_ps=metric("delay", "mult"),
            mult_cycles=int(metric("cycles", "mult")),
        )


@dataclass(frozen=True)
class HardwareCost:
    feature_count: int
    group_feature_counts: dict[str, int]
    aggregator_inputs: int
    frequency_ghz: float
    std_area_mm2: float
    agg_area_mm2: float
    total_area_mm2: float
    total_power_mw: float
    setup_b_area_overhead_pct: float
    idle_power_overhead_pct: float
    median_workload_power_overhead_pct: float
    add_count: int
    mult_count: int
    estimated_serial_cycles: int
    operator_bit_width: int
    add_delay_ps: float
    mult_delay_ps: float

    def to_summary_dict(self, prefix: str = "hw") -> dict[str, float | int]:
        return {
            f"{prefix}_frequency_ghz": self.frequency_ghz,
            f"{prefix}_operator_bit_width": self.operator_bit_width,
            f"{prefix}_std_area_mm2": self.std_area_mm2,
            f"{prefix}_agg_area_mm2": self.agg_area_mm2,
            f"{prefix}_area_mm2": self.total_area_mm2,
            f"{prefix}_power_mw": self.total_power_mw,
            f"{prefix}_setup_b_area_overhead_pct": self.setup_b_area_overhead_pct,
            f"{prefix}_idle_power_overhead_pct": self.idle_power_overhead_pct,
            f"{prefix}_median_workload_power_overhead_pct": self.median_workload_power_overhead_pct,
            f"{prefix}_add_count": self.add_count,
            f"{prefix}_mult_count": self.mult_count,
            f"{prefix}_estimated_serial_cycles": self.estimated_serial_cycles,
            f"{prefix}_add_delay_ps": self.add_delay_ps,
            f"{prefix}_mult_delay_ps": self.mult_delay_ps,
        }


def standard_euclidean_area(n_features: int, costs: OperatorCosts | None = None) -> float:
    costs = OperatorCosts.from_csv() if costs is None else costs
    n_features = int(n_features)
    if n_features <= 0:
        return 0.0
    per_feature = 2.0 * costs.mult_area_mm2 + costs.add_area_mm2
    adder_tree = max(n_features - 1, 0) * costs.add_area_mm2
    return n_features * per_feature + adder_tree


def standard_euclidean_power(
    n_features: int,
    *,
    frequency_ghz: float = 1.0,
    costs: OperatorCosts | None = None,
) -> float:
    costs = OperatorCosts.from_csv() if costs is None else costs
    n_features = int(n_features)
    if n_features <= 0:
        return 0.0
    per_feature = 2.0 * costs.mult_power_mw_at_1ghz + costs.add_power_mw_at_1ghz
    adder_tree = max(n_features - 1, 0) * costs.add_power_mw_at_1ghz
    return float(frequency_ghz) * (n_features * per_feature + adder_tree)


def aggregation_area(n_inputs: int, costs: OperatorCosts | None = None) -> float:
    costs = OperatorCosts.from_csv() if costs is None else costs
    return 2.0 * costs.mult_area_mm2 if int(n_inputs) > 0 else 0.0


def aggregation_power(
    n_inputs: int,
    *,
    frequency_ghz: float = 1.0,
    costs: OperatorCosts | None = None,
) -> float:
    costs = OperatorCosts.from_csv() if costs is None else costs
    return float(frequency_ghz) * 2.0 * costs.mult_power_mw_at_1ghz if int(n_inputs) > 0 else 0.0


def classify_feature_group(feature_name: str) -> str:
    name = str(feature_name).lower()
    if any(token in name for token in SENSOR_TOKENS):
        return "SEN"
    if any(token in name for token in MEMORY_TOKENS):
        return "MEM"
    if any(token in name for token in COMPUTE_TOKENS):
        return "COM"
    return "OTHER"


def count_feature_groups(feature_names: list[str] | tuple[str, ...]) -> dict[str, int]:
    counts = {"COM": 0, "MEM": 0, "SEN": 0, "OTHER": 0}
    for feature in feature_names:
        counts[classify_feature_group(feature)] += 1
    return {key: value for key, value in counts.items() if value > 0}


def format_feature_group_counts(group_feature_counts: dict[str, int]) -> str:
    return ";".join(f"{key}={int(group_feature_counts[key])}" for key in sorted(group_feature_counts))


def estimate_cintas_hardware_cost(
    *,
    feature_names: list[str] | tuple[str, ...] | None = None,
    n_features: int | None = None,
    group_feature_counts: dict[str, int] | None = None,
    frequency_ghz: float = 1.0,
    setup_b_area_mm2: float = SETUP_B_AREA_MM2,
    idle_power_w: float = IDLE_POWER_W,
    workload_powers_w: dict[str, float] | None = None,
    costs: OperatorCosts | None = None,
) -> HardwareCost:
    """Estimate CINTAS cost using the provided add/mult hardware table.

    This ports the reference formulas:

    - STD block per feature: ``2 * mult + 1 * add``
    - STD adder tree: ``n_features - 1`` adders
    - AGG block: ``2 * mult``
    - Power scales linearly with the supplied GHz point
    """
    costs = OperatorCosts.from_csv() if costs is None else costs
    workload_powers_w = WORKLOAD_POWER_W if workload_powers_w is None else workload_powers_w

    if group_feature_counts is None:
        if feature_names is not None:
            group_feature_counts = count_feature_groups(tuple(feature_names))
        elif n_features is not None:
            group_feature_counts = {"ALL": int(n_features)}
        else:
            raise ValueError("Provide feature_names, n_features, or group_feature_counts.")

    clean_counts = {str(k): int(v) for k, v in group_feature_counts.items() if int(v) > 0}
    feature_count = int(sum(clean_counts.values()))
    aggregator_inputs = len(clean_counts) if feature_count > 0 else 0

    std_area = sum(standard_euclidean_area(nf, costs) for nf in clean_counts.values())
    std_power = sum(
        standard_euclidean_power(nf, frequency_ghz=frequency_ghz, costs=costs)
        for nf in clean_counts.values()
    )
    agg_area = aggregation_area(aggregator_inputs, costs)
    agg_power = aggregation_power(aggregator_inputs, frequency_ghz=frequency_ghz, costs=costs)

    total_area = std_area + agg_area
    total_power_mw = std_power + agg_power
    total_power_w = total_power_mw / 1000.0
    median_workload_power = float(np.median(np.array(list(workload_powers_w.values()), dtype=float)))

    add_count = sum(nf + max(nf - 1, 0) for nf in clean_counts.values())
    mult_count = sum(2 * nf for nf in clean_counts.values()) + (2 if aggregator_inputs > 0 else 0)
    estimated_cycles = (
        sum(nf * (2 * costs.mult_cycles + costs.add_cycles) + max(nf - 1, 0) * costs.add_cycles for nf in clean_counts.values())
        + (2 * costs.mult_cycles if aggregator_inputs > 0 else 0)
    )

    return HardwareCost(
        feature_count=feature_count,
        group_feature_counts=clean_counts,
        aggregator_inputs=aggregator_inputs,
        frequency_ghz=float(frequency_ghz),
        std_area_mm2=float(std_area),
        agg_area_mm2=float(agg_area),
        total_area_mm2=float(total_area),
        total_power_mw=float(total_power_mw),
        setup_b_area_overhead_pct=100.0 * float(total_area) / float(setup_b_area_mm2),
        idle_power_overhead_pct=100.0 * float(total_power_w) / float(idle_power_w),
        median_workload_power_overhead_pct=100.0 * float(total_power_w) / median_workload_power,
        add_count=int(add_count),
        mult_count=int(mult_count),
        estimated_serial_cycles=int(estimated_cycles),
        operator_bit_width=int(costs.bit_width),
        add_delay_ps=float(costs.add_delay_ps),
        mult_delay_ps=float(costs.mult_delay_ps),
    )


def compute_power_from_features(num_features: int, ghz: float = 1.0, std: bool = True) -> float:
    if std:
        return standard_euclidean_power(num_features, frequency_ghz=ghz)
    return aggregation_power(num_features, frequency_ghz=ghz)


def compute_area_from_features(num_features: int, std: bool = True) -> float:
    if std:
        return standard_euclidean_area(num_features)
    return aggregation_area(num_features)


def compute_tableIII_setupB(
    *,
    n_features: int = 15,
    frequency_ghz: float = 1.0,
    setup_b_die_area_mm2: float = SETUP_B_AREA_MM2,
    idle_power_w: float = IDLE_POWER_W,
    workload_powers_w: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Create the Setup B overhead table from the add/mult hardware costs."""
    workload_powers_w = WORKLOAD_POWER_W if workload_powers_w is None else workload_powers_w
    cost = estimate_cintas_hardware_cost(
        n_features=int(n_features),
        frequency_ghz=float(frequency_ghz),
        setup_b_area_mm2=float(setup_b_die_area_mm2),
        idle_power_w=float(idle_power_w),
        workload_powers_w=workload_powers_w,
    )

    data = [
        {
            "method": "EXACT (CINTAS)",
            "n_features": int(n_features),
            "area_mm2": cost.total_area_mm2,
            "power_mw": cost.total_power_mw,
            "area_overhead_pct": cost.setup_b_area_overhead_pct,
            "idle_power_overhead_pct": cost.idle_power_overhead_pct,
        },
        {
            "method": "OCTANE",
            "n_features": 227,
            "area_mm2": np.nan,
            "power_mw": np.nan,
            "area_overhead_pct": 1.2,
            "idle_power_overhead_pct": 2.6,
        },
        {
            "method": "E-SCOUT",
            "n_features": 230,
            "area_mm2": np.nan,
            "power_mw": np.nan,
            "area_overhead_pct": 2.2,
            "idle_power_overhead_pct": 1.0,
        },
    ]
    return pd.DataFrame(data)
