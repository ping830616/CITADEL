# TCAD Extension Methodology

This document converts the TCAD cover-letter promises into an executable research plan. For the expanded point-by-point methodology used to interpret the attached image, see `docs/image_flow_methodology.md`. It is based on the ETS EXACT pipeline and Fig. 3-style flow:

`benign calibration -> causal graph/ranking -> top-k feature budget -> CINTAS parameter search -> benign threshold -> streaming inference`.

The inline image in the prompt rendered as a black strip in the local view, so this methodology follows the extracted paper pseudocode and the cover letter contents.

## 1. Freeze The Research Questions

Define the journal paper around four claims:

1. EXACT remains accurate and portable across heterogeneous platforms and broader SLM anomaly modes.
2. The CINTAS design space has quantifiable accuracy, latency, bandwidth, and hardware-cost trade-offs.
3. Fixed-point CINTAS can be implemented in RTL/FPGA with predictable resource, latency, and energy behavior.
4. Lifecycle deployment can tolerate benign drift through calibration, periodic recalibration, and interpretable anomaly context.

Each claim must map to one or more tables/figures and one reproducible script.

## 2. Reproduce The ETS Baseline

Goal: lock the baseline before adding journal changes.

Steps:

1. Clone the original EXACT repo and fetch the telemetry snapshot.
2. Create the pinned environment from `environment.yml` or `pyproject.toml`.
3. Run `scripts/run_exact_ets2026.py` on the original telemetry.
4. Verify that the reproduced metrics match the ETS paper within the allowed tolerance.
5. Save the run manifest, input hashes, output hashes, and hardware/software metadata.

Deliverables:

- `results/ets_baseline/run_manifest.json`
- Fig. 4-style decision-block performance
- Fig. 5-style benign causal networks
- Fig. 6-style top-ranked feature bars
- Table III-style hardware overhead comparison

## 3. Define The TCAD Data Contract

Goal: make every machine and server consume the same telemetry schema.

Required columns:

- numeric telemetry features, such as core counters, memory counters, voltage, power, and temperature
- `setup`: stable platform label, for example `A`, `B`, `SERVER_XEON`, `EMBEDDED_ARM`
- `scenario`: `BENIGN`, `DROOP`, `RH`, `SPECTRE`, plus new SLM anomaly names
- `workload`: benchmark or application label
- `time_idx`: monotonic sample index within each setup/scenario/workload run

Rules:

- store raw data as immutable snapshots under `data/telemetry/raw/<snapshot_id>/`
- store cleaned, aligned data under `data/telemetry/processed/<snapshot_id>/`
- never overwrite a snapshot after it appears in a manifest
- record platform metadata in `data/platforms/<setup>.json`
- hash every CSV used in an experiment

## 4. Expand Platforms And Anomaly Classes

Goal: address the cover-letter portability gap.

Minimum platform expansion:

- existing desktop DDR4 platform
- existing desktop DDR5 platform
- one server-class CPU-DRAM platform
- one embedded or edge-class platform if available

Minimum anomaly expansion:

- voltage droop
- RowHammer or memory disturbance
- Spectre or microarchitectural security anomaly
- workload-induced benign variation
- firmware/configuration-induced drift
- aging-inspired or lifecycle fault proxy

Protocol:

1. Collect benign calibration traces for every setup and workload.
2. Collect anomaly traces with the same sampling period and feature schema where possible.
3. If a feature is unavailable on a platform, mark it as missing in platform metadata rather than silently imputing it.
4. Run per-platform EXACT calibration using benign-only data.
5. Evaluate within-platform and cross-platform transfer separately.

## 5. Run Design-Space Ablations

Goal: quantify the choices that were fixed in the ETS paper.

Ablation axes:

- feature budget `k`: examples `5, 8, 10, 15, 20, 30`
- aggregation operator `Phi`: `max`, `mean`, `median`, and optionally percentile
- decision-block length `N`: examples `50, 100, 150, 250, 500, 1000`
- score mixing `lambda_res`: examples `0.0, 0.25, 0.5, 0.75, 1.0`
- score weighting: uniform, inverse variance, causal-rank proportional
- fixed-point precision: examples `Q8`, `Q10`, `Q12`, `Q15`, `Q18`

For each grid point, report:

- MCC, balanced accuracy, F1, AUROC, AUPRC
- Brier score and ECE for calibration
- latency in samples and time
- feature bandwidth
- integer add/multiply/compare counts
- fixed-point error versus floating-point reference
- hardware area and energy estimates

Primary output:

- `results/tcad_full/tcad_ablation_summary.csv`

## 6. Add Drift-Aware Lifecycle Evaluation

Goal: show SLM readiness over time.

Drift sources:

- workload mix shift
- firmware or BIOS configuration change
- ambient temperature shift
- supply-voltage policy change
- aging proxy by gradual timing, voltage, or thermal feature shift

Lifecycle protocol:

1. Fit `mu`, `gamma`, causal graph, selected features, `lambda_res`, and threshold `tau` from initial benign calibration.
2. Apply the frozen model to later benign windows and anomaly windows.
3. Measure false-positive drift before recalibration.
4. Trigger recalibration using benign-only safe windows.
5. Re-evaluate false positives, anomaly sensitivity, and feature-rank stability.
6. Report when recalibration changes only thresholds versus when it changes feature selection.

Recommended figures:

- false-positive rate over lifecycle time
- feature-rank stability across recalibration epochs
- anomaly score distributions before and after recalibration

## 7. Implement RTL/FPGA CINTAS

Goal: replace estimated hardware cost with implementation evidence.

Implementation scope:

- fixed-point standardization using stored `mu_q` and `gamma_q`
- absolute-value term `E1`
- quadratic term `E2`
- weighted accumulation
- `lambda_res` mixer
- streaming block aggregation
- threshold comparator
- alert and top-contributor context

Verification:

1. Generate golden vectors from `exact.cintas.FixedPointCINTAS`.
2. Run RTL simulation and compare bit-exact scores.
3. Sweep Q formats and feature budgets.
4. Synthesize for FPGA or ASIC library.
5. Report LUT/FF/DSP/BRAM or area/power/timing.

Deliverables:

- `rtl/cintas/cintas_stream.sv`
- RTL testbench and golden vectors
- synthesis scripts
- `results/rtl_sweep/rtl_resource_summary.csv`

## 8. Build The TCAD Paper Package

Every paper table and figure should be generated from tracked scripts:

- Table: platform summary
- Table: anomaly and workload matrix
- Table: ablation summary
- Table: RTL/FPGA resource and latency
- Figure: extended EXACT pipeline
- Figure: performance versus `N`, `k`, and `lambda_res`
- Figure: precision versus hardware cost
- Figure: drift and recalibration behavior
- Figure: explainability context for representative anomalies

Before submission:

1. rerun all scripts from a clean clone
2. compare manifests across two machines or containers
3. archive the exact telemetry snapshot ID
4. freeze paper figures and tables
5. tag the repo release used for TCAD submission
