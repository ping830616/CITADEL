from __future__ import annotations

import numpy as np
import pandas as pd


def compute_tableIII_setupB(
    *,
    setup_b_die_area_mm2: float = 215.25,
    idle_power_w: float = 35.5,
    workload_powers_w: dict[str, float] | None = None,
    cintas_area_mm2: float = 0.0057,
    cintas_workload_overhead_pct: float = 0.0032,
) -> pd.DataFrame:
    """Recreate the *calculation pattern* used in EXACT.ipynb for Table III.

    The draft paper ultimately reports:
      - # features
      - Area overhead (%)
      - Idle-power overhead (%)

    This helper computes EXACT's area overhead and estimates idle-power
    overhead by converting a workload-overhead percentage into an absolute
    CINTAS power, then dividing by idle power.

    Notes
    -----
    The exact numbers depend on:
      * CPU die area
      * reference workload power baseline
      * clock point

    If you need strict paper-matching values, keep these constants aligned
    with the draft.
    """
    if workload_powers_w is None:
        workload_powers_w = {
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

    median_workload_power = float(np.median(np.array(list(workload_powers_w.values()), dtype=float)))

    area_overhead_pct = 100.0 * float(cintas_area_mm2) / float(setup_b_die_area_mm2)

    cintas_power_w = (float(cintas_workload_overhead_pct) / 100.0) * median_workload_power
    idle_overhead_pct = 100.0 * float(cintas_power_w) / float(idle_power_w)

    data = [
        {
            "method": "EXACT (CINTAS)",
            "n_features": 15,
            "area_overhead_pct": area_overhead_pct,
            "idle_power_overhead_pct": idle_overhead_pct,
        },
        {
            "method": "OCTANE",
            "n_features": 227,
            "area_overhead_pct": 1.2,
            "idle_power_overhead_pct": 2.6,
        },
        {
            "method": "E-SCOUT",
            "n_features": 230,
            "area_overhead_pct": 2.2,
            "idle_power_overhead_pct": 1.0,
        },
    ]
    return pd.DataFrame(data)
