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

For the first clone:

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

## 6. Create The Conda Environment

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

## 7. Start Jupyter In Tmux

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

Open that URL in your Mac browser. If you used port `8890` for the tunnel, start Jupyter with `--port=8890` and open:

```text
http://127.0.0.1:8890/lab?token=...
```

## 8. Run The Notebook

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

For the final TCAD journal-scale run, change only:

```python
TCAD_PRESET = "full"
```

Then run the notebook from top to bottom. Long cells show progress directly in the notebook output. The notebook also writes progress messages here:

```text
results/notebook_run/notebook_progress.log
```

## 9. Set Up Vivado On The ASU Tools Server

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

Copy the setup file to your home folder and source it:

```text
cp /usr/local/tools/vivado/2025.2/Vivado/settings64.csh ~/settings64_vivado_2025_2.csh
source ~/settings64_vivado_2025_2.csh
rehash
which vivado
vivado -version
```

If you are in Bash, run Vivado commands through `tcsh`:

```text
tcsh -lc 'source ~/settings64_vivado_2025_2.csh; vivado -version'
```

To launch the GUI from a terminal with display forwarding:

```text
source ~/settings64_vivado_2025_2.csh
vivado &
```

For paper artifacts, batch mode is preferred. From `~/CITADEL`, run FPGA-oriented synthesis for the selected CITADEL settings:

```text
cd ~/CITADEL
git fetch origin main
mkdir -p scripts
git show origin/main:scripts/vivado_cintas_synth.tcl > scripts/vivado_cintas_synth.tcl
ls -lh scripts/vivado_cintas_synth.tcl

mkdir -p results/notebook_run/rtl_sweep/A_DROOP
mkdir -p results/notebook_run/rtl_sweep/A_RH
mkdir -p results/notebook_run/rtl_sweep/B_DROOP
mkdir -p results/notebook_run/rtl_sweep/B_SPECTRE

vivado -mode batch -source scripts/vivado_cintas_synth.tcl -log results/notebook_run/rtl_sweep/A_DROOP/vivado.log -journal results/notebook_run/rtl_sweep/A_DROOP/vivado.jou -tclargs A_DROOP xc7a35tcpg236-1 15 15 1000
vivado -mode batch -source scripts/vivado_cintas_synth.tcl -log results/notebook_run/rtl_sweep/A_RH/vivado.log -journal results/notebook_run/rtl_sweep/A_RH/vivado.jou -tclargs A_RH xc7a35tcpg236-1 20 8 550
vivado -mode batch -source scripts/vivado_cintas_synth.tcl -log results/notebook_run/rtl_sweep/B_DROOP/vivado.log -journal results/notebook_run/rtl_sweep/B_DROOP/vivado.jou -tclargs B_DROOP xc7a35tcpg236-1 15 15 200
vivado -mode batch -source scripts/vivado_cintas_synth.tcl -log results/notebook_run/rtl_sweep/B_SPECTRE/vivado.log -journal results/notebook_run/rtl_sweep/B_SPECTRE/vivado.jou -tclargs B_SPECTRE xc7a35tcpg236-1 30 8 700
```

The `git show` command above fetches only the Vivado Tcl helper. It is useful when `git pull` is blocked by local notebook edits or by missing Git LFS on the ASU server.

If running from Bash, wrap each command with `tcsh -lc`, for example:

```text
tcsh -lc 'source ~/settings64_vivado_2025_2.csh; cd ~/CITADEL; vivado -mode batch -source scripts/vivado_cintas_synth.tcl -log results/notebook_run/rtl_sweep/A_DROOP/vivado.log -journal results/notebook_run/rtl_sweep/A_DROOP/vivado.jou -tclargs A_DROOP xc7a35tcpg236-1 15 15 1000'
```

The reports are written under:

```text
results/notebook_run/rtl_sweep/<tag>/
```

The important files are:

```text
utilization.rpt
timing_summary.rpt
power.rpt
post_synth.dcp
```

Use the same FPGA part for all rows. If ASU provides a specific board part, replace `xc7a35tcpg236-1` with that part in every command.

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

Copy the main notebook results folder:

```text
mkdir -p ~/Downloads/citadel_asu_results
rsync -avz --progress 'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/notebook_run/' ~/Downloads/citadel_asu_results/
```

Copy any single file:

```text
scp 'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/notebook_run/tcad_ablation/tcad_ablation_summary.csv' ~/Downloads/
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
