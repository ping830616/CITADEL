# Reproducibility Guide

The target is same inputs plus same config plus same environment yields the same outputs across laptops, workstations, and servers.

## Environment

- Python is pinned to `>=3.11,<3.14`.
- Package versions are pinned in `requirements.txt` and `environment.yml`.
- Numerical execution is configured inside the single notebook.
- Default runs use `seed=123` and `threads=1`.

## Data

Use immutable data snapshots:

```text
data/telemetry/raw/<snapshot_id>/
data/telemetry/processed/<snapshot_id>/
data/platforms/<setup>.json
```

Rules:

- add large CSVs with Git LFS
- never edit a snapshot in place
- store data-cleaning notebook cells and config next to generated outputs
- require SHA-256 hashes in every run manifest

## Running On A New Machine

Use a Git client with Git LFS enabled so the tracked CSV files are materialized, not left as pointer files. Then open `notebooks/exact_tcad_all_experiments.ipynb` in Jupyter and run it from top to bottom. The notebook is the only experiment entry point.

## ASU Linux Server

Use the ASU server for reproducible research runs when you want the same notebook flow on Linux.

Connect from your laptop with either quoted username syntax:

```text
ssh 'asurite\hsiaopin@149.169.30.50'
```

or escaped backslash syntax:

```text
ssh asurite\\hsiaopin@149.169.30.50
```

On the server:

```text
tmux new -s citadel
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
export PYTHONHASHSEED=123
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export MPLBACKEND=Agg
python -m jupyter lab --no-browser --ip=127.0.0.1 --port=8888 notebooks/exact_tcad_all_experiments.ipynb
```

If you manually run `mv ~/CITADEL ...` and it says `No such file or directory`, continue. There was no old clone to move.

If `git lfs` is not installed, use Conda:

```text
conda install -c conda-forge git-lfs -y
which git-lfs
git-lfs --version
cd ~/CITADEL
git lfs install
git lfs pull
```

Confirm that LFS downloaded real data:

```text
find data/telemetry -name "*.csv" | head -n 1 | xargs head -5
```

The output should show CSV content. If it starts with `version https://git-lfs.github.com/spec/v1`, the file is still a Git LFS pointer.

Before each run, check whether GitHub has newer commits:

```text
cd ~/CITADEL
git fetch origin
git status -sb
git log --oneline HEAD..origin/main
```

If `git log --oneline HEAD..origin/main` prints commits, GitHub has updates that are not yet in this local folder.

Update all tracked folders and files from GitHub:

```text
cd ~/CITADEL
git pull --ff-only origin main
git lfs pull
```

If the server has local edits, commit or stash them before pulling:

```text
git status
git stash push -m "temporary ASU local changes"
git pull --ff-only origin main
git lfs pull
git stash pop
```

After editing repo files on ASU, keep GitHub current:

```text
git status
git add README.md docs/ notebooks/ configs/ hardware/ rtl/ data/ environment.yml requirements.txt .github/workflows/ci.yml
git commit -m "Update CITADEL workflow"
git push origin main
```

Use two Mac terminal windows for remote Jupyter.

Terminal 1 is only the tunnel. Start it on your Mac and keep it open:

```text
ssh -L 8888:127.0.0.1:8888 'asurite\hsiaopin@149.169.30.50'
```

Terminal 2 starts Jupyter. Open a second Mac terminal, SSH normally, update the repo, activate the environment, and launch Jupyter:

```text
ssh 'asurite\hsiaopin@149.169.30.50'
cd ~/CITADEL
git fetch origin
git status -sb
git log --oneline HEAD..origin/main
git pull --ff-only origin main
git lfs pull
conda activate citadel-slm
export PYTHONHASHSEED=123
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export MPLBACKEND=Agg
python -m jupyter lab --no-browser --ip=127.0.0.1 --port=8888 notebooks/exact_tcad_all_experiments.ipynb
```

Open the local URL in your Mac browser and use the token printed by Terminal 2:

```text
http://127.0.0.1:8888/lab?token=...
```

Run `TCAD_PRESET = "smoke"` first. After the smoke run matches locally, change only `TCAD_PRESET` to `"full"` for the journal-scale run.

Copy results back from the server with:

```text
rsync -avz 'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/notebook_run/' ./citadel_asu_results/
```

## Manifest Check

Compare these fields in `run_manifest.json`:

- config values
- Python and package versions
- input file hashes
- output file hashes
- git commit

If manifests differ, treat the run as non-identical until the cause is known.
