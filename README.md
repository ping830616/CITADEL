# CITADEL

**CITADEL** is the journal-extension workspace for **Causal In-Field Telemetry Analytics and Drift-Aware Edge Learning for Silicon Lifecycle Management**.

The repository builds on **EXACT**: Edge-eXplainable Autonomous Causal Telemetry. EXACT established the edge-only CINTAS detector on two CPU-DRAM platforms. CITADEL turns that detector into a hardware-aware and drift-aware SLM methodology:

- design-space ablations for feature budget, aggregation, decision-block length, score weighting, and fixed-point precision
- broader heterogeneous-platform and SLM-anomaly validation
- FPGA/RTL implementation and cost evaluation for CINTAS
- drift-aware lifecycle calibration, recalibration, and explainable anomaly context

The code is intentionally portable: Python versions are pinned, runtime seeds and thread counts are fixed, generated artifacts receive SHA-256 manifests, and the smoke-test dataset is deterministic.

## Notebook-Only Workflow

The single supported experiment entry point is `notebooks/exact_tcad_all_experiments.ipynb`. Open that notebook in Jupyter, run the cells from top to bottom, and use its configuration cell to choose smoke or full CITADEL runs.

The notebook automatically locates the tracked telemetry folders:

- `data/telemetry/processed/ddr_data/`
- `data/telemetry/raw/apple_data/`

If the notebook reports that a CSV is a Git LFS pointer, fetch the Git LFS objects through your Git client before running the experiments.

## Repository Map

- `exact/`: reusable core library inherited from EXACT, including I/O, preprocessing, CINTAS scoring, metrics, plotting, and hardware-cost helpers; it is not an experiment entry point
- `notebooks/`: the single experiment runner for EXACT reproduction, CITADEL ablation, hardware summaries, and FPGA/RTL integration hooks
- `configs/`: smoke and full ablation grids
- `docs/`: start-to-finish methodology, traceability matrix, data schema, reproducibility checklist, and RTL plan
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

## Run For Reproducibility

Use Python 3.11 or 3.12 when possible because GitHub Actions tests both versions. Python 3.13 also works locally, but matching CI is cleaner for paper artifacts. For final paper numbers, use Python 3.11 with `environment.yml` on every machine.

This repo supports two setup paths:

- `venv` plus `pip install -e ".[dev,notebook]"`
- Conda using `environment.yml`

For strict paper reproducibility, use the same path on both machines. Do not mix the `venv` path on one machine with the Conda path on another when generating submission tables. The Conda path is recommended for the ASU Linux server when Conda or Mamba is available.

The notebook sets deterministic seeds and thread counts again inside Python. For startup-level reproducibility, launch Jupyter from a shell where these variables are already fixed:

```text
export PYTHONHASHSEED=123
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export MPLBACKEND=Agg
```

### Laptop Run

On macOS or Linux, clone the repo, materialize the Git LFS data, create an isolated environment, install the package, and launch the notebook.

Option A uses `venv`:

```text
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git lfs install
git lfs pull
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev,notebook]"
python -m pytest
export PYTHONHASHSEED=123
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export MPLBACKEND=Agg
python -m jupyter lab notebooks/exact_tcad_all_experiments.ipynb
```

Option B uses `environment.yml`:

```text
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git lfs install
git lfs pull
conda env create -f environment.yml
conda activate citadel-slm
python -m pip install -e . --no-deps
python -m pytest
export PYTHONHASHSEED=123
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export MPLBACKEND=Agg
python -m jupyter lab notebooks/exact_tcad_all_experiments.ipynb
```

In the notebook configuration cell, keep these settings for a reproducible laptop run:

```python
SEED = 123
THREADS = 1
DATA_MODE = "real"
TCAD_PRESET = "smoke"
RUN_REPEAT_CHECK = True
```

Then run the notebook from top to bottom. The smoke preset is the recommended laptop check. It validates the full CITADEL flow without running the largest design-space sweep.

### ASU Linux Server Run

On an ASU Linux server, use the same repo and notebook. The main differences are environment setup, remote Jupyter access, and optional job allocation if the server is managed by a scheduler. If Conda or Mamba is available, prefer `environment.yml` so the server receives the same pinned package versions as the laptop.

Connect to the ASU server from your laptop with your ASURITE domain login. In `zsh`, either quote the username or escape the backslash:

```text
ssh 'asurite\hsiaopin@149.169.30.50'
```

or:

```text
ssh asurite\\hsiaopin@149.169.30.50
```

After logging in, start a persistent terminal session so long CITADEL runs survive laptop sleep or network drops:

```text
tmux new -s citadel
```

Conda server setup:

```text
cd ~
if [ -d CITADEL ]; then
  mv CITADEL CITADEL_previous_clone
fi
git clone git@github.com:ping830616/CITADEL.git
cd CITADEL
git lfs install
git lfs pull
conda env create -f environment.yml
conda activate citadel-slm
python -m pip install -e . --no-deps
python -m pytest
```

If you manually run `mv ~/CITADEL ...` and it says `No such file or directory`, that is fine. It means there was no old failed clone. Continue with `git clone`.

If `git lfs` is missing on the ASU server, install it through Conda first:

```text
conda install -c conda-forge git-lfs -y
which git-lfs
git-lfs --version
cd ~/CITADEL
git lfs install
git lfs pull
```

Check that Git LFS materialized real CSV files rather than pointer files:

```text
find data/telemetry -name "*.csv" | head -n 1 | xargs head -5
```

If the output begins with `version https://git-lfs.github.com/spec/v1`, run `git lfs pull` again and verify that your GitHub SSH key has access to the repository.

Before starting Jupyter, set the deterministic runtime variables:

```text
export PYTHONHASHSEED=123
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export MPLBACKEND=Agg
```

If Conda is not available, use `venv`:

```text
git clone git@github.com:ping830616/CITADEL.git
cd CITADEL
git lfs install
git lfs pull
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev,notebook]"
python -m pytest
```

If the server uses environment modules, load Python before creating the virtual environment:

```text
module avail python
module load python/3.11
python3.11 -m venv .venv
```

If the server requires an interactive compute allocation, request one before launching Jupyter. The exact command depends on the ASU machine policy, but a typical Slurm-style allocation looks like this:

```text
salloc --time=04:00:00 --cpus-per-task=4 --mem=32G
```

Start Jupyter on the server without opening a browser:

```text
python -m jupyter lab --no-browser --ip=127.0.0.1 --port=8888 notebooks/exact_tcad_all_experiments.ipynb
```

From your laptop, open an SSH tunnel to the server. Keep this tunnel open while using Jupyter:

```text
ssh -L 8888:127.0.0.1:8888 'asurite\hsiaopin@149.169.30.50'
```

or, without quotes:

```text
ssh -L 8888:127.0.0.1:8888 asurite\\hsiaopin@149.169.30.50
```

Then open the Jupyter URL printed by the server, usually beginning with:

```text
http://127.0.0.1:8888/lab?token=...
```

For the server run, keep the same deterministic settings first:

```python
SEED = 123
THREADS = 1
DATA_MODE = "real"
TCAD_PRESET = "smoke"
RUN_REPEAT_CHECK = True
```

After the smoke run matches, change only the preset for the journal-scale run:

```python
TCAD_PRESET = "full"
```

When the run completes, copy server results back to your laptop if needed:

```text
rsync -avz 'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/notebook_run/' ./citadel_asu_results/
```

If port `8888` is already in use, replace every `8888` above with the same unused port, such as `8890`.

Before every ASU run, check whether GitHub has newer commits:

```text
cd ~/CITADEL
git fetch origin
git status -sb
git log --oneline HEAD..origin/main
```

If the last command prints commits, GitHub has updates that are not yet in this server folder.

Update all tracked folders and files from GitHub:

```text
cd ~/CITADEL
git status
git pull --ff-only origin main
git lfs pull
```

If `git status` shows local edits, commit or stash them before pulling:

```text
git status
git stash push -m "temporary ASU local changes"
git pull --ff-only origin main
git lfs pull
git stash pop
```

After making repo changes on ASU, push them back:

```text
git status
git add README.md docs/ exact/ notebooks/ configs/ tests/
git commit -m "Update CITADEL workflow"
git push origin main
```

### What To Compare Across Machines

After each run, check these outputs:

- `results/notebook_run/ets_baseline/run_manifest.json`
- `results/notebook_run/tcad_ablation/run_manifest.json`
- `results/notebook_run/tcad_ablation/tcad_config_resolved.json`
- `results/notebook_run/tcad_ablation/tcad_ablation_summary.csv`

For strict reproducibility, the resolved config, input hashes, selected-feature files, and summary CSV values should match between the laptop and the ASU server. If they do not match, first check Python version, package versions, Git commit, Git LFS data materialization, `SEED`, `THREADS`, and `TCAD_PRESET`.

The manifest records the git commit, dirty-worktree state, Python version, direct package versions, hashes for `pyproject.toml`, `requirements.txt`, `environment.yml`, input CSV hashes, and output artifact hashes. Treat a run with `"git_dirty": true` as a development run, not a paper-submission run.

## CITADEL Methodology

The project plan is in `docs/tcad_methodology.md`, `docs/research_execution_plan.md`, and `docs/image_flow_methodology.md`. The cover-letter-to-artifact map is in `docs/tcad_requirements_traceability.md`. Together they turn the cover-letter promises into a complete execution path:

1. reproduce the EXACT baseline
2. freeze telemetry schema and platform metadata
3. run systematic CINTAS/CITADEL ablations
4. collect and validate additional platforms and anomaly classes
5. quantify lifecycle drift and benign recalibration
6. implement and verify fixed-point RTL/FPGA CINTAS
7. regenerate all CITADEL/TCAD tables and figures from the notebook and its manifests

## Data

CITADEL tracks real telemetry directly in this repo using Git LFS. The notebook reads DDR4/DDR5 telemetry from `data/telemetry/processed/ddr_data/` and Apple M2 Pro telemetry from `data/telemetry/raw/apple_data/`. Each run manifest records the exact input hashes used for the results.

The deterministic sample dataset is only for testing the pipeline shape. It is not evidence for the paper.

## Relationship to EXACT

This repo starts from the portable EXACT codebase at `https://github.com/ping830616/EXACT` and adds the CITADEL journal framework: design-space exploration, fixed-point precision analysis, hardware-cost modeling, RTL/FPGA-oriented validation, benign-drift checks, and reproducible result manifests. Keep conference-reproduction code stable; add journal experiments through the single notebook, configs, and result manifests.
