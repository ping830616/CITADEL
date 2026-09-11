# CITADEL

**CITADEL** stands for **Conditional Interdependence in Telemetry Analytics and Drift-Aware Edge Learning**. It is the journal extension workspace for a silicon lifecycle management flow that builds on EXACT and turns the compact CINTAS detector into a hardware aware workflow with design space exploration, fixed point sensitivity, lifecycle drift checking, RTL and FPGA oriented validation, and supplemental limited observability portability analysis.

The primary end-to-end entry point is the notebook:

```text
notebooks/exact_tcad_all_experiments.ipynb
```

The focused graph/ranking sensitivity runner is also invoked from that notebook and can be run directly as `scripts/run_graph_sensitivity.py`.

This README gives the short TCAD reproduction path. Detailed runbooks are linked at the end.

## TCAD Reproduction Quick Path

### 1. Clone Or Update

```text
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git lfs pull
```

For an existing clone:

```text
cd CITADEL
git fetch origin
git pull --ff-only origin main
git lfs pull
```

If any telemetry CSV begins with `version https://git-lfs.github.com/spec/v1`, the Git LFS data were not materialized; run `git lfs pull` again.

### 2. Create The Environment

```text
conda env create -f environment.yml
conda activate citadel-slm
```

If the environment already exists:

```text
conda env update -f environment.yml --prune
conda activate citadel-slm
```

### 3. Run The Notebook

Start Jupyter from the repository root:

```text
python -m jupyter lab notebooks/exact_tcad_all_experiments.ipynb
```

Use these notebook settings to reproduce the TCAD paper results:

```python
SEED = 123
THREADS = 1
DATA_MODE = "real"
TCAD_PRESET = "full"
RUN_REPEAT_CHECK = True
```

Run the notebook from top to bottom. The `full` preset is required to reconstruct the paper-selected Table VI operating points because the shorter `balanced` development grid excludes settings such as median aggregation, `N=550/700`, `k=20`, and `lambda_res=0/1`. The full exhaustive design-space sweep can take a long time. Use `balanced` for shorter development or revalidation runs, not for reconstructing Table VI.

To regenerate only the benign workload comparison, run the **Benign workload profiles (Reviewer 1, Comment 6)** cell after the data preparation section. This cell can run alone in a fresh kernel; it does not require DSE or the anomaly datasets. It saves `workload_profiles.png` at 300 dpi, `workload_profiles.pdf`, supporting CSVs, and a manifest under `results/notebook_run/workload_profiles/`, and displays the PNG in the notebook. Fetch the benign Git LFS objects first if needed:

```bash
git lfs pull --include='data/telemetry/processed/ddr_data/*benign*.csv' --exclude=''
```

To reproduce the graph-parameter and ranking-term sensitivity evidence in Section V-D without rerunning the DSE, use the notebook cell **Graph and ranking sensitivity at frozen Table VI configurations** or run:

```bash
git lfs pull --include='data/telemetry/processed/ddr_data/*.csv,results/notebook_run/droop_adaptive_data/*.csv,results/notebook_run/tcad_ablation/tcad_ablation_summary.csv,results/notebook_run/tcad_ablation/causal/*.csv,results/notebook_run/droop_adaptive_ablation/p0_99/causal/*.csv' --exclude=''
export PYTHONHASHSEED=123
python scripts/run_graph_sensitivity.py
```

This focused run holds the four Table VI monitoring configurations fixed. It changes `tau_c` or `pi_min` one at a time, or removes one of `centrality`, `edge_stability`, `conditional_dependence`, and `alignment` while renormalizing the remaining ranking coefficients. It does not re-optimize the feature budget, decision-block length, score mixture, aggregation, feature weighting, fixed-point format, threshold quantile, or fold count. The generated claim audit derives every range endpoint from result rows and stops if the pinned runtime or archived baseline gates do not match. See [Graph and ranking sensitivity evidence](docs/graph_ranking_sensitivity.md).

To run the Intel workload evaluation, go to **Section 12: Intel Workload Change Evaluation**. Section 12.1 uses both preserved paper testbeds, ten nonoverlapping recording block replicates, randomized workload orders, two calibration cycles, and three held out evaluation cycles. It reports every block plus the mean, sample standard deviation, range, and 95 percent bootstrap interval. The preserved workload files were collected separately, so the constructed boundaries test workload distribution and order sensitivity rather than the physical transient of a continuously measured switch. A one sided exact binomial check distinguishes statistically supported reference incompatibility from ordinary variation around the 1 percent target. See [Intel benign workload order stress test](docs/intel_workload_order_stress_test.md) for the protocol and limits.

Section 12.2 provides the submission quality continuous Intel campaign. It starts a new Intel PCM process for each independent run and keeps it active across timestamped PAMPAR workload switches. This campaign must be run on Setup A and Setup B before claiming measured Intel switch transients. See [Continuous Intel workload transition campaign](docs/intel_continuous_workload_transitions.md) for the commands and acceptance checks.

Section 13 retains the Apple continuous transition campaign as an optional limited observability supplement. See [Apple benign workload transition runbook](docs/apple_workload_transitions.md) for its collection requirements.

For what the preserved scripts establish about anomaly generation, voltage control, and file labels, see [Anomaly provenance and labels](docs/anomaly_provenance.md). Historical DROOP arguments and verified event boundaries remain unavailable.

### 4. Check Required Notebook Artifacts

The notebook should produce the main TCAD artifacts under `results/notebook_run/`:

```text
tcad_ablation/tcad_ablation_summary.csv
tcad_ablation/tcad_ablation_fold_results.csv
tcad_ablation/tcad_selected_features.csv
graph_sensitivity/README.md
graph_sensitivity/graph_sensitivity_fold_results.csv
graph_sensitivity/graph_sensitivity_summary.csv
graph_sensitivity/graph_sensitivity_selected_features.csv
graph_sensitivity/graph_sensitivity_feature_ranks.csv
graph_sensitivity/graph_sensitivity_graph_edges.csv
graph_sensitivity/graph_sensitivity_claims.json
graph_sensitivity/protocol.json
graph_sensitivity/selected_operating_points.json
graph_sensitivity/run_manifest.json
lifecycle_drift/lifecycle_recalibration_summary.csv
lifecycle_drift/lifecycle_recalibration_windows.csv
fpga/cintas_setupA_q15_golden_vectors.csv
apple_limited_observability/apple_observability_best_by_scenario.csv
apple_limited_observability/apple_workload_summary.csv
intel_workload_orders/intel_workload_order_run_results.csv
intel_workload_orders/intel_workload_order_summary.csv
intel_workload_orders/fig_intel_workload_order_variation.png
apple_workload_transitions/transition_rule_summary.csv
apple_workload_transitions/transition_event_summary.csv
apple_workload_transitions/fig_apple_workload_transition_scores.png
paper_tbd_replacements.csv
```

Run manifests are written beside the results and record the git commit, configuration, package versions, input hashes, and output hashes.

### 5. Run ASU/Vivado RTL Evidence

The notebook exports the selected CINTAS settings and expects Vivado evidence here:

```text
results/notebook_run/rtl_sweep/rtl_resource_summary.csv
```

Use the ASU handoff in [`docs/asu_server_runbook.md`](docs/asu_server_runbook.md): copy the repository from the MacBook to ASU, run the four Vivado batch synthesis commands, copy `results/notebook_run/rtl_sweep/` back to the MacBook, and parse the reports on the MacBook if ASU's default Python is too old:

```text
python3 scripts/parse_vivado_rtl_sweep.py --root results/notebook_run/rtl_sweep
```

Then rerun the notebook RTL/FPGA merge section and the TCAD gallery section so the paper tables and figures include the latest Vivado evidence.

### 6. Verify Reproducibility

For submission-quality results:

- `RUN_REPEAT_CHECK` should report that the repeated TCAD summary matches the first run.
- `run_manifest.json` files should show the intended git commit and input hashes.
- `graph_sensitivity/run_manifest.json` should report that all four archived baselines reproduce and that the pinned runtime versions match.
- `graph_sensitivity/graph_sensitivity_claims.json` should report `status: PASS`; each numerical endpoint should name its source case and variant.
- The notebook should be run with `SEED = 123`, `THREADS = 1`, `DATA_MODE = "real"`, and `TCAD_PRESET = "full"`.
- Treat a run with `"git_dirty": true`, `"git_dirty_at_start": true`, or `"archival_provenance_status": "DEVELOPMENT_DIRTY_WORKTREE"` as a development run rather than the submitted archival artifact.

## Repository Map

- `notebooks/`: primary self-contained CITADEL experiment runner, including the focused sensitivity launch/display cell
- `configs/`: preset DSE grids for quick checks and full paper runs
- `docs/`: methodology, reproducibility notes, ASU server runbook, RTL plan, and traceability matrix
- `rtl/cintas/`: CINTAS SystemVerilog starter design
- `scripts/`: focused sensitivity, transition-analysis, Vivado synthesis, and report-parsing helpers
- `hardware/`: analytical operator-cost references
- `data/telemetry/processed/ddr_data/`: DDR4/DDR5 telemetry for the main CINTAS study
- `data/telemetry/raw/apple_data/`: Apple limited-observability telemetry
- `TELEMETRY_COLLECTION_SCRIPTS/`: configured DDR4 and DDR5 collection scripts and restored auxiliary collectors
- `APPLE_DATA_GENERATION/`: Apple telemetry collection provenance copied from DICE, without analysis outputs
- `results/`: generated TCAD artifacts tracked with Git LFS for reproducibility

## Detailed Guides

- [`docs/asu_server_runbook.md`](docs/asu_server_runbook.md): ASU SSH, file transfer, Vivado setup, synthesis commands, and copy-back flow
- [`docs/rtl_plan.md`](docs/rtl_plan.md): RTL/FPGA-oriented validation plan
- [`docs/reproducibility.md`](docs/reproducibility.md): cross-machine reproducibility checklist
- [`docs/telemetry_collection.md`](docs/telemetry_collection.md): telemetry sources, tool revisions, commands, timing, synchronization, privileges, and historical limits
- [`docs/intel_workload_order_stress_test.md`](docs/intel_workload_order_stress_test.md): randomized Intel workload order protocol, preprocessing, outputs, and interpretation boundary
- [`docs/intel_continuous_workload_transitions.md`](docs/intel_continuous_workload_transitions.md): independent continuous Intel PCM campaign, workload switches, analysis, and acceptance checks
- [`docs/apple_workload_transitions.md`](docs/apple_workload_transitions.md): rapid benign workload transition protocol, notebook controls, outputs, and interpretation limits
- [`docs/telemetry_dictionary.csv`](docs/telemetry_dictionary.csv): per-signal definitions, interfaces, units, sampling information, and missing-value treatment
- [`docs/tcad_end_to_end_result_methodology.md`](docs/tcad_end_to_end_result_methodology.md): complete TCAD result workflow
- [`docs/graph_ranking_sensitivity.md`](docs/graph_ranking_sensitivity.md): frozen operating points, one-at-a-time protocol, reproduced manuscript ranges, and evidence map
- [`docs/tcad_requirements_traceability.md`](docs/tcad_requirements_traceability.md): mapping from paper claims to repository artifacts
- [`docs/exact_to_citadel_extension.md`](docs/exact_to_citadel_extension.md): what transfers from EXACT and what is new in CITADEL

## Relationship To EXACT

CITADEL starts from the portable EXACT codebase and adds the TCAD journal framework: stable conditional telemetry graph learning, hardware-aware DSE, fixed-point sensitivity, hardware-cost modeling, RTL/FPGA-oriented validation, lifecycle drift checking, and reproducible result manifests. In the TCAD paper, describe the EXACT result as an **EXACT baseline reproduction inside CITADEL**; the CITADEL contributions begin after that baseline.
