from __future__ import annotations

import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_operator_costs_match_reference_hw_csv() -> None:
    from exact.hardware import OperatorCosts

    costs = OperatorCosts.from_csv(REPO_ROOT / "hardware" / "hw.csv")

    assert math.isclose(costs.add_area_mm2, 1165.234 / 1_000_000.0)
    assert math.isclose(costs.mult_area_mm2, 4532.164 / 1_000_000.0)
    assert math.isclose(costs.add_power_mw_at_1ghz, 0.178)
    assert math.isclose(costs.mult_power_mw_at_1ghz, 0.5146)
    assert costs.add_cycles == 3
    assert costs.mult_cycles == 2


def test_standard_and_aggregate_costs_follow_eduardo_formula() -> None:
    from exact.hardware import OperatorCosts, aggregation_area, estimate_cintas_hardware_cost, standard_euclidean_area

    costs = OperatorCosts.from_csv(REPO_ROOT / "hardware" / "cintas_operator_costs.csv")
    expected_std3 = 3 * (2 * costs.mult_area_mm2 + costs.add_area_mm2) + 2 * costs.add_area_mm2
    expected_agg = 2 * costs.mult_area_mm2

    assert math.isclose(standard_euclidean_area(3, costs), expected_std3)
    assert math.isclose(aggregation_area(3, costs), expected_agg)

    cost = estimate_cintas_hardware_cost(group_feature_counts={"COM": 1, "MEM": 1, "SEN": 1}, costs=costs)
    expected_total = 3 * standard_euclidean_area(1, costs) + expected_agg
    assert math.isclose(cost.total_area_mm2, expected_total)
    assert cost.add_count == 3
    assert cost.mult_count == 8


def test_feature_groups_drive_hardware_cost() -> None:
    from exact.hardware import count_feature_groups, estimate_cintas_hardware_cost

    features = ["core_ipc", "dram_bw", "pkg_power", "vcc_voltage"]
    assert count_feature_groups(features) == {"COM": 1, "MEM": 1, "SEN": 2}

    cost = estimate_cintas_hardware_cost(feature_names=features, frequency_ghz=2.0)
    assert cost.feature_count == 4
    assert cost.aggregator_inputs == 3
    assert cost.total_power_mw > 0.0
    assert cost.setup_b_area_overhead_pct > 0.0
