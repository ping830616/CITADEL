# Reproducibility Guide

The target is same inputs plus same config plus same environment yields the same outputs across laptops, workstations, and servers.

## Environment

- Python is pinned to `>=3.11,<3.14`.
- Package versions are pinned in `pyproject.toml`, `requirements.txt`, and `environment.yml`.
- Numerical execution is configured through `exact.repro.configure_reproducibility`.
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
- store data-cleaning scripts and config next to generated outputs
- require SHA-256 hashes in every run manifest

## Running On A New Machine

```bash
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git lfs install
git lfs pull
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,notebook]"
python scripts/run_tcad_ablation.py --data-root data/telemetry --out-root results/tcad_full --config configs/tcad_grid_full.json
```

## Manifest Check

Compare these fields in `run_manifest.json`:

- config values
- Python and package versions
- input file hashes
- output file hashes
- git commit

If manifests differ, treat the run as non-identical until the cause is known.
