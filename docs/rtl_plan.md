# CITADEL CINTAS RTL And FPGA Plan

## Datapath

CINTAS evaluates selected telemetry features in streaming order:

1. subtract stored benign mean `mu_q`
2. multiply by stored reciprocal standard deviation `gamma_q`
3. compute `abs(z_q)` for the linear term
4. compute `z_q * z_q` for the quadratic term
5. multiply by feature weight `w_q`
6. accumulate `E1` and `E2`
7. mix with `lambda_q`
8. update the block aggregator
9. compare against threshold `tau_q`

## Sweep Parameters

- feature budgets: `5, 8, 10, 15, 20, 30`
- Q formats: `Q8, Q10, Q12, Q15, Q18`
- aggregation: `max`, `mean`, `median` if median is implemented through a small buffer
- clock constraints: FPGA target clock and ASIC target clock

## Verification

Generate golden vectors from the RTL/FPGA section of `notebooks/exact_tcad_all_experiments.ipynb`. Then compare RTL output bit-for-bit against `exact.cintas.FixedPointCINTAS`.

## Reporting

For every synthesis point, report:

- LUTs, FFs, DSPs, BRAMs for FPGA
- area, power, timing slack for ASIC if available
- cycles per sample
- cycles per decision block
- energy per sample
- energy per decision block
- numerical error versus floating-point reference

## Current Operator-Cost Source

Until RTL/FPGA synthesis is complete, the CITADEL ablation table uses Eduardo Ortega's add/multiply cost table in `hardware/hw.csv` and the normalized repo copy in `hardware/cintas_operator_costs.csv`.

The current estimate follows the reference script:

- add raw area `1165.234`, power `0.178 mW`, delay `62.7 ps`, cycles `3`
- multiply raw area `4532.164`, power `0.5146 mW`, delay `29.09 ps`, cycles `2`
- raw area is divided by `1000**2` before reporting `mm^2`
- STD block cost per feature is `2 * mult + add`
- STD adder-tree cost is `(n_features - 1) * add`
- AGG block cost is `2 * mult`
- power scales linearly with the GHz setting

The model reports Setup B area overhead against `215.25 mm^2` and idle-power overhead against `35.5 W`. These columns are estimates and should be replaced or validated by RTL synthesis reports before final TCAD submission.
