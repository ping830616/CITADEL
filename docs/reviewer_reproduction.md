# Reviewer Reproduction Guide

This guide defines exactly what the CITADEL repository verifies and how to
regenerate each experimental result in the paper.

## What a passing check means

The supported cross-machine target is scientific equivalence:

- exact source snapshot, input identities, schemas, categorical choices, and
  selected configurations;
- numerical agreement under the checked-in tolerances and at the precision
  printed in the manuscript;
- decodable, nonempty figures with their declared layout and main/legend
  assets.

Figure validation is structural; it does not claim pixel-level or
visual-semantic equivalence across renderers.

PNG bytes, timestamps, host paths, elapsed times, and raw Vivado report bytes
may differ across systems. New live telemetry is an independent experiment and
is not expected to reproduce archived measurements exactly.

The paper audit deliberately reports two different conclusions:

- `coverage_status` and `traceability_status` cover the compact evidence for
  every enumerated Section V table, figure, and numerical claim;
- `fresh_clean_rerun_status` is `PASS` only if every requested family has an
  explicitly retained clean rerun of the experiment itself.

Do not describe every result as freshly rerun unless all three fields pass.

## 1. Prepare an immutable checkout

```bash
git lfs install
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git checkout paper-r1-reviewer-evidence-v3
git rev-parse HEAD
git status --porcelain
```

Save the full commit hash. `git status --porcelain` must be empty before a
comparison-grade run.

## 2. Create the locked environment

```bash
uv python install 3.11.15
uv sync --frozen --no-dev
uv lock --check
uv run --frozen python scripts/reproduce.py verify-archive --scope source
```

The launcher starts analysis processes with seed 123, one numerical thread,
UTC, a fixed locale, and a noninteractive plotting backend. Run manifests also
record package versions, platform, NumPy/BLAS information, configuration, and
input/output hashes.

## 3. Check the committed paper evidence

```bash
uv run --frozen python scripts/reproduce.py verify-paper --scope all
```

This fast audit reads ordinary Git files under
[`reproducibility/paper_results/`](../reproducibility/paper_results/). It does
not download telemetry or pretend to execute the long experiments.

For one family, replace `all` with `core`, `sensitivity`, `rtl`, `intel`, or
`apple`.

## 4. Regenerate a paper-result family

### Main results: Tables VI–X and Figures 3, 4, and 6

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope core
uv run --frozen python scripts/reproduce.py preflight --scope core
uv run --frozen python scripts/reproduce.py notebook \
  --profile core --preset full --data-mode real \
  --verify --run-id reviewer-main
```

The preserved full run took roughly 15 hours on its source machine. The
launcher projects only paper-facing results into the run-local
`paper_results/core/` directory before comparison.

### Section V-D graph/ranking sensitivity

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope sensitivity
uv run --frozen python scripts/reproduce.py preflight --scope sensitivity
uv run --frozen python scripts/reproduce.py sensitivity \
  --verify --repeat --run-id reviewer-sensitivity
```

This focused run evaluates the four frozen operating points; it does not
reselect the design-space optimum.

### Figure 7 recorded benign workload order

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope intel
uv run --frozen python scripts/reproduce.py preflight --scope intel
uv run --frozen python scripts/reproduce.py intel-orders \
  --verify --repeat --run-id reviewer-intel-orders
```

The canonical run uses both setups, ten nonoverlapping recording-block
replicates, 104 calibration blocks and 156 evaluation blocks per replicate,
and 10,000 bootstrap resamples. Boundaries are constructed from separately
recorded benign files; this does not measure a physical switch transient.

### Figure 8 Apple limited observability

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope apple
uv run --frozen python scripts/reproduce.py preflight --scope apple
uv run --frozen python scripts/reproduce.py notebook \
  --profile apple --preset full --data-mode real \
  --verify --run-id reviewer-apple
```

Each observability view uses its own reference and feature selection.

### Figure 5 and Table XI RTL synthesis

This requires Vivado 2025.2, SW Build 6299465, a working license/device
database, and part `xc7a200tfbg676-1`.

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope rtl
uv run --frozen python scripts/reproduce_rtl.py \
  --output-root results/reproduced/reviewer-rtl --dry-run
uv run --frozen python scripts/reproduce_rtl.py \
  --output-root results/reproduced/reviewer-rtl
```

The checker compares the manuscript fields at their printed precision: WNS to
three decimals, frequency to two decimals, total power to the integer mW, and
Figure 5 utilization percentages to one decimal. It also checks the target,
tool build, timing constraint, four cases, timing closure, and zero BRAM.

## 5. Acceptance reports

| Family | Report |
|---|---|
| Core/Apple | `<run-id>/paper_result_comparison.json` |
| Repeated core/Apple | `<run-id>-repeat/paper_result_repeat_comparison.json` |
| Sensitivity | `<run-id>/paper_result_comparison.json` |
| Repeated sensitivity | `<run-id>-repeat/repeat_comparison.json` |
| Figure 7 | `<run-id>/figure7_archive_comparison.json` and `figure7_claim_verification.json` |
| Repeated Figure 7 | `<run-id>-repeat/repeat_comparison.json` |
| RTL | `reviewer-rtl/comparison_report.json` |

All paths above are under `results/reproduced/`. Require `status: PASS` and,
where present, `verification_coverage: COMPLETE`. A notebook finishing without
a passing comparison report is not evidence of equivalence.

## Current evidence tiers

| Family | Current committed evidence |
|---|---|
| Core | Hashed historical paper projection (`REFERENCE_ONLY`); full clean rerun command is available. |
| Sensitivity | Clean archived run and claim audit. |
| RTL | Archived-report reanalysis; `fresh_vivado_synthesis: false`. |
| Figure 7 | Two clean unchanged runs with complete repeat verification. |
| Apple | Hashed historical paper projection (`REFERENCE_ONLY`); clean rerun command is available. |

This is why the repository can state that every enumerated Section V table,
figure, and numerical claim is mapped and auditable, while still withholding
the broader claim that every experiment has already been independently rerun
on another machine.
