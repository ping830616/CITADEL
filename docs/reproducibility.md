# Cross-Machine Reproducibility

CITADEL reproduces scientific results from an immutable source snapshot and
the preserved inputs. Exact configuration, schemas, categorical choices,
selected configurations, and feature sets must agree. Numeric values use the
tolerances in `reproducibility/result_contract.json`.

Renderer-dependent image bytes, timestamps, absolute paths, runtime duration,
and raw Vivado report bytes are not portable comparison targets.

## Locked environment

The canonical environment is CPython 3.11.15 with the complete dependency
graph in `uv.lock`:

```bash
uv python install 3.11.15
uv sync --frozen --no-dev
uv lock --check
```

The launcher fixes seed 123, one numerical thread, UTC, locale, and the plotting
backend before starting the analysis process. It records package versions,
platform, NumPy/BLAS/threadpool details, configuration, and file hashes.

## Immutable checkout

```bash
git lfs install
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git checkout paper-r1-reviewer-evidence-v3
git status --porcelain
```

The status command must be empty before a comparison-grade run.

## Two different verification levels

Audit compact evidence and manuscript claims without downloading telemetry:

```bash
uv run --frozen python scripts/reproduce.py verify-paper --scope all
```

The JSON output deliberately separates:

- `coverage_status`: every expected paper item and required compact file exists;
- `traceability_status`: hashes, provenance records, declared figure
  layout/main/legend assets, and manuscript-value checks pass;
- `fresh_clean_rerun_status`: every requested experiment family has retained
  clean-run evidence.

A pass for the first two fields must not be described as a fresh rerun.

Verify the tracked source/input inventory separately:

```bash
uv run --frozen python scripts/reproduce.py verify-archive --scope source
```

## Scoped input download

Download only the inputs needed for one result family:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope core
uv run --frozen python scripts/reproduce.py fetch-lfs --scope sensitivity
uv run --frozen python scripts/reproduce.py fetch-lfs --scope apple
uv run --frozen python scripts/reproduce.py fetch-lfs --scope intel
uv run --frozen python scripts/reproduce.py fetch-lfs --scope rtl
```

Compact paper references are ordinary Git files under
`reproducibility/paper_results/`; `--include-reference` is not required.
Preflight rejects any required input that is still an LFS pointer.

## Isolated runs

All commands write to a new `results/reproduced/<run-id>/` tree. Existing
outputs are rejected rather than mixed with a new run.

```bash
# Main paper results
uv run --frozen python scripts/reproduce.py notebook \
  --profile core --preset full --data-mode real \
  --verify --run-id reviewer-main

# Graph/ranking sensitivity
uv run --frozen python scripts/reproduce.py sensitivity \
  --verify --repeat --run-id reviewer-sensitivity

# Figure 7
uv run --frozen python scripts/reproduce.py intel-orders \
  --verify --repeat --run-id reviewer-intel-orders

# Figure 8
uv run --frozen python scripts/reproduce.py notebook \
  --profile apple --preset full --data-mode real \
  --verify --run-id reviewer-apple
```

`--profile all --verify` is rejected because a notebook-wide development sweep
is not the same as verifying every paper result. Use `verify-paper --scope all`
for the compact audit and the named commands for fresh execution.

## Scientific comparison contract

`scripts/verify_reproducibility.py` enforces:

- exact CSV/JSON schemas, strings, booleans, case IDs, and selected features;
- exact row order unless a rule declares scientific identity keys;
- tolerance-based numeric comparison; the compact paper-result profile rules
  use `rtol=1e-9` and `atol=5e-11`, while the comparison CLI defaults to
  `rtol=1e-10` and `atol=1e-12` only when a rule does not override them;
- failure for missing results and unresolved LFS pointers;
- explicit reporting of any output outside the comparison contract.

Full equivalence requires `status: PASS` and
`verification_coverage: COMPLETE`. `PASS_WITH_UNVERIFIED` or successful
notebook completion alone is not full result equivalence.

Figures are validated as decodable, nonuniform images with the declared layout
and main/legend assets. Their source tables and labels are the cross-machine
comparison targets; the PNG hash is provenance only, and the check does not
claim visual-semantic equivalence.

## Hardware boundary

RTL regeneration requires Vivado 2025.2, SW Build 6299465, part
`xc7a200tfbg676-1`, its device database, and a working license. The committed
RTL evidence is an archived-report reanalysis, not a fresh synthesis run.

For exact commands and current evidence tiers, see the
[reviewer reproduction guide](reviewer_reproduction.md).
