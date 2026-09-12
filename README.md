# CITADEL

[![Reproducibility CI](https://github.com/ping830616/CITADEL/actions/workflows/ci.yml/badge.svg)](https://github.com/ping830616/CITADEL/actions/workflows/ci.yml)

This repository contains the code, preserved telemetry, locked software
environment, and result records used for the CITADEL paper.

## Reproducibility target

The target is the experimental evidence reported in Section V: Tables VI-IX
and XI, Figures 3-8, and the numerical results in Sections V-B and V-D. Table
X is a literature comparison; its CITADEL row can be checked against Tables VI
and IX, while the cited prior-work rows are not new experimental outputs.

Reproduction does not require collecting new telemetry, matching every
intermediate file, regenerating unused plots, or producing byte-identical PNG
files. Scientific tables, schemas, categorical values, and selected
configurations must agree; floating-point values use the declared tolerances,
and figures are rebuilt from the verified source tables.

The graph- and ranking-sensitivity results have clean archived evidence. The
other paper-result families have deterministic entry points below, but their
historical references are not all clean and complete. Do not describe the
entire Section V result set as independently verified until clean runs of those
paper-facing outputs have been retained.

## Step-by-step reproduction

### 1. Get the exact source

Install Git, Git LFS, and [uv](https://docs.astral.sh/uv/). The paper-results
snapshot is tagged `paper-r1-results-reproducibility`; use that immutable tag
rather than a moving branch as the experiment identifier.

```bash
git lfs install
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git checkout paper-r1-results-reproducibility
git rev-parse HEAD
git status --porcelain
```

Record the full hash printed by `git rev-parse HEAD`. The final command must
print nothing before a comparison-grade run.

### 2. Install the locked environment

```bash
uv python install 3.11.15
uv sync --frozen --no-dev
uv lock --check
uv run --frozen python scripts/reproduce.py verify-archive --scope source
```

The launcher fixes the seed, numerical thread count, timezone, locale, and
plotting backend before Python starts.

### 3. Run the paper analyses

Run every subsection below to reproduce the complete Section V result set, or
run only the mapped subsection when checking one paper item. Each fetch command
downloads the required Git LFS inputs without downloading the whole archive.

#### Main configuration and reference-validity analyses

This run regenerates the main configuration search, detection tables,
numerical comparison, analytical cost, reference-validity outputs, and paper
figures. The full search took about 15 hours on the original source machine.

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope core --include-reference
uv run --frozen python scripts/reproduce.py verify-archive \
  --scope core --require-materialized
uv run --frozen python scripts/reproduce.py notebook \
  --profile core --preset full --data-mode real \
  --verify --run-id reviewer-main
```

#### Graph- and ranking-sensitivity analysis

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope sensitivity --include-reference
uv run --frozen python scripts/reproduce.py verify-archive \
  --scope sensitivity --require-materialized
uv run --frozen python scripts/reproduce.py sensitivity \
  --verify --repeat --run-id reviewer-sensitivity
```

#### Recorded benign workload-order analysis

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope intel
uv run --frozen python scripts/reproduce.py verify-archive \
  --scope intel --require-materialized
uv run --frozen python scripts/reproduce.py intel-orders \
  --repeat --run-id reviewer-intel-orders
```

This analysis uses boundaries constructed from preserved recordings; it is not
a continuously measured physical workload switch.

#### Apple limited-observability analysis

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope apple --include-reference
uv run --frozen python scripts/reproduce.py verify-archive \
  --scope apple --require-materialized
uv run --frozen python scripts/reproduce.py notebook \
  --profile apple --preset full --data-mode real \
  --verify --run-id reviewer-apple
```

#### FPGA-targeted RTL synthesis

This requires Vivado 2025.2, SW Build 6299465, its device database and license,
and the XC7A200T target used in the paper.

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope rtl
uv run --frozen python scripts/reproduce_rtl.py \
  --output-root results/reproduced/reviewer-rtl --dry-run
uv run --frozen python scripts/reproduce_rtl.py \
  --output-root results/reproduced/reviewer-rtl
```

Use a new `--run-id`, or a new `--output-root` for FPGA synthesis, for every
attempt. Generated results are isolated under `results/reproduced/`; the
archived references are not overwritten.

### 4. Check the paper results

For `--verify`, inspect:

```text
results/reproduced/<run-id>/archive_comparison.json
```

For `--repeat`, inspect:

```text
results/reproduced/<run-id>-repeat/repeat_comparison.json
```

For FPGA synthesis, inspect:

```text
results/reproduced/reviewer-rtl/comparison_report.json
```

The FPGA comparison must report `status: PASS`.

For the paper claim, inspect only the mapped Section V outputs listed below.
Every paper-facing table and the source data for every paper figure must agree.
The broader archive report can mention optional intermediate outputs; those do
not expand the paper reproducibility target. Any mismatch in a mapped paper
result is a failure.

Numeric tables use the tolerances in
[the result contract](reproducibility/result_contract.json); schemas,
categorical values, and selected configurations are exact. Figures 3-8 must be
generated and nonempty, but their PNG bytes may differ with operating system,
fonts, and renderer when the underlying data agree.

## Results reported in the paper

### Selected CINTAS configurations

These are the selected operating points in Table VI and Fig. 3. All use median
aggregation and `p=0.99`. The figure uses the labels **Cross-validation MCC**
and **selected CINTAS configuration**.

| Setup/event | Features | Block length | Score mixture | Weight | q | MCC | FPR | Area | Idle power |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| A/DROOP | 15/181 | 1000 | 0 | inverse | 15 | 0.992 | 0.78% | 0.083% | 0.060% |
| A/RH | 20/181 | 550 | 1 | uniform | 8 | 0.992 | 0.85% | 0.110% | 0.080% |
| B/DROOP | 15/460 | 200 | 0.50 | inverse | 15 | 0.991 | 0.77% | 0.083% | 0.060% |
| B/SPECTRE | 30/460 | 700 | 0.75 | uniform | 8 | 0.989 | 1.10% | 0.161% | 0.118% |

Across these four cases, ROC-AUC/AUC-PR is 0.999–1.000 and F1 is
0.995–0.996. The same cross-validation results support configuration selection
and reporting, so these values are an empirical configuration comparison, not
an independent test of the complete selection procedure.

### Other reported analyses

| Paper location | Reported result | Evidence status |
|---|---|---|
| Sec. V-B | Across 13 recorded workloads, mean MCC is 0.989, 0.994, 0.991, and 0.990; mean FPR is 1.28%, 0.62%, 0.77%, and 1.28% for A/DROOP, A/RH, B/DROOP, and B/SPECTRE. | Historical archive; regenerate with `reviewer-main`. |
| Table VII, Sec. V-C | Saturating feature budgets are 15, 20, 15, and 5 for A/DROOP, A/RH, B/DROOP, and B/SPECTRE. | Historical archive; regenerate with `reviewer-main`. |
| Fig. 4, Sec. V-D | The stable conditional dependency graph and top-ranked features are rebuilt from the preserved benign telemetry. | Historical archive; regenerate with `reviewer-main`. |
| Sec. V-D | Graph variants give MCC 0.940–0.992, benign FPR 0.77%–1.71%, and feature overlap 37.9%–100%; ranking-term removals give MCC 0.798–0.992, benign FPR 0.77%–1.64%, and overlap 53.8%–100%. | [Clean claim audit](results/notebook_run/graph_sensitivity/graph_sensitivity_claims.json). |
| Table VIII, Sec. V-E | Mean absolute sample-score error ranges from 4.6 × 10⁻⁵ to 0.114; maximum error ranges from 2.6 × 10⁻⁴ to 2.09. | Partial archive; regenerate with `reviewer-main`. |
| Table IX, Sec. V-F | Feature-count reduction is 89.0%–96.7%; analytical area is 0.083%–0.161% and idle power is 0.060%–0.118%. | Historical archive; regenerate with `reviewer-main`. |
| Table X | The CITADEL comparison row is derived from Tables VI and IX; prior-work rows are cited literature values. | Derived cross-check against Tables VI and IX; literature rows are source-attributed constants. |
| Fig. 5 and Table XI, Sec. V-G | The prototype uses 863–907 LUTs, 242–259 flip-flops, 37–38 DSPs, no BRAM, and has estimates of 2.110–2.569 ns WNS, 43.69–44.58 MHz, and 157–158 mW. | Partial archive; reproduce with Vivado. |
| Fig. 6, Sec. V-H | Initial benign FPR is 0.77% for Setup A and 1.73% for Setup B; recalibration gives 1.15% for both, with feature overlap of 76.5% and 66.7%. | Historical archive; regenerate with `reviewer-main`. |
| Fig. 7, Sec. V-I | Mean benign FPR is 0.58% ± 0.82 percentage points for Setup A and 0.83% ± 1.00 for Setup B. | Repeatable runner; no committed comparison bundle yet. |
| Fig. 8, Sec. V-J | Best MCC by Apple stress condition across the evaluated views and configurations is 0.917 CACHE, 0.878 ATOMIC, 0.754 MEMBW, 0.370 BRANCH, and 0.367 TLB. | Historical archive; regenerate with `reviewer-apple`. |

The fixed-point values compare sample scores and do not by themselves establish
identical block decisions. The FPGA study is a maximum-aggregation streaming
prototype, unlike the selected median configurations, and is not a board-level
measurement. Apple views use separate references and feature selection. New
live telemetry is an independent experiment and is not expected to be
byte-identical to the preserved recordings.

For detailed provenance and acceptance criteria, use the
[Reviewer Reproduction Guide](docs/reviewer_reproduction.md).
