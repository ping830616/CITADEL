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
- store data-cleaning notebook cells and config next to generated outputs
- require SHA-256 hashes in every run manifest

## Running On A New Machine

Use a Git client with Git LFS enabled so the tracked CSV files are materialized, not left as pointer files. Then open `notebooks/exact_tcad_all_experiments.ipynb` in Jupyter and run it from top to bottom. The notebook is the only experiment entry point.

## Manifest Check

Compare these fields in `run_manifest.json`:

- config values
- Python and package versions
- input file hashes
- output file hashes
- git commit

If manifests differ, treat the run as non-identical until the cause is known.
