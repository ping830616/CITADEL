# CITADEL

**CITADEL** is the journal-extension workspace for **Causal In-Field Telemetry Analytics and Drift-Aware Edge Learning for Silicon Lifecycle Management**.

The repository builds on **EXACT**: Edge-eXplainable Autonomous Causal Telemetry. EXACT established the edge-only CINTAS detector on two CPU-DRAM platforms. CITADEL turns that detector into a hardware-aware and drift-aware SLM methodology:

- design-space ablations for feature budget, aggregation, decision-block length, score weighting, and fixed-point precision
- broader heterogeneous-platform and SLM-anomaly validation
- FPGA/RTL implementation and cost evaluation for CINTAS
- drift-aware lifecycle calibration, recalibration, and explainable anomaly context

The experiment code is intentionally contained in one notebook: `notebooks/exact_tcad_all_experiments.ipynb`. Python versions are pinned, runtime seeds and thread counts are fixed, generated artifacts receive SHA-256 manifests, and the smoke-test dataset is deterministic.

## Notebook-Only Workflow

The single supported experiment entry point is `notebooks/exact_tcad_all_experiments.ipynb`. Open that notebook in Jupyter, run the cells from top to bottom, and use its configuration cell to choose smoke or full CITADEL runs. The notebook contains the former helper code inline, so there is no separate Python package or script to run. The same notebook now produces the TCAD ablation metrics, false-positive rate, lifecycle drift/recalibration tables, and paper-ready TBD replacement CSV.

The notebook automatically locates the tracked telemetry folders:

- `data/telemetry/processed/ddr_data/`
- `data/telemetry/raw/apple_data/`

If the notebook reports that a CSV is a Git LFS pointer, fetch the Git LFS objects through your Git client before running the experiments.

## Repository Map

- `notebooks/`: the single self-contained experiment runner for EXACT reproduction, CITADEL ablation, false-positive-rate reporting, lifecycle recalibration, hardware summaries, and FPGA/RTL integration hooks
- `configs/`: smoke and full ablation grids
- `docs/`: start-to-finish methodology, ASU server runbook, traceability matrix, data schema, reproducibility checklist, and RTL plan
- `docs/figures/`: CITADEL manuscript PNG assets for Overleaf figures and draft table images
- `rtl/cintas/`: synthesizable CINTAS SystemVerilog starter design and testbench notes
- `environment.yml`: Conda environment for reproducible laptop/server runs
- `data/external_sources.json`: versioned registry for external DDR and Apple telemetry sources
- `data/telemetry/processed/ddr_data/`: DDR4/DDR5 CSV target for CITADEL CINTAS experiments
- `data/telemetry/raw/apple_data/`: Apple M2 Pro tier-0/1/2 target for observability studies
- `data/sample/`: deterministic generated data for smoke tests, not tracked
- `results/`: generated tables, plots, and run manifests, not tracked

## Reproducibility Contract

Every experiment should be run from the notebook with repo-relative paths. Each notebook run writes `run_manifest.json` files with configuration, package versions, input hashes, and output hashes. Matching manifests across machines mean the same numerical inputs and outputs were used.

## Run Reproducibly On Any Machine

Use the same workflow on a laptop, workstation, or Linux server. ASU-specific SSH, tmux, shell, and file-transfer commands are kept in [`docs/asu_server_runbook.md`](docs/asu_server_runbook.md).

### 1. Clone Or Update The Repository

For a first clone:

```text
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
```

For an existing clone:

```text
cd CITADEL
git fetch origin
git pull --ff-only origin main
git lfs pull
git log --oneline -1
```

If GitHub asks for credentials, use your GitHub username and a GitHub Personal Access Token. Do not use an ASU password for GitHub authentication.

### 2. Materialize Git LFS Telemetry

The telemetry CSVs are stored with Git LFS. Fetch them before running the notebook:

```text
git lfs install
git lfs pull
find data/telemetry -name "*.csv" | head -n 1 | xargs head -5
```

If the first line says `version https://git-lfs.github.com/spec/v1`, the file is still a Git LFS pointer. Run `git lfs pull` again and confirm that your GitHub token can read this repository.

### 3. Create Or Update The Environment

Create the Conda environment the first time:

```text
conda env create -f environment.yml
```

If the environment already exists, update it:

```text
conda env update -f environment.yml --prune
```

Activate it:

```text
conda activate citadel-slm
```

If `conda activate` is not initialized, source your Conda setup script first. A common path is:

```text
source ~/miniconda3/etc/profile.d/conda.sh
conda activate citadel-slm
```

### 4. Fix Runtime Determinism

The notebook also sets reproducibility controls, but setting them before launch makes runs easier to compare across machines:

```text
export PYTHONHASHSEED=123
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export MPLBACKEND=Agg
```

### 5. Start Jupyter

From the repository root:

```text
python -m jupyter lab notebooks/exact_tcad_all_experiments.ipynb
```

On a remote server, start Jupyter with `--no-browser --ip=127.0.0.1 --port=<port>` and use SSH port forwarding from your laptop. The ASU-specific commands are in [`docs/asu_server_runbook.md`](docs/asu_server_runbook.md).

### 6. Run The Notebook

Open:

```text
notebooks/exact_tcad_all_experiments.ipynb
```

For a quick reproducibility check, use these settings in the notebook configuration cell:

```python
SEED = 123
THREADS = 1
DATA_MODE = "real"
TCAD_PRESET = "smoke"
RUN_REPEAT_CHECK = True
```

For the final TCAD journal-scale run, change only:

```python
TCAD_PRESET = "full"
```

The full configuration evaluates block lengths:

```text
50, 100, 150, 200, ..., 900, 950, 1000
```

Run the notebook from top to bottom after every GitHub update. If you pulled notebook changes while Jupyter was already open, restart the kernel before rerunning.

### 7. Check The Result Artifacts

After the notebook finishes, check:

```text
results/notebook_run/ets_baseline/run_manifest.json
results/notebook_run/tcad_ablation/run_manifest.json
results/notebook_run/tcad_ablation/tcad_config_resolved.json
results/notebook_run/tcad_ablation/tcad_ablation_summary.csv
results/notebook_run/tcad_ablation/tcad_ablation_fold_results.csv
results/notebook_run/tcad_ablation/tcad_selected_features.csv
results/notebook_run/tcad_ablation_repeat/tcad_ablation_summary.csv
results/notebook_run/lifecycle_drift/run_manifest.json
results/notebook_run/lifecycle_drift/lifecycle_recalibration_summary.csv
results/notebook_run/lifecycle_drift/lifecycle_recalibration_by_scenario.csv
results/notebook_run/droop_adaptive_ablation/droop_adaptive_best_by_setup.csv
results/notebook_run/droop_adaptive_ablation/droop_adaptive_vs_main_tcad.csv
results/notebook_run/paper_tbd_replacements.csv
```

The repeat check should report:

```text
Repeated TCAD summary equals first run: True
```

## What To Compare Across Machines

After each run, check these outputs:

- `results/notebook_run/ets_baseline/run_manifest.json`
- `results/notebook_run/tcad_ablation/run_manifest.json`
- `results/notebook_run/tcad_ablation/tcad_config_resolved.json`
- `results/notebook_run/tcad_ablation/tcad_ablation_summary.csv`
- `results/notebook_run/lifecycle_drift/run_manifest.json`
- `results/notebook_run/lifecycle_drift/lifecycle_recalibration_summary.csv`
- `results/notebook_run/lifecycle_drift/lifecycle_recalibration_by_scenario.csv`
- `results/notebook_run/paper_tbd_replacements.csv`

For strict reproducibility, the resolved config, input hashes, selected-feature files, summary CSV values, lifecycle CSV values, and paper TBD replacement values should match between the laptop and the ASU server. If they do not match, first check Python version, package versions, Git commit, Git LFS data materialization, `SEED`, `THREADS`, and `TCAD_PRESET`.

The manifest records the git commit, dirty-worktree state, Python version, direct package versions, hashes for `requirements.txt`, `environment.yml`, input CSV hashes, and output artifact hashes. Treat a run with `"git_dirty": true` as a development run, not a paper-submission run.

## CITADEL Methodology

The project plan is in `docs/tcad_methodology.md`, `docs/research_execution_plan.md`, and `docs/image_flow_methodology.md`. The cover-letter-to-artifact map is in `docs/tcad_requirements_traceability.md`. Together they turn the cover-letter promises into a complete execution path:

1. reproduce the EXACT baseline
2. freeze telemetry schema and platform metadata
3. run systematic CINTAS/CITADEL ablations
4. collect and validate additional platforms and anomaly classes
5. quantify lifecycle drift and benign recalibration
6. implement and verify fixed-point RTL/FPGA CINTAS
7. use `results/notebook_run/paper_tbd_replacements.csv` to replace manuscript TBD values
8. regenerate all CITADEL/TCAD tables and figures from the notebook and its manifests

## Data

CITADEL tracks real telemetry directly in this repo using Git LFS. The notebook reads DDR4/DDR5 telemetry from `data/telemetry/processed/ddr_data/` and Apple M2 Pro telemetry from `data/telemetry/raw/apple_data/`. Each run manifest records the exact input hashes used for the results.

The deterministic sample dataset is only for testing the pipeline shape. It is not evidence for the paper.

## Relationship to EXACT

This repo starts from the portable EXACT codebase at `https://github.com/ping830616/EXACT` and adds the CITADEL journal framework: design-space exploration, fixed-point precision analysis, hardware-cost modeling, RTL/FPGA-oriented validation, benign-drift checks, and reproducible result manifests. The default upstream EXACT provenance is pinned to commit `b6b8b17ef825d9f4fad754f88c1de583b09805b9`, and every new run manifest records that lineage under `method_provenance`.

The ETS baseline manifest is generated by the CITADEL notebook, not by executing a live checkout of the EXACT repository. In the TCAD paper, describe it as an **EXACT baseline reproduction inside CITADEL**. The CITADEL contributions begin after that baseline: FPR reporting, TCAD design-space exploration, lifecycle recalibration, hardware-cost modeling, fixed-point golden vectors, and RTL/FPGA integration hooks.

For a paper-ready map of what transfers from EXACT and what is new in CITADEL, see `docs/exact_to_citadel_extension.md`.
