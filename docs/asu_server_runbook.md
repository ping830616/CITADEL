# ASU Server Runbook

This document is the ASU-specific execution guide for CITADEL. The general reproducibility workflow is in the repository `README.md`; this file contains only the ASU server details, shell fixes, tmux/Jupyter setup, GitHub token notes, and file-transfer commands.

The ASU server examples use:

```text
asurite\hsiaopin@149.169.30.50
```

Use your ASU password only for the `ssh` login. If GitHub asks for a password during `git clone`, paste a GitHub Personal Access Token, not the ASU password.

## 1. Open The SSH Tunnel

On your Mac, open Terminal 1 and keep it open:

```text
ssh -N -L 8888:127.0.0.1:8888 'asurite\hsiaopin@149.169.30.50'
```

This makes the server's Jupyter page available at `http://127.0.0.1:8888` on your Mac. After you enter your ASU password, this terminal may look blank. That is normal. Keep it open.

If port `8888` is busy, use another port everywhere, for example:

```text
ssh -N -L 8890:127.0.0.1:8890 'asurite\hsiaopin@149.169.30.50'
```

If the Mac says `Address already in use`, find and stop the old tunnel:

```text
lsof -iTCP:8888 -sTCP:LISTEN
kill -9 PID
```

Replace `PID` with the process id printed by `lsof`.

## 2. Log In And Use Bash

Open Terminal 2 on your Mac:

```text
ssh 'asurite\hsiaopin@149.169.30.50'
```

After you are on the server, switch to Bash first. This avoids shell errors such as `export: Command not found`, `if: Expression Syntax`, and `Too many ('s`.

```text
/bin/bash -l
```

## 3. Clone Or Update CITADEL

For a comparison-grade first clone, replace `<artifact-commit-or-tag>` with the
immutable identifier cited by the manuscript:

```text
cd ~
export GIT_LFS_SKIP_SMUDGE=1
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git checkout <artifact-commit-or-tag>
git lfs install
git log --oneline -1
git status --porcelain
```

The final command must print nothing. Updating to moving `main` is appropriate
for development, but it is not an immutable reviewer run.

If GitHub asks for credentials:

```text
Username for 'https://github.com': ping830616
Password for 'https://ping830616@github.com': paste_your_github_token_here
```

The token needs repository `Contents` permission. `Read-only` is enough to run the notebook; `Read and write` is needed only if you want to push changes from the server.

If GitHub returns `403`, create a new token that explicitly has access to `ping830616/CITADEL`, then retry the clone.

If the repo already exists on the server, update it:

```text
cd ~/CITADEL
git fetch origin
git status -sb
git log --oneline HEAD..origin/main
git pull --ff-only origin main
git lfs pull
git log --oneline -1
```

If `git log --oneline HEAD..origin/main` prints commits, those commits are waiting to be pulled. If it prints nothing, your server clone is already current.

## 4. Reclone If Needed

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

If `mv` says `No such file or directory`, continue with `git clone`; it only means there was no old `CITADEL` folder.

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

## 5. Get Git LFS Data

The telemetry CSVs are stored with Git LFS. Check whether Git LFS exists:

```text
git lfs version
```

If that command is missing, install Git LFS through Conda:

```text
conda install -c conda-forge git-lfs -y
```

Then fetch only the experiment profile rather than the entire archive:

```text
cd ~/CITADEL
git lfs install
python3 scripts/reproduce.py fetch-lfs --scope core
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

## 6. Create The Exact Environment

The primary reviewer path uses uv 0.12.13 and the complete checked-in lock:

```text
cd ~/CITADEL
python3 -m venv ~/citadel-uv-bootstrap
source ~/citadel-uv-bootstrap/bin/activate
python -m pip install uv==0.12.13
uv python install 3.11.15
uv sync --frozen
uv lock --check
```

Conda is an alternative with the same exact Python and direct package pins:

```text
cd ~/CITADEL
conda env create -f environment.yml
conda activate citadel-slm
```

If that environment already exists, update it instead:

```text
conda env update -f environment.yml --prune
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

## 7. Start Jupyter In Tmux

Use `tmux` so the notebook keeps running if your laptop disconnects. Start tmux with Bash directly so the locked `uv` environment and the optional Conda alternative work normally:

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
export PYTHONHASHSEED=123
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export MPLBACKEND=Agg
export CITADEL_INTERACTIVE_RUN=asu-interactive-$(date -u +%Y%m%dT%H%M%SZ)
export CITADEL_RESULTS_ROOT=results/reproduced/$CITADEL_INTERACTIVE_RUN/notebook_run
uv run --frozen python -m jupyter lab --no-browser --ip=127.0.0.1 --port=8888 --notebook-dir=notebooks
```

Copy the URL printed by Jupyter. It will look like:

```text
http://127.0.0.1:8888/lab?token=...
```

Open that URL in your Mac browser. If you used port `8890` for the tunnel, start Jupyter with `--port=8890` and open:

```text
http://127.0.0.1:8890/lab?token=...
```

## 8. Run The Notebook

In JupyterLab, open:

```text
exact_tcad_all_experiments.ipynb
```

Run the lightweight, isolated repeat check first:

```text
uv run --frozen python scripts/reproduce.py notebook \
  --profile smoke --preset smoke --data-mode sample \
  --repeat --run-id asu-smoke
```

To reconstruct and compare the paper-selected Table VI operating points, run:

```text
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope core --include-reference
uv run --frozen python scripts/reproduce.py notebook \
  --profile core --preset full --data-mode real \
  --verify --run-id asu-core
```

Use the `balanced` preset only for development; it does not contain every Table
VI setting. The focused graph/ranking sensitivity study is separate from the
exhaustive DSE and has its own `scripts/reproduce.py sensitivity --verify`
entry point. Long cells show progress directly in the notebook output. The
named wrapper run also writes progress messages here:

```text
results/reproduced/asu-core/notebook_run/notebook_progress.log
```

## 9. Set Up Vivado On The ASU Tools Server

### MacBook To ASU Vivado Handoff

Use this handoff when the notebook is run on the MacBook but synthesis is run
on ASU. Clone the immutable artifact commit independently rather than mirroring
a working tree, so the launcher's clean-checkout gate and source hashes remain
meaningful.

On both machines, confirm the manuscript's exact commit:

```text
cd ~/CITADEL
git rev-parse HEAD
git status --porcelain
```

The hashes must match and the status commands must print nothing. On ASU, use
that immutable checkout, materialize the RTL reference scope, and write a fresh
run only below `results/reproduced/`:

```text
uv run --frozen python scripts/reproduce.py fetch-lfs --scope rtl
tcsh -c 'source ~/settings64_vivado_2025_2.csh; cd ~/CITADEL; uv run --frozen python scripts/reproduce_rtl.py --output-root results/reproduced/asu-rtl-reviewer'
```

The launcher parses and compares the reports on ASU using the locked Python
environment. Copy only that uniquely named reproduction bundle back to a
different `results/reproduced/` directory on the MacBook:

```text
mkdir -p /Users/hsiaopingni/CITADEL/results/reproduced/from-asu
rsync -avz --progress \
  'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/reproduced/asu-rtl-reviewer/' \
  /Users/hsiaopingni/CITADEL/results/reproduced/from-asu/
```

Never copy a reproduction over `results/notebook_run/rtl_sweep/`; that path is
the immutable archived reference. Retain `reproduction_plan.json`,
`run_manifest.json`, and `comparison_report.json` with the transferred reports.

### Vivado Setup

Vivado 2025.2 Standard Edition is installed on the ASU tools mount. Use this flow on:

```text
149.169.30.50
```

which should report host `en4226599rl`.

Log in and check the tools mount:

```text
ssh 'asurite\hsiaopin@149.169.30.50'
hostname
df -h /usr/local/tools
ls -l /usr/local/tools/vivado/2025.2/Vivado/settings64.csh
```

If you use another ASU server, confirm that `/usr/local/tools` is mounted from `129.219.4.25:/data/tools`. The Vivado setup file is written for the `/usr/local/tools` path.

Copy the setup file to your home folder and load it through `tcsh`:

```text
cp /usr/local/tools/vivado/2025.2/Vivado/settings64.csh ~/settings64_vivado_2025_2.csh
tcsh -c 'source ~/settings64_vivado_2025_2.csh; rehash; which vivado; vivado -version'
```

If you are in Bash, run Vivado commands through `tcsh -c`. The ASU `tcsh` does not support `-lc`:

```text
tcsh -c 'source ~/settings64_vivado_2025_2.csh; vivado -version'
```

To launch the GUI from Bash with display forwarding:

```text
tcsh -c 'source ~/settings64_vivado_2025_2.csh; exec vivado' &
```

For paper artifacts, keep the immutable checkout clean and use the strict RTL
launcher. It pins the four selected configurations, Artix-7 part
`xc7a200tfbg676-1`, 25 ns period, and Vivado 2025.2 build 6299465. First
materialize the archived comparison reports and inspect the exact plan:

```text
cd ~/CITADEL
git status --short
uv run --frozen python scripts/reproduce.py fetch-lfs --scope rtl
uv run --frozen python scripts/reproduce_rtl.py --dry-run
```

Do not fetch helpers from a moving branch or write into
`results/notebook_run/rtl_sweep`; that directory is the archived reference.
Run all four configurations into a new, isolated result directory. From Bash,
load Vivado through `tcsh` while preserving the immutable repository sources:

```text
tcsh -c 'source ~/settings64_vivado_2025_2.csh; cd ~/CITADEL; uv run --frozen python scripts/reproduce_rtl.py --output-root results/reproduced/asu-rtl'
```

Choose a new output-root name for every attempt. The launcher parses the fresh
reports, writes a provenance manifest, and compares the scientific fields with
the archived summary. It rejects a missing report/checkpoint, an unfetched LFS
pointer, or any `run_config.csv` that differs from the four frozen tags, target
part, feature/Q/sample parameters, or literal `25.000` ns period. The reports
are written under:

```text
results/reproduced/asu-rtl/<tag>/
```

The important files are:

```text
utilization.rpt
timing_summary.rpt
power.rpt
post_synth.dcp
run_config.csv
rtl_resource_summary.csv
```

Do not substitute a different FPGA part for an archival comparison. A different
device is a new experiment and must use a separately named output root and must
not be described as reproducing the archived resource figures.

## 10. Leave And Return To The Run

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

## 11. Push Your Edits From ASU

If you edit the notebook yourself and want GitHub to receive those changes:

```text
/bin/bash -l
cd ~/CITADEL
git status -sb
git add notebooks/exact_tcad_all_experiments.ipynb README.md docs/ scripts/
git commit -m "Update CITADEL notebook and paper notes"
git push origin main
git status -sb
```

After pulling notebook changes, refresh JupyterLab, restart the notebook kernel, and run the notebook from the top. Jupyter keeps old Python functions in memory until the kernel restarts.

## 12. Copy Files Or Folders From ASU To Your Mac

Run these commands from your Mac terminal, not inside the ASU SSH session.

Copy the named `asu-core` reproduction bundle, including its receipt and
comparison report:

```text
mkdir -p ~/Downloads/citadel_asu_results
rsync -avz --progress 'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/reproduced/asu-core/' ~/Downloads/citadel_asu_results/
```

Copy any single file:

```text
scp 'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/reproduced/asu-core/notebook_run/tcad_ablation/tcad_ablation_summary.csv' ~/Downloads/
```

Copy any folder by replacing the server path and local destination:

```text
rsync -avz --progress 'asurite\hsiaopin@149.169.30.50:~/CITADEL/path/to/server_folder/' ~/Downloads/local_folder/
```

Copy the whole CITADEL folder, excluding the Git history and common cache files:

```text
mkdir -p ~/Downloads/CITADEL_from_ASU
rsync -avz --progress --exclude '.git/' --exclude '.venv/' --exclude '__pycache__/' --exclude '.ipynb_checkpoints/' 'asurite\hsiaopin@149.169.30.50:~/CITADEL/' ~/Downloads/CITADEL_from_ASU/
```
