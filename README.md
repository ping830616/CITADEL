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

## Linux / ASU Quick Start

This is the recommended path for reproducing CITADEL on a Linux server. The ASU server examples use:

```text
asurite\hsiaopin@149.169.30.50
```

Use your ASU password only for the `ssh` login. If GitHub asks for a password during `git clone`, paste a GitHub Personal Access Token, not the ASU password.

### 1. Open The SSH Tunnel

On your Mac, open Terminal 1 and keep it open:

```text
ssh -N -L 8888:127.0.0.1:8888 'asurite\hsiaopin@149.169.30.50'
```

This makes the server's Jupyter page available at `http://127.0.0.1:8888` on your Mac.
After you enter your ASU password, this terminal may look blank. That is normal. Keep it open.

If port `8888` is busy, use another port everywhere, for example:

```text
ssh -N -L 8890:127.0.0.1:8890 'asurite\hsiaopin@149.169.30.50'
```

### 2. Log In And Use Bash

Open Terminal 2 on your Mac:

```text
ssh 'asurite\hsiaopin@149.169.30.50'
```

After you are on the server, switch to `bash` first. This avoids shell errors such as `export: Command not found`, `if: Expression Syntax`, and `Too many ('s`.

```text
/bin/bash -l
```

### 3. Clone The Repo For The First Time

Run these commands on the ASU server:

```text
cd ~
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git log --oneline -1
```

If GitHub asks for credentials:

```text
Username for 'https://github.com': ping830616
Password for 'https://ping830616@github.com': paste_your_github_token_here
```

The token needs repository `Contents` permission. `Read-only` is enough to run the notebook; `Read and write` is needed only if you want to push changes from the server.

If GitHub returns `403`, create a new token that explicitly has access to `ping830616/CITADEL`, then retry the clone.

If you already cloned the repo before and GitHub has new updates, you usually do not need to reclone. Update the existing server folder with:

```text
cd ~/CITADEL
git fetch origin
git pull --ff-only origin main
git lfs pull
git log --oneline -1
```

If you prefer a completely fresh copy while keeping the old folder, backup the old folder and reclone:

```text
cd ~
mv CITADEL CITADEL_backup_$(date +%Y%m%d_%H%M%S)
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git lfs install
git lfs pull
git log --oneline -1
```

If `mv` says `No such file or directory`, continue with `git clone`; it only means there was no old `CITADEL` folder.

If you want to completely delete the old folder instead, use this only when you are sure there are no results or edits you need inside `~/CITADEL`:

```text
cd ~
rm -rf CITADEL
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git lfs install
git lfs pull
git log --oneline -1
```

### 4. Get Git LFS Data

The telemetry CSVs are stored with Git LFS. Check whether Git LFS exists:

```text
git lfs version
```

If that command is missing, install Git LFS through Conda:

```text
conda install -c conda-forge git-lfs -y
```

Then fetch the data:

```text
cd ~/CITADEL
git lfs install
git lfs pull
```

If `git clone` prints `git-lfs: command not found` and `Clone succeeded, but checkout failed`, install Git LFS and repair the checkout instead of recloning:

```text
/bin/bash -l
conda install -c conda-forge git-lfs -y
cd ~/CITADEL
git lfs install
git restore --source=HEAD :/
git lfs pull
git status
```

Check that the CSVs are real data, not Git LFS pointer files:

```text
find data/telemetry -name "*.csv" | head -n 1 | xargs head -5
```

If the first line says `version https://git-lfs.github.com/spec/v1`, run `git lfs pull` again and confirm your GitHub token can read this repository.

### 5. Create The Conda Environment

Run:

```text
cd ~/CITADEL
conda env create -f environment.yml
```

If the environment already exists, update it instead:

```text
cd ~/CITADEL
conda env update -f environment.yml --prune
```

Activate the environment:

```text
source ~/miniconda3/etc/profile.d/conda.sh
conda activate citadel-slm
```

If `source ~/miniconda3/etc/profile.d/conda.sh` prints `export: Command not found` or `Too many ('s`, you are still in the server's non-Bash shell. Start Bash and then repeat the Conda activation:

```text
/bin/bash -l
cd ~/CITADEL
source ~/miniconda3/etc/profile.d/conda.sh
conda activate citadel-slm
```

If your Conda installation is somewhere else, find it with:

```text
find ~ -path "*/etc/profile.d/conda.sh" 2>/dev/null | head -n 1
```

Then replace `~/miniconda3/etc/profile.d/conda.sh` with the printed path.

### 6. Start Jupyter In Tmux

Use `tmux` so the notebook keeps running if your laptop disconnects. Start tmux with Bash directly so Conda activation works:

```text
tmux new -s citadel /bin/bash -l
```

If you see `duplicate session: citadel`, an old session is already running. To return to it:

```text
tmux attach -t citadel
```

If you want to cancel the old session and start a new one:

```text
tmux kill-session -t citadel
tmux new -s citadel /bin/bash -l
```

If you are already inside tmux and `source ~/miniconda3/etc/profile.d/conda.sh` prints `export: Command not found` or `Too many ('s`, switch that tmux window into Bash first:

```text
exec /bin/bash -l
```

Then run:

```text
cd ~/CITADEL
source ~/miniconda3/etc/profile.d/conda.sh
conda activate citadel-slm
export PYTHONHASHSEED=123
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export MPLBACKEND=Agg
python -m jupyter lab --no-browser --ip=127.0.0.1 --port=8888 --notebook-dir=notebooks
```

Copy the URL printed by Jupyter. It will look like:

```text
http://127.0.0.1:8888/lab?token=...
```

Open that URL in your Mac browser.

If you used port `8890` for the tunnel, start Jupyter with `--port=8890` and open:

```text
http://127.0.0.1:8890/lab?token=...
```

### 7. Run The Notebook

In JupyterLab, open:

```text
exact_tcad_all_experiments.ipynb
```

For a quick reproducibility check, use these settings in the notebook configuration cell:

```python
SEED = 123
THREADS = 1
DATA_MODE = "real"
TCAD_PRESET = "smoke"
RUN_REPEAT_CHECK = True
```

Then run the notebook from top to bottom.

For the final TCAD journal-scale run, change only:

```python
TCAD_PRESET = "full"
```

Long cells show progress directly in the notebook output. The notebook also writes progress messages here:

```text
results/notebook_run/notebook_progress.log
```

### 8. Leave And Return To The Run

To detach from tmux without stopping Jupyter:

```text
Ctrl-b
d
```

To return later:

```text
ssh 'asurite\hsiaopin@149.169.30.50'
/bin/bash -l
tmux attach -t citadel
```

If `tmux new -s citadel` says `duplicate session: citadel`, the session already exists. Attach to it:

```text
tmux attach -t citadel
```

If you want to cancel that old session and start fresh:

```text
tmux kill-session -t citadel
tmux new -s citadel /bin/bash -l
```

### 9. Update An Existing Clone Later

Use this whenever GitHub has newer notebook or README updates.

From your Mac, SSH to the ASU server:

```text
ssh 'asurite\hsiaopin@149.169.30.50'
```

Then run this on the ASU server:

```text
/bin/bash -l
cd ~/CITADEL
git fetch origin
git status -sb
git log --oneline HEAD..origin/main
git pull --ff-only origin main
git lfs pull
git log --oneline -1
```

If `git log --oneline HEAD..origin/main` prints commits, those commits are waiting to be pulled. If it prints nothing, your server clone is already current.

After pulling notebook changes, refresh JupyterLab, restart the notebook kernel, and run the notebook from the top. This matters because Jupyter keeps old Python functions in memory until the kernel restarts.

### 10. Reclone From Scratch If Needed

If the server folder is messy or authentication was wrong during the first clone, you can backup and reclone:

```text
cd ~
mv CITADEL CITADEL_backup_$(date +%Y%m%d_%H%M%S)
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git lfs install
git lfs pull
git log --oneline -1
```

If `mv` says `No such file or directory`, that is fine. It means there was no old `CITADEL` folder.

Or completely delete the old folder and reclone. Use this only when you are sure there are no results or edits you need inside `~/CITADEL`:

```text
cd ~
rm -rf CITADEL
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git lfs install
git lfs pull
git log --oneline -1
```

### 11. Copy Results Back To Your Mac

After the notebook completes, run this from your Mac:

```text
rsync -avz 'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/notebook_run/' ./citadel_asu_results/
```

## Laptop Quick Check

For a local smoke run on macOS or Linux:

```text
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git lfs install
git lfs pull
conda env create -f environment.yml
source ~/miniconda3/etc/profile.d/conda.sh
conda activate citadel-slm
python -m jupyter lab notebooks/exact_tcad_all_experiments.ipynb
```

Use the same notebook settings as the ASU smoke run first. For final paper numbers, prefer the ASU Linux server and keep `TCAD_PRESET = "full"`.

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
