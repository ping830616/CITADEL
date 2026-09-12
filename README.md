# CITADEL

[![Reproducibility CI](https://github.com/ping830616/CITADEL/actions/workflows/ci.yml/badge.svg)](https://github.com/ping830616/CITADEL/actions/workflows/ci.yml)

This repository contains the code, preserved telemetry, locked environment,
and compact evidence for the experimental results in the CITADEL paper.

## Reviewer status

Every enumerated Section V table, figure, and numerical claim has a compact,
hashed bundle and an automated manuscript-value audit. This establishes result
coverage and traceability. It does **not** by itself mean that every long
experiment was freshly rerun on a second machine.

The immutable reviewer snapshot is `paper-r1-reviewer-evidence-v3`. At this
snapshot:

- the graph/ranking study has clean archived evidence;
- Figure 7 has two clean, unchanged runs and a complete repeat comparison;
- the main and Apple bundles are traceable historical references with clean
  reproduction commands;
- the RTL bundle is a checked reanalysis of archived Vivado reports; a new
  Vivado run is still required to call it fresh synthesis evidence.

The audit reports these two conclusions separately so a passing integrity
check cannot be mistaken for proof that every experiment was freshly rerun.

## Step-by-step reproduction

### 1. Check out the exact snapshot

Install Git, Git LFS, and [uv](https://docs.astral.sh/uv/), then run:

```bash
git lfs install
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git checkout paper-r1-reviewer-evidence-v3
git status --porcelain
```

The final command must print nothing before a comparison-grade run.

### 2. Install the locked environment

```bash
uv python install 3.11.15
uv sync --frozen --no-dev
uv lock --check
uv run --frozen python scripts/reproduce.py verify-archive --scope source
```

The launcher fixes the seed, numerical thread count, timezone, locale, and
plotting backend before analysis starts.

### 3. Audit all paper evidence first

This quick command needs no telemetry download:

```bash
uv run --frozen python scripts/reproduce.py verify-paper --scope all
```

Accept the compact evidence only when `coverage_status` and
`traceability_status` are both `PASS`. Read `fresh_clean_rerun_status`
separately; it is intentionally stricter.

### 4. Regenerate the result family you want to check

Main configurations, Tables VI–X, and Figures 3, 4, and 6 (about 15 hours on
the original source machine):

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope core
uv run --frozen python scripts/reproduce.py preflight --scope core
uv run --frozen python scripts/reproduce.py notebook \
  --profile core --preset full --data-mode real \
  --verify --run-id reviewer-main
```

Graph- and ranking-sensitivity results:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope sensitivity
uv run --frozen python scripts/reproduce.py preflight --scope sensitivity
uv run --frozen python scripts/reproduce.py sensitivity \
  --verify --repeat --run-id reviewer-sensitivity
```

Figure 7 recorded benign workload-order analysis:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope intel
uv run --frozen python scripts/reproduce.py preflight --scope intel
uv run --frozen python scripts/reproduce.py intel-orders \
  --verify --repeat --run-id reviewer-intel-orders
```

Apple limited-observability results:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope apple
uv run --frozen python scripts/reproduce.py preflight --scope apple
uv run --frozen python scripts/reproduce.py notebook \
  --profile apple --preset full --data-mode real \
  --verify --run-id reviewer-apple
```

Figure 5 and Table XI require Vivado 2025.2, SW Build 6299465, its device
database and license, and the XC7A200T target used in the paper:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope rtl
uv run --frozen python scripts/reproduce_rtl.py \
  --output-root results/reproduced/reviewer-rtl --dry-run
uv run --frozen python scripts/reproduce_rtl.py \
  --output-root results/reproduced/reviewer-rtl
```

Always choose a new `--run-id` or RTL `--output-root`. Runs are isolated under
`results/reproduced/` and never overwrite the committed reference evidence.

### 5. Read the comparison reports

| Run | Required report |
|---|---|
| Main or Apple | `results/reproduced/<run-id>/paper_result_comparison.json` |
| Repeated main or Apple | `results/reproduced/<run-id>-repeat/paper_result_repeat_comparison.json` |
| Sensitivity | `results/reproduced/<run-id>/paper_result_comparison.json` |
| Repeated sensitivity | `results/reproduced/<run-id>-repeat/repeat_comparison.json` |
| Figure 7 | `results/reproduced/<run-id>/figure7_archive_comparison.json` and `figure7_claim_verification.json` |
| Repeated Figure 7 | `results/reproduced/<run-id>-repeat/repeat_comparison.json` |
| RTL | `results/reproduced/reviewer-rtl/comparison_report.json` |

A comparison-grade report must have `status: PASS` and
`verification_coverage: COMPLETE` where that field is present.

## Results and evidence locations

| Paper location | Reported result | Compact evidence |
|---|---|---|
| Table VI, Fig. 3 | Selected configurations have MCC 0.989–0.992 and FPR 0.77%–1.10%; Fig. 3 uses “Cross-validation MCC” and “selected CINTAS configuration.” | [`reproducibility/paper_results/core/`](reproducibility/paper_results/core/) |
| Sec. V-B | Across 13 workloads, mean MCC is 0.989, 0.994, 0.991, and 0.990; mean FPR is 1.28%, 0.62%, 0.77%, and 1.28%. | [`reproducibility/paper_results/core/`](reproducibility/paper_results/core/) |
| Table VII | Saturating feature budgets are 15, 20, 15, and 5. | [`reproducibility/paper_results/core/`](reproducibility/paper_results/core/) |
| Fig. 4, Sec. V-D | Stable graph/rank sources plus graph and ranking sensitivity ranges. | [`core`](reproducibility/paper_results/core/) and [`sensitivity`](reproducibility/paper_results/sensitivity/) |
| Table VIII | Mean absolute score error is 4.6×10⁻⁵–0.114; maximum error is 2.6×10⁻⁴–2.09. | [`reproducibility/paper_results/core/`](reproducibility/paper_results/core/) |
| Tables IX–X | Feature reduction is 89.0%–96.7%; analytical area is 0.083%–0.161% and idle power is 0.060%–0.118%. | [`reproducibility/paper_results/core/`](reproducibility/paper_results/core/) |
| Fig. 5, Table XI | 863–907 LUTs, 242–259 flip-flops, 37–38 DSPs, no BRAM, 2.110–2.569 ns WNS, 43.69–44.58 MHz, and 157–158 mW. | [`reproducibility/paper_results/rtl/`](reproducibility/paper_results/rtl/) |
| Fig. 6, Sec. V-H | Initial FPR is 0.77% and 1.73%; recalibration gives 1.15% for both, with 76.5% and 66.7% feature overlap. | [`reproducibility/paper_results/core/`](reproducibility/paper_results/core/) |
| Fig. 7, Sec. V-I | Mean benign FPR is 0.58% ± 0.82 percentage points and 0.83% ± 1.00; boundary means are 0.26% and 0.51%. | [`reproducibility/paper_results/intel/`](reproducibility/paper_results/intel/) |
| Fig. 8, Sec. V-J | Best MCC is 0.917 CACHE, 0.878 ATOMIC, 0.754 MEMBW, 0.370 BRANCH, and 0.367 TLB. | [`reproducibility/paper_results/apple/`](reproducibility/paper_results/apple/) |

Table X’s CITADEL row is derived from Tables VI and IX. The prior-work rows are
literature values, not new CITADEL experiments. Rendered figure bytes may vary
with fonts and operating system. Figure checks cover source tables,
configuration, labels, and declared layout/main/legend assets; they do not
claim pixel-level or visual-semantic equivalence.

See the [reviewer reproduction guide](docs/reviewer_reproduction.md) for the
acceptance contract and provenance details.
