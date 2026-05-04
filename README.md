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

- `exact/`: portable Python reference implementation inherited from EXACT, plus CITADEL ablation orchestration
- `notebooks/`: the single experiment runner for EXACT reproduction, CITADEL ablation, hardware summaries, and FPGA/RTL integration hooks
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

Every experiment should be run from the notebook with repo-relative paths. Each notebook run writes `run_manifest.json` files with configuration, package versions, input hashes, and output hashes. Matching manifests across machines mean the same numerical inputs and outputs were used.

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
