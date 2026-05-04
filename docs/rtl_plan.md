# CINTAS RTL And FPGA Plan

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

Generate golden vectors from Python:

```bash
python scripts/run_tcad_ablation.py --data-root data/sample --out-root results/tcad_smoke --preset smoke
```

Then add a vector export step for the chosen feature set and compare RTL output bit-for-bit against `exact.cintas.FixedPointCINTAS`.

## Reporting

For every synthesis point, report:

- LUTs, FFs, DSPs, BRAMs for FPGA
- area, power, timing slack for ASIC if available
- cycles per sample
- cycles per decision block
- energy per sample
- energy per decision block
- numerical error versus floating-point reference
