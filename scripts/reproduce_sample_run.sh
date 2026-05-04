#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

EXACT_SEED="${EXACT_SEED:-123}"
export PYTHONHASHSEED="${PYTHONHASHSEED:-$EXACT_SEED}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"

python scripts/generate_sample_data.py --out-root data/sample --seed "$EXACT_SEED" --rows 600
python scripts/run_exact_ets2026.py --data-root data/sample --out-root results/sample_ets --seed "$EXACT_SEED" --threads 1
python scripts/run_tcad_ablation.py --data-root data/sample --out-root results/sample_tcad --preset smoke --seed "$EXACT_SEED" --threads 1
