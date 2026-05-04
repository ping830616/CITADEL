# TCAD Requirements Traceability

This file maps the cover-letter gaps to the journal-extension experiments, code paths, and expected paper artifacts.

| Cover-letter gap | TCAD extension | Reproducible artifact |
| --- | --- | --- |
| Limited to two desktop CPU-DRAM platforms and three anomaly types | Add server-class, embedded/edge, and lifecycle-oriented telemetry snapshots; evaluate within-platform and cross-platform transfer | `data/telemetry/raw/<snapshot_id>/`, `data/platforms/<setup>.json`, `results/tcad_full/platform_summary.csv` |
| Fixed EXACT/CINTAS design choices were not ablated | Sweep feature budget, aggregation operator, decision-block length, score weighting, residual-score mixing, and fixed-point precision | `configs/tcad_grid_full.json`, `scripts/run_tcad_ablation.py`, `results/tcad_full/tcad_ablation_summary.csv` |
| Hardware cost relied on fixed-point modeling and estimates | Implement bit-true CINTAS, generate golden vectors, run RTL simulation, and synthesize FPGA/ASIC targets | `rtl/cintas/`, `results/rtl_sweep/rtl_resource_summary.csv`, `results/rtl_sweep/precision_cost_summary.csv` |
| Long-term SLM drift, recalibration, and scalability were incomplete | Add benign drift scenarios, recalibration epochs, feature-rank stability checks, and unmonitored-variable diagnosis cases | `results/lifecycle_drift/`, drift/recalibration figures, anomaly-context case studies |

## Paper Claim To Evidence Map

1. **Portability:** train/calibrate on each benign platform snapshot, test on matched and shifted workloads, and report MCC, balanced accuracy, AUROC, AUPRC, and false-positive rate.
2. **Design-space trade-off:** sweep CINTAS parameters and plot detection quality versus latency, telemetry bandwidth, arithmetic operations, and fixed-point error.
3. **Hardware feasibility:** compare floating-point reference, fixed-point Python, RTL simulation, and FPGA synthesis using the same golden vectors.
4. **Lifecycle readiness:** show drift-aware benign recalibration lowers false positives while preserving anomaly sensitivity and interpretable top-contributor context.

Every claim should have a script, a manifest, a table or figure, and a paragraph-ready interpretation before it enters the TCAD manuscript.
