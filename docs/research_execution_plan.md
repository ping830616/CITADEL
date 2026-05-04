# Research Execution Plan

The attached prompt image rendered as an unreadable black strip locally, so this plan follows the visible EXACT flow used in the existing scaffold: benign calibration, causal graph/ranking, top-k feature selection, CINTAS parameter search, benign thresholding, and streaming inference. The plan is written as a standalone research workflow.

## Stage 0: Repository And Reproducibility Baseline

1. Start every experiment from a clean commit.
2. Create the pinned Python environment with `make install` or the Docker image.
3. Run `make reproduce-smoke` and verify that tests pass.
4. Record the git commit, package versions, seed, thread counts, input hashes, and output hashes in `run_manifest.json`.

Exit gate: a fresh clone on another machine produces the same smoke-test manifest structure and the same smoke-test metrics.

## Stage 1: ETS Baseline Reproduction

1. Import the original EXACT telemetry snapshot from `https://github.com/ping830616/EXACT`.
2. Preserve the raw CSV files under `data/telemetry/raw/<snapshot_id>/`.
3. Convert to the TCAD schema under `data/telemetry/processed/<snapshot_id>/`.
4. Run the ETS reproduction script without changing TCAD parameters.
5. Compare reproduced tables and figures against the conference paper.

Exit gate: ETS detection and explainability results match the paper within a stated tolerance.

## Stage 2: Data Contract

1. Standardize required columns: `setup`, `scenario`, `workload`, `time_idx`, and numeric telemetry features.
2. Create one platform metadata file per setup under `data/platforms/`.
3. Mark unavailable counters explicitly in metadata.
4. Hash every raw and processed CSV.
5. Freeze the snapshot ID before using it in paper results.

Exit gate: all scripts can run with repo-relative paths and no machine-specific absolute paths.

## Stage 3: Benign Calibration

1. Split benign traces by platform and workload.
2. Estimate feature means, variances, and normalization constants from benign-only data.
3. Build the benign causal/correlation graph.
4. Rank telemetry features by causal relevance and stability.
5. Store calibration parameters and selected features with the run manifest.

Exit gate: calibration can be regenerated from raw data and produces identical selected features for a fixed seed and config.

## Stage 4: CINTAS Streaming Detector

1. Compute normalized feature residuals for each incoming telemetry sample.
2. Apply top-k feature selection from the benign calibration phase.
3. Compute `E1` absolute-deviation terms and `E2` quadratic residual terms.
4. Mix score components with the configured score weights and `lambda_res`.
5. Aggregate scores over the decision block.
6. Compare the block score against the benign threshold.
7. Emit anomaly label, score, latency, and top-contributor context.

Exit gate: floating-point and fixed-point reference implementations produce bounded numerical differences.

## Stage 5: Design-Space Ablation

1. Sweep feature budget `k`.
2. Sweep aggregation operator.
3. Sweep decision-block length.
4. Sweep residual-score mixing and score weighting.
5. Sweep fixed-point precision.
6. For every grid point, compute detection metrics, latency, feature bandwidth, arithmetic operation count, and fixed-point error.
7. Rank Pareto-optimal configurations for TCAD figures.

Exit gate: `results/tcad_full/tcad_ablation_summary.csv` supports paper-ready trade-off plots.

## Stage 6: Heterogeneous Platform Validation

1. Add server-class and embedded or edge-class platforms when available.
2. Add macOS Apple Silicon as a limited-observability host platform using the ITC/DICE dataset.
3. Keep sampling period, workload labels, and anomaly labels consistent when possible.
4. Evaluate within-platform calibration.
5. Evaluate cross-platform transfer for hardware-counter platforms.
6. Report macOS separately as host-level portability, not as an on-chip hardware-cost claim.
7. Separate portability failures caused by missing counters, workload shifts, and true model degradation.

Exit gate: the manuscript can state where EXACT transfers directly and where recalibration is required.

## Stage 7: Lifecycle Drift And Digital-Twin Calibration

1. Define lifecycle epochs for workload, firmware, temperature, voltage-policy, and aging-proxy drift.
2. Apply the frozen benign calibration to later benign windows.
3. Track false positives and score-distribution movement.
4. Trigger benign-only recalibration at controlled epochs.
5. Compare threshold-only recalibration against full feature-rank recalibration.
6. Report anomaly sensitivity before and after recalibration.

Exit gate: drift figures show whether recalibration improves false positives without hiding real anomalies.

## Stage 8: RTL/FPGA CINTAS

1. Export fixed-point calibration constants and golden vectors.
2. Simulate the SystemVerilog CINTAS stream module against golden vectors.
3. Sweep Q format and feature budget.
4. Synthesize each configuration.
5. Report LUT/FF/DSP/BRAM or area/power/timing, implementation latency, and energy per decision block.

Exit gate: hardware tables are measured from RTL/FPGA synthesis rather than only estimated from operation counts.

## Stage 9: Statistical Validation

1. Use repeated splits or blocked cross-validation by workload/session.
2. Report confidence intervals for key metrics.
3. Use paired comparisons when comparing CINTAS settings on identical traces.
4. Identify unstable configurations and remove them from preferred deployment recommendations.

Exit gate: claims are backed by uncertainty estimates, not only point metrics.

## Stage 10: Manuscript Assembly

1. Generate every table and figure from scripts.
2. Link every table and figure to a run manifest.
3. Archive raw data snapshot IDs and processed-data hashes.
4. Tag the exact code release used for submission.
5. Rerun the full pipeline on at least two environments: local workstation and clean container or server.

Exit gate: a reviewer can reproduce the submitted results from the tagged repository plus the archived telemetry snapshot.
