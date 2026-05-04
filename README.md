# EXACT-TCAD

**EXACT-TCAD** is the journal-extension workspace for **EXACT**: Edge-eXplainable Autonomous Causal Telemetry for silicon lifecycle management.

The ETS version established the edge-only CINTAS detector on two CPU-DRAM platforms. This repo is organized around the TCAD extension described in the cover letter:

- design-space ablations for feature budget, aggregation, decision-block length, score weighting, and fixed-point precision
- broader heterogeneous-platform and SLM-anomaly validation
- FPGA/RTL implementation and cost evaluation for CINTAS
- drift-aware lifecycle calibration, recalibration, and explainable anomaly context

The code is intentionally portable: Python versions are pinned, runtime seeds and thread counts are fixed, generated artifacts receive SHA-256 manifests, and the smoke-test dataset is deterministic.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,notebook]"

python scripts/generate_sample_data.py --out-root data/sample --rows 600
python scripts/run_tcad_ablation.py --data-root data/sample --out-root results/tcad_smoke --preset smoke
pytest
```

For Conda:

```bash
conda env create -f environment.yml
conda activate exact-tcad
```

## Repository Map

- `exact/`: portable Python reference implementation inherited from EXACT, plus TCAD ablation orchestration
- `scripts/`: command-line entry points for sample data, ETS reproduction, and TCAD sweeps
- `configs/`: smoke and full ablation grids
- `docs/`: start-to-finish methodology, data schema, reproducibility checklist, and RTL plan
- `rtl/cintas/`: synthesizable CINTAS SystemVerilog starter design and testbench notes
- `data/telemetry/`: real telemetry snapshot location, tracked with Git LFS when added
- `data/sample/`: deterministic generated data for smoke tests, not tracked
- `results/`: generated tables, plots, and run manifests, not tracked

## Reproducibility Contract

Every experiment should be runnable from the command line with repo-relative paths:

```bash
python scripts/run_tcad_ablation.py \
  --data-root data/telemetry \
  --out-root results/tcad_full \
  --config configs/tcad_grid_full.json
```

Each run writes `run_manifest.json` files with configuration, package versions, input hashes, and output hashes. Matching manifests across machines mean the same numerical inputs and outputs were used.

## TCAD Methodology

The project plan is in `docs/tcad_methodology.md`. It turns the cover-letter promises into a complete execution path:

1. reproduce the ETS baseline
2. freeze telemetry schema and platform metadata
3. run systematic CINTAS/EXACT ablations
4. collect and validate additional platforms and anomaly classes
5. quantify lifecycle drift and benign recalibration
6. implement and verify fixed-point RTL/FPGA CINTAS
7. regenerate all TCAD tables and figures from manifests

## Data

Large telemetry CSVs should be added under `data/telemetry/` using Git LFS:

```bash
git lfs install
git lfs track "data/telemetry/*.csv"
```

The deterministic sample dataset is only for testing the pipeline shape. It is not evidence for the paper.

## Relationship to EXACT

This repo starts from the portable EXACT codebase at `https://github.com/ping830616/EXACT` and adds TCAD-specific experiment orchestration, documentation, and RTL scaffolding. Keep conference-reproduction code stable; add journal experiments through new configs, scripts, and result manifests.
