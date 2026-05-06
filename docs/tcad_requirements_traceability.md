# CITADEL Requirements Traceability

This file maps the CITADEL paper goals to experiments, code paths, and expected artifacts.

| Research need | Planned experiment | Reproducible artifact |
| --- | --- | --- |
| Portability across platforms and observability levels | Evaluate desktop DDR4, desktop DDR5, additional server/embedded platforms when available, and macOS as a limited-observability host case | `data/telemetry/raw/<snapshot_id>/`, `data/platforms/<setup>.json`, `results/tcad_full/platform_summary.csv`, `results/macos_limited_observability/` |
| Quantified CINTAS design choices | Sweep feature budget, aggregation operator, decision-block length, score weighting, residual-score mixing, fixed-point precision, and false-positive rate | `notebooks/exact_tcad_all_experiments.ipynb`, `configs/tcad_grid_full.json`, `results/notebook_run/tcad_ablation/tcad_ablation_summary.csv` |
| Hardware-aware deployment | Start from Eduardo Ortega's add/mult operator table, attach area/power/delay estimates to every hardware-counter ablation row, then validate with bit-true CINTAS RTL simulation and FPGA/ASIC synthesis | `hardware/hw.csv`, `hardware/cintas_operator_costs.csv`, `rtl/cintas/`, `results/rtl_sweep/rtl_resource_summary.csv` |
| Lifecycle readiness | Freeze the initial benign detector, evaluate later benign windows as drift proxies, compare threshold-only and full benign-only feature-rank recalibration, and report feature-rank stability | `results/notebook_run/lifecycle_drift/`, `results/notebook_run/paper_tbd_replacements.csv`, drift/recalibration figure |
| Limited-observability robustness | Use the macOS ITC/DICE dataset to test whether benign calibration and compact block scoring work with host-level telemetry | `results/macos_limited_observability/`, macOS feature availability table, macOS detection summary |

## Paper Claim To Evidence Map

1. **Compact detection:** show that selected features can detect anomalies while reducing telemetry bandwidth.
2. **CITADEL design-space trade-off:** plot detection quality versus latency, telemetry bandwidth, arithmetic operations, fixed-point error, area, and power.
3. **Hardware feasibility:** compare floating-point reference, fixed-point Python, RTL simulation, and FPGA synthesis using the same golden vectors.
4. **Lifecycle readiness:** show drift-aware benign recalibration lowers false positives while preserving anomaly sensitivity and interpretable top-contributor context.
5. **Platform realism:** report hardware-counter platforms and host-level macOS telemetry separately so deployment assumptions remain clear.

Every claim should have a notebook cell, a manifest, a table or figure, and a paragraph-ready interpretation before it enters the paper.
