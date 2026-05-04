# Detailed EXACT-TCAD Methodology

The image attached in the prompt renders as a black strip in this environment, so the labels below are the explicit methodology I used for the repo. They follow the EXACT/CINTAS flow already encoded in the codebase: raw telemetry, benign calibration, MICI/causal feature selection, CINTAS scoring, decision aggregation, hardware-cost modeling, lifecycle drift, and RTL validation.

## 0. Research Target And Claims

Goal: build a complete, hardware-aware SLM research workflow around EXACT and CINTAS.

Claims to prove:

1. EXACT/CINTAS is portable across heterogeneous CPU-DRAM platforms and broader SLM anomalies.
2. Its design choices have measurable performance, latency, bandwidth, and hardware-cost trade-offs.
3. CINTAS is feasible as a fixed-point RTL/FPGA block.
4. Lifecycle calibration can manage benign drift while preserving anomaly sensitivity and explainability.

Keep yourself on track by requiring every claim to have:

- one script
- one config file
- one manifest
- one table or figure
- one manuscript paragraph explaining the result

## 1. Raw Telemetry And Platform Setup

Purpose: make the data portable before doing any modeling.

Inputs:

- platform label, such as desktop DDR4, desktop DDR5, server CPU-DRAM, embedded or edge platform
- observability label, such as hardware-counter telemetry or host-level telemetry
- workload label, such as DFT, DJ, MM, TR, and the expanded workload set
- scenario label, such as BENIGN, DROOP, RowHammer, Spectre, firmware drift, workload drift, aging proxy
- monotonic sample index
- numeric telemetry counters, power, voltage, and temperature signals

Actions:

1. Store raw immutable CSVs under `data/telemetry/raw/<snapshot_id>/`.
2. Store cleaned aligned CSVs under `data/telemetry/processed/<snapshot_id>/`.
3. Store platform metadata under `data/platforms/<setup>.json`.
4. Record unavailable counters explicitly instead of silently filling them.
5. Hash every CSV in the run manifest.

Done when:

- all scripts use repo-relative paths
- no experiment depends on a local absolute path
- `run_manifest.json` lists input hashes and the git commit

## 2. Preprocessing And Schema Lock

Purpose: ensure each platform is comparable even when the hardware exposes different counters.

Actions:

1. Normalize column names.
2. Remove accidental index columns, duplicated columns, and nonnumeric telemetry fields.
3. Align setup, scenario, workload, and time-index metadata.
4. Drop constant features after documenting why they were removed.
5. Keep the intersection of features for strict cross-platform comparisons.
6. Keep platform-specific features only for platform-local studies.

Outputs:

- cleaned telemetry CSVs
- data-schema notes
- feature availability matrix

Done when:

- the same input snapshot produces the same cleaned files on another machine
- the feature set used in each experiment is written to the selected-feature CSV

## 3. Benign Calibration

Purpose: build an unsupervised reference of healthy behavior.

Actions:

1. Use BENIGN rows only.
2. Estimate per-feature benign mean `mu`.
3. Estimate per-feature benign standard deviation `sigma`.
4. Compute stable feature weights, either uniform or inverse-variance.
5. Freeze these calibration parameters before evaluating anomalies.

CINTAS normalization:

```text
z_f(t) = (x_f(t) - mu_f) / sigma_f
```

Outputs:

- benign calibration parameters
- selected features
- feature weights
- manifest entries for the calibration data

Done when:

- anomaly rows never influence benign calibration
- rerunning calibration with the same data and seed selects the same features

## 4. MICI/Causal Feature Screening

Purpose: reduce telemetry dimensionality while keeping explainable anomaly context.

The hardware reference code you shared uses three MICI feature groups:

- `COM`: compute-oriented counters
- `MEM`: memory/cache/DRAM-oriented counters
- `SEN`: sensor, voltage, thermal, and power signals

Actions:

1. Build benign correlation or causal-dependency graphs.
2. Rank features by their relation to the CINTAS/CIAS anomaly score.
3. Apply the MICI threshold, such as `0.85`, or a top-k feature budget.
4. Save group-specific feature lists.
5. Track rank stability across workloads and recalibration epochs.

Outputs:

- `COM_*_MICI_0.85.csv`
- `MEM_*_MICI_0.85.csv`
- `SEN_*_MICI_0.85.csv`
- causal edge lists
- feature-rank plots

Done when:

- each selected feature has a group and rank
- feature selection is reproducible from benign-only data
- the paper can explain why the final feature budget was chosen

## 5. Top-k Feature Budget

Purpose: quantify the trade-off between accuracy and deployability.

Actions:

1. Sweep `k`, for example `5, 8, 10, 15, 20, 30`.
2. Record the actual selected feature count when fewer than `k` features are available.
3. Report feature bandwidth as selected features per sample and per decision block.
4. Compare detection metrics against area and power estimates.

Outputs:

- selected-feature CSV
- ablation summary with `top_k` and `n_selected_features`
- feature-budget versus metric plots

Done when:

- the paper has a clear recommended `k`
- the recommendation is justified by accuracy, latency, and hardware cost

## 6. CINTAS Sample Scoring

Purpose: score each telemetry sample with a lightweight edge-deployable detector.

For each selected feature:

```text
E1(t) = sum_f w_f * |z_f(t)|
E2(t) = sum_f w_f * z_f(t)^2
score(t) = (1 - lambda_res) * E2(t) + lambda_res * E1(t)
```

Actions:

1. Sweep `lambda_res`, for example `0.0, 0.25, 0.5, 0.75, 1.0`.
2. Sweep weighting mode, such as uniform and inverse-variance.
3. Run floating-point reference scoring.
4. Run fixed-point reference scoring.
5. Record fixed-point mean absolute error and max absolute error.

Outputs:

- per-sample scores
- fixed-point error columns
- score-distribution plots

Done when:

- the preferred score weighting and `lambda_res` are justified by both detection quality and hardware cost

## 7. Decision-Block Aggregation

Purpose: convert sample scores into robust streaming decisions.

Actions:

1. Sweep decision-block length `N`, for example `50, 100, 150, 250, 500, 1000`.
2. Sweep aggregation operator, such as max, mean, median, or percentile.
3. Fit the threshold `tau` from benign blocks only.
4. Evaluate anomaly blocks against the frozen threshold.
5. Report detection latency in samples and seconds.

Outputs:

- block-level labels
- threshold values
- latency versus accuracy plots

Done when:

- the selected block length has a clear latency and robustness justification

## 8. Hardware-Cost Model

Purpose: connect the algorithmic design choices to implementable area and power.

The repo now uses Eduardo Ortega's operator table:

```text
add:  area raw 1165.234, power 0.178 mW, delay 62.7 ps, cycles 3
mult: area raw 4532.164, power 0.5146 mW, delay 29.09 ps, cycles 2
```

Following the reference script, raw area is divided by `1000**2`.

STD cost per feature:

```text
2 * mult + 1 * add
```

STD adder tree:

```text
(n_features - 1) * add
```

AGG cost:

```text
2 * mult
```

Actions:

1. Compute COM, MEM, and SEN STD costs from the selected feature groups.
2. Add AGG cost for the group aggregation stage.
3. Scale power linearly by GHz.
4. Report area overhead against Setup B area, `215.25 mm^2`.
5. Report idle-power overhead against Setup B idle power, `35.5 W`.
6. Track add count, multiply count, operator delays, and estimated serial cycles.

Outputs:

- hardware columns in `tcad_ablation_summary.csv`
- hardware source CSVs under `hardware/`
- RTL sweep tables once synthesis is available

Done when:

- every ablation row has associated area, power, delay, and operation-count estimates
- later RTL/FPGA results can replace or validate the estimate

## 9. Heterogeneous Platform Validation

Purpose: prove portability beyond the desktop CPU-DRAM setup.

Actions:

1. Add at least one server-class platform.
2. Add at least one embedded or edge-class platform if available.
3. Add macOS Apple Silicon as a limited-observability host platform using the ITC/DICE data.
4. Evaluate within-platform calibration.
5. Evaluate cross-platform transfer for hardware-counter platforms.
6. Report macOS separately because it uses host-level telemetry rather than low-level on-chip counters.
7. Separate failures caused by missing counters from failures caused by model drift.

Outputs:

- platform summary table
- anomaly/workload matrix
- within-platform and cross-platform metric tables
- macOS limited-observability summary table

Done when:

- the manuscript can state where EXACT transfers directly and where recalibration is required
- the manuscript does not mix host-level macOS results with on-chip hardware-cost claims

## 10. Lifecycle Drift And Recalibration

Purpose: address long-term SLM deployment.

Drift cases:

- workload mix shift
- firmware or BIOS setting change
- ambient temperature shift
- voltage policy change
- aging proxy
- unmonitored-variable disturbance

Actions:

1. Freeze an initial benign calibration.
2. Apply it to later benign and anomaly windows.
3. Measure false-positive drift.
4. Trigger benign-only recalibration.
5. Compare threshold-only recalibration against full feature-rank recalibration.
6. Track feature-rank stability and anomaly sensitivity.

Outputs:

- false-positive rate over lifecycle time
- score distributions before and after recalibration
- feature-rank stability plots

Done when:

- recalibration reduces benign false positives without suppressing true anomalies

## 11. RTL/FPGA CINTAS

Purpose: move from modeled hardware overhead to implementation evidence.

Actions:

1. Export fixed-point `mu_q`, `gamma_q`, `w_q`, `lambda_q`, and `tau_q`.
2. Generate golden vectors from Python.
3. Simulate SystemVerilog against the golden vectors.
4. Sweep Q formats and feature budgets.
5. Synthesize FPGA or ASIC targets.
6. Report LUT, FF, DSP, BRAM, area, power, timing, and energy per decision block.

Outputs:

- golden vectors
- simulation logs
- synthesis reports
- RTL resource summary

Done when:

- RTL scores match the fixed-point Python reference within the defined tolerance
- hardware tables come from synthesis, not only estimated arithmetic counts

## 12. Paper Assembly And Reproducibility Gate

Purpose: make the TCAD submission auditable.

Actions:

1. Generate every figure and table from scripts.
2. Link every figure and table to a manifest.
3. Rerun the complete pipeline on two environments.
4. Compare manifests and explain any platform-dependent differences.
5. Tag the exact code release used for submission.

Done when:

- a clean clone can regenerate the smoke experiment
- the full data snapshot and tagged code can regenerate the paper results
- the cover-letter claims are all backed by repo artifacts
