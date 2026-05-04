# CITADEL

**CITADEL** is the journal-extension workspace for **Causal In-Field Telemetry Analytics and Drift-Aware Edge Learning for Silicon Lifecycle Management**.

The repository builds on **EXACT**: Edge-eXplainable Autonomous Causal Telemetry. EXACT established the edge-only CINTAS detector on two CPU-DRAM platforms. CITADEL turns that detector into a hardware-aware and drift-aware SLM methodology:

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
conda activate citadel-slm
```

## Repository Map

- `exact/`: portable Python reference implementation inherited from EXACT, plus CITADEL ablation orchestration
- `scripts/`: command-line entry points for sample data, EXACT reproduction, and CITADEL/TCAD sweeps
- `notebooks/`: single-notebook runner for EXACT reproduction, CITADEL ablation, hardware summaries, and FPGA/RTL integration hooks
- `configs/`: smoke and full ablation grids
- `docs/`: start-to-finish methodology, traceability matrix, data schema, reproducibility checklist, and RTL plan
- `docs/figures/`: CITADEL manuscript PNG assets for Overleaf figures and draft table images
- `rtl/cintas/`: synthesizable CINTAS SystemVerilog starter design and testbench notes
- `data/external_sources.json`: versioned registry for external DDR and Apple telemetry sources
- `data/telemetry/processed/ddr_data/`: DDR4/DDR5 CSV target for CITADEL CINTAS experiments
- `data/telemetry/raw/apple_data/`: Apple M2 Pro tier-0/1/2 target for observability studies
- `data/sample/`: deterministic generated data for smoke tests, not tracked
- `results/`: generated tables, plots, and run manifests, not tracked

## Reproducibility Contract

Every experiment should be runnable from the command line with repo-relative paths:

```bash
python scripts/prepare_external_data.py --source ddr_data --download
python scripts/run_tcad_ablation.py \
  --data-root data/telemetry/processed/ddr_data \
  --out-root results/tcad_full \
  --config configs/tcad_grid_full.json
```

Each run writes `run_manifest.json` files with configuration, package versions, input hashes, and output hashes. Matching manifests across machines mean the same numerical inputs and outputs were used.

For a one-command local smoke reproduction:

```bash
make reproduce-smoke
```

For the single-notebook workflow:

```bash
jupyter lab notebooks/exact_tcad_all_experiments.ipynb
```

For an isolated container run:

```bash
docker build -t citadel-slm .
docker run --rm citadel-slm
```

## CITADEL Methodology

The project plan is in `docs/tcad_methodology.md`, `docs/research_execution_plan.md`, and `docs/image_flow_methodology.md`. The cover-letter-to-artifact map is in `docs/tcad_requirements_traceability.md`. Together they turn the cover-letter promises into a complete execution path:

1. reproduce the EXACT baseline
2. freeze telemetry schema and platform metadata
3. run systematic CINTAS/CITADEL ablations
4. collect and validate additional platforms and anomaly classes
5. quantify lifecycle drift and benign recalibration
6. implement and verify fixed-point RTL/FPGA CINTAS
7. regenerate all CITADEL/TCAD tables and figures from manifests

## Data

CITADEL tracks external telemetry through `data/external_sources.json`. Large CSVs are downloaded locally and ignored by git, while each run manifest records the exact input hashes used for the results.

```bash
# Hardware-counter data for CITADEL CINTAS experiments.
python scripts/prepare_external_data.py --source ddr_data --download

# Apple M2 Pro tiered telemetry for limited-observability studies.
python scripts/prepare_external_data.py --source apple_data --download

# Small laptop smoke subset of DDR data.
python scripts/prepare_external_data.py \
  --source ddr_data \
  --workloads dft,mm \
  --download
```

The deterministic sample dataset is only for testing the pipeline shape. It is not evidence for the paper.

## Relationship to EXACT

This repo starts from the portable EXACT codebase at `https://github.com/ping830616/EXACT` and adds the CITADEL journal framework: design-space exploration, fixed-point precision analysis, hardware-cost modeling, RTL/FPGA-oriented validation, benign-drift checks, and reproducible result manifests. Keep conference-reproduction code stable; add journal experiments through new configs, scripts, and result manifests.
