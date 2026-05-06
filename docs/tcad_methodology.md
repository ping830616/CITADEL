# CITADEL Research Methodology

This document defines the research plan for **CITADEL: Causal In-Field Telemetry Analytics and Drift-Aware Edge Learning for Silicon Lifecycle Management**.

Core flow:

`telemetry snapshot -> benign calibration -> causal feature ranking -> top-k feature budget -> CINTAS scoring -> benign threshold -> streaming inference -> drift check -> hardware validation`.

## 1. Research Questions

1. Can CITADEL detect SLM anomalies with a small, explainable telemetry feature set inherited from the EXACT causal telemetry flow?
2. Which CINTAS settings give the best trade-off among detection quality, latency, telemetry bandwidth, fixed-point error, and hardware cost?
3. How stable is the benign CITADEL reference when workloads, software, firmware, temperature, voltage policy, or platform observability changes?
4. Can the fixed-point CINTAS path be verified through RTL simulation and FPGA-oriented synthesis reports?

Every question must map to a notebook section, a manifest, a table or figure, and a short paper interpretation.

## 2. Terms Used Consistently

- **SLM:** silicon lifecycle management; monitoring and decision support across design, test, deployment, and field operation.
- **Telemetry:** measured hardware or host-system signals.
- **Benign:** known healthy operation used for calibration.
- **Anomaly:** a deviation from benign behavior, such as voltage droop, RowHammer, Spectre, workload drift, firmware drift, or an aging proxy.
- **Feature budget `k`:** the number of telemetry signals selected for runtime scoring.
- **Decision block `N`:** a fixed group of consecutive samples that produces one anomaly decision.
- **CINTAS:** Causal Integrated Anomaly Scoring, the fixed-point runtime scoring block.
- **Fixed-point arithmetic:** scaled integer arithmetic used instead of floating-point arithmetic.
- **RTL:** register-transfer level hardware description used for cycle-level hardware verification.
- **FPGA:** field-programmable gate array used to prototype hardware before ASIC implementation.

## 3. Data Contract

Required columns for processed telemetry:

- `setup`: stable platform label, for example `DDR4_DESKTOP`, `DDR5_DESKTOP`, `MACOS_M2_PRO`, `SERVER_XEON`.
- `scenario`: stable condition label, for example `BENIGN`, `DROOP`, `RH`, `SPECTRE`, `WORKLOAD_DRIFT`, `FIRMWARE_DRIFT`, `AGING_PROXY`.
- `workload`: benchmark or application label.
- `time_idx`: monotonic sample index.
- numeric telemetry features.

Rules:

1. Store raw immutable data under `data/telemetry/raw/<snapshot_id>/`.
2. Store processed data under `data/telemetry/processed/<snapshot_id>/`.
3. Store platform metadata under `data/platforms/<setup>.json`.
4. Mark missing features explicitly.
5. Hash every CSV used in an experiment.

## 4. Platform Plan

Use two experiment lanes.

### Lane A: Hardware-Counter Platforms

Purpose: support CINTAS hardware claims.

Include:

- desktop DDR4 CPU--DRAM platform
- desktop DDR5 CPU--DRAM platform
- server-class CPU--DRAM platform if available
- embedded or edge-class platform if available

These platforms should use counters and sensors that map naturally to on-chip or near-sensor deployment. Report hardware cost, add/multiply counts, fixed-point error, RTL vectors, and FPGA/RTL results here.

### Lane B: Limited-Observability Host Platform

Purpose: test portability when low-level counters are unavailable.

Recommended platform:

- macOS Apple Silicon data from the ITC/DICE study

Use this lane to answer whether benign calibration, compact feature selection, block-level scoring, and drift handling survive with host-level telemetry. Do not merge this lane into the CINTAS area/power table unless a matching hardware implementation path is defined. Report it as limited-observability robustness.

## 5. Benign Calibration

1. Split each setup into benign calibration windows and evaluation windows.
2. Estimate benign mean `mu` and reciprocal standard deviation `gamma`.
3. Normalize each feature with `z_f(t) = (x_f(t) - mu_f) * gamma_f`.
4. Store `mu`, `gamma`, feature names, and hashes in the run manifest.
5. Keep anomaly rows out of calibration.

## 6. Causal Feature Ranking

1. Build a benign dependency or causal graph over telemetry signals.
2. Rank features by graph role and relationship to the CINTAS score.
3. Group features into `COM`, `MEM`, and `SEN`.
4. Select the top `k` features.
5. Save the selected features and group counts.

Feature groups:

- `COM`: compute and execution counters.
- `MEM`: memory, cache, DRAM, and address-translation counters.
- `SEN`: power, voltage, temperature, energy, and other sensor signals.

## 7. CINTAS Scoring

For each selected feature:

```text
E1(t) = sum_f w_f * |z_f(t)|
E2(t) = sum_f w_f * z_f(t)^2
score(t) = (1 - lambda_res) * E2(t) + lambda_res * E1(t)
```

Steps:

1. Sweep `lambda_res`.
2. Sweep feature weighting, such as uniform and inverse variance.
3. Sweep fixed-point Q format.
4. Compare floating-point and fixed-point scores.
5. Record fixed-point mean absolute error and maximum absolute error.

## 8. Decision-Block Inference

1. Sweep decision-block length `N`.
2. Sweep aggregation operator, such as max, mean, median, or percentile.
3. Fit threshold `tau` from benign blocks only.
4. Emit one decision per block.
5. Report latency in samples and seconds.

Metrics:

- MCC
- balanced accuracy
- F1
- AUROC
- AUPRC
- Brier score
- expected calibration error
- false-positive rate

## 9. Design-Space Ablation

Sweep:

- feature budget `k`: `5, 8, 10, 15, 20, 30`
- decision-block length `N`: `50, 100, 150, 250, 500, 1000`
- `lambda_res`: `0.0, 0.25, 0.5, 0.75, 1.0`
- aggregation operator
- feature weighting
- fixed-point precision: `Q8, Q10, Q12, Q15, Q18`

Report:

- detection quality
- latency
- telemetry bandwidth
- fixed-point error
- add/multiply/compare counts
- area, power, delay, and cycles
- Pareto-preferred configurations

Primary output:

- `results/notebook_run/tcad_ablation/tcad_ablation_summary.csv`

## 10. Lifecycle Drift And Recalibration

Drift sources:

- workload mix shift
- firmware or BIOS setting change
- ambient temperature shift
- voltage-policy shift
- aging proxy
- missing or unmonitored variables

Steps:

1. Freeze the initial benign reference.
2. Apply the frozen detector to later benign windows and anomaly windows.
3. Track false-positive rate, anomaly true-positive rate, and score-distribution movement.
4. Recalibrate using safe benign windows.
5. Compare threshold-only recalibration with full benign-only feature-rank recalibration.
6. Report feature-rank stability.

Notebook outputs:

- `results/notebook_run/lifecycle_drift/lifecycle_recalibration_summary.csv`
- `results/notebook_run/lifecycle_drift/lifecycle_recalibration_by_scenario.csv`
- `results/notebook_run/lifecycle_drift/lifecycle_feature_rank_stability.csv`
- `results/notebook_run/lifecycle_drift/run_manifest.json`
- `results/notebook_run/paper_tbd_replacements.csv`

## 11. RTL And FPGA Path

1. Export fixed-point constants and golden vectors from Python.
2. Simulate the RTL CINTAS module against the golden vectors.
3. Sweep Q format and feature budget.
4. Run FPGA or ASIC-oriented synthesis.
5. Save LUT/FF/DSP/BRAM, timing, area, power, latency, and energy results.

## 12. Paper Package

Tables:

- platform and telemetry summary
- anomaly and workload matrix
- design-space ablation summary
- limited-observability macOS results
- hardware-cost and RTL/FPGA resource summary
- lifecycle recalibration summary

Figures:

- full EXACT workflow
- feature-ranking and COM/MEM/SEN selection
- performance versus `N`, `k`, and `lambda_res`
- fixed-point precision versus hardware cost
- lifecycle drift and recalibration
- CINTAS hardware datapath

Final gate:

1. Rerun the notebook from a clean clone.
2. Compare manifests across two environments.
3. Archive data snapshot IDs.
4. Freeze paper figures and tables.
5. Tag the code used for submission.
