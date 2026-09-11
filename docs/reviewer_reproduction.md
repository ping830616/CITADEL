# Reviewer Reproduction Guide

This guide tells a reviewer what can be reproduced from archived telemetry,
what requires a new physical experiment, and what requires Vivado. It should be
read with the bundle-level
[`artifact_inventory.md`](../reproducibility/artifact_inventory.md) and the
[`legacy_provenance.md`](../reproducibility/legacy_provenance.md) audit.

## Reproduction Claims Used Here

“Reproduce” does not mean the same thing for every CITADEL result:

1. **Archived-data reanalysis:** run the same code and configuration on the same
   tracked telemetry. Require exact inputs and categorical selections, then
   compare floating-point metrics within a declared tolerance and at manuscript
   precision.
2. **Live hardware collection:** repeat the disclosed protocol on a qualifying
   machine. The new trace is an independent measurement; it should not be
   byte-identical or numerically identical to the archived trace.
3. **Vivado reproduction:** repeat synthesis with the disclosed Vivado release,
   FPGA part, timing constraint, Tcl, and RTL. Compare parsed resource/timing
   fields, not report bytes.

At audited snapshot `b2541355b8e5f4853e63976a05af00b99244bde6`, the
graph/ranking-sensitivity bundle is the only result bundle that records clean
source provenance and a passing claim-level self-check. The TCAD, DROOP,
lifecycle, and Apple limited-observability outputs remain useful legacy evidence,
but their manifests record dirty source trees. Workload-profile, Intel
workload-order, EXACT-baseline, and continuous-transition bundles are not
archived at that snapshot. These states are enumerated rather than hidden in
[`artifact_inventory.json`](../reproducibility/artifact_inventory.json).

## 1. Start From an Immutable Checkout

Replace `<artifact-commit-or-tag>` with the full commit or signed release tag
identified by the manuscript. Do not use the moving `main` branch as the
experiment identifier.

```bash
export GIT_LFS_SKIP_SMUDGE=1
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git checkout <artifact-commit-or-tag>
git rev-parse HEAD
git status --porcelain
git lfs install
```

`git status --porcelain` must print nothing before a canonical run. Preserve the
reported commit together with the result manifest.

The repository uses Git LFS for telemetry and large CSV results. Pull only the
profile needed for the selected experiment, as shown below. A file beginning
with `version https://git-lfs.github.com/spec/v1` is an LFS pointer, not the
telemetry or result content.

## 2. Create the Python Environment

The canonical local environment is the checked-in `uv.lock` under exact CPython
3.11.15:

```bash
uv python install 3.11.15
uv sync --frozen --no-dev
```

Run Python entry points below as `uv run --frozen python ...` when using this
environment. The lock has been resolved locally on macOS ARM with all direct
versions matching. The cross-platform CI workflow is designed to repeat the
deterministic smoke check on Ubuntu 24.04 and macOS 14; inspect the workflow run
for the artifact commit rather than treating the workflow definition as a
completed test.

Conda is an alternative with the same direct package and exact Python pins:

```bash
conda env create -f environment.yml
conda activate citadel-slm
```

For an existing environment:

```bash
conda env update -f environment.yml --prune
conda activate citadel-slm
```

Set process-level determinism controls **before** starting Python or Jupyter:

```bash
export PYTHONHASHSEED=123
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export MPLBACKEND=Agg
```

Setting `PYTHONHASHSEED` inside an already running notebook does not change the
interpreter's hash randomization. For a canonical comparison, also record
`python --version`, `conda list`, operating system/architecture, and the NumPy
and SciPy build/BLAS information.

### Automated preflight and isolated outputs

The preferred reviewer interface is `scripts/reproduce.py`. It starts Python
children with the seed, one-thread limits, UTC timezone, fixed locale, and an
isolated output root under `results/reproduced/<run-id>/`. It does not overwrite
the archived reference result tree.

For example, prepare the graph-sensitivity profile with:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope sensitivity
uv run --frozen python scripts/reproduce.py preflight --scope sensitivity
```

When the release contains `reproducibility/archive_manifest.json`, verify
tracked source/input/output hashes (LFS pointer metadata are sufficient for an
inventory-only check; add `--require-materialized` before an actual run):

```bash
uv run --frozen python scripts/reproduce.py verify-archive --scope sensitivity
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope sensitivity --include-reference
uv run --frozen python scripts/reproduce.py verify-archive --scope sensitivity --require-materialized
```

The `core` profile invokes lifecycle analysis and its final artifact checks;
`--verify` therefore fails if the lifecycle tables or any other required
scientific output are absent. At this audited baseline, candidate-only workload,
paper-text, and new four-case golden-vector outputs make a successful core
comparison `PASS_WITH_UNVERIFIED` with `PARTIAL` coverage. Notebook completion
or that partial status is not evidence that every result agrees; full
equivalence requires `status: PASS` and `verification_coverage: COMPLETE` after
those references are archived.

## 3. Reproduce the Clean Graph/Ranking-Sensitivity Evidence

This focused runner evaluates the four frozen operating points; it does not
rerun or reselect the design-space optimum.

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope sensitivity --include-reference
uv run --frozen python scripts/reproduce.py sensitivity --verify --run-id reviewer-sensitivity
```

The direct generation-and-comparison equivalent is:

```bash
git lfs pull --include='data/telemetry/processed/ddr_data/*.csv,results/notebook_run/droop_adaptive_data/*.csv,results/notebook_run/graph_sensitivity/*.csv,results/notebook_run/graph_sensitivity/*.json' --exclude=''
uv run --frozen python scripts/run_graph_sensitivity.py \
  --output-root results/reproduced/direct-sensitivity/notebook_run/graph_sensitivity \
  --droop-data-root results/notebook_run/droop_adaptive_data
uv run --frozen python scripts/verify_reproducibility.py compare \
  --profile sensitivity \
  --reference-root results/notebook_run \
  --candidate-root results/reproduced/direct-sensitivity/notebook_run \
  --report results/reproduced/direct-sensitivity/archive_comparison.json
```

The archived reference is `results/notebook_run/graph_sensitivity/`. The wrapper
writes the independent candidate under
`results/reproduced/reviewer-sensitivity/notebook_run/graph_sensitivity/`, so it
does not replace the archive. A direct run targeting the canonical archive
refuses to replace it from a dirty checkout. Inspect the candidate's status
fields after completion:

```bash
SENSITIVITY_RESULT_ROOT=results/reproduced/reviewer-sensitivity/notebook_run/graph_sensitivity
jq '{repository_commit, git_dirty_at_start, archival_provenance_status, claim_status, draft_claims_match_at_reported_precision}' "$SENSITIVITY_RESULT_ROOT/run_manifest.json"
jq '{status, ranges, draft_largest_reduction_checks}' "$SENSITIVITY_RESULT_ROOT/graph_sensitivity_claims.json"
```

Accept the result only when `git_dirty_at_start` is `false`,
`archival_provenance_status` is `PASS`, `claim_status` is `PASS`, and every
baseline validation in the manifest has `all_checks_pass: true`. The claim
audit names the exact case and variant supplying each reported range endpoint.

## 4. Reanalyze the Main Archived DDR/Apple Data

### Main TCAD and DROOP design-space exploration

Materialize the computational inputs and archived comparison references. The
wrapper can then execute an isolated headless profile:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope core --include-reference
uv run --frozen python scripts/reproduce.py preflight \
  --scope core --include-reference
uv run --frozen python scripts/reproduce.py notebook \
  --profile core --preset full --data-mode real \
  --verify --run-id reviewer-core
```

For an interactive inspection, set the controls before Jupyter starts:

```bash
export CITADEL_SEED=123
export CITADEL_THREADS=1
export CITADEL_PROFILE=core
export CITADEL_DATA_MODE=real
export CITADEL_TCAD_PRESET=full
export CITADEL_RESULTS_ROOT=results/reproduced/reviewer-interactive/notebook_run
export CITADEL_RUN_INTEL_WORKLOAD_ORDERS=0
export CITADEL_RUN_APPLE_OBSERVABILITY=0
export CITADEL_RUN_LIFECYCLE=1
uv run --frozen python -m jupyter lab notebooks/exact_tcad_all_experiments.ipynb
```

Run Sections 1 through 4 in order. The `full` preset is required for the paper
operating points; `smoke` and `balanced` are development checks and cannot
reconstruct the complete selected-setting table. The preserved full run log
records roughly 15 hours for the standard plus DROOP branches on its source
machine, so reviewers should plan accordingly.

Section 4 first writes a standard RH/SPECTRE manifest, runs the two
DROOP-adaptive quantiles, merges their tables, and then replaces the interim
root manifest with a final integrated manifest whose hashes describe the final
files. The preserved pre-remediation root manifest in the audited snapshot did
not provide that link; do not mistake it for a new clean run.

### Lifecycle drift and recalibration

Lifecycle analysis is enabled by default for `CITADEL_PROFILE=core` and `all`
and is invoked from Section 4 after the integrated DSE manifest is finalized.
For a targeted interactive invocation after Sections 1 and 2, use:

```python
lifecycle_artifacts = notebook_run_lifecycle_drift(
    data_root=DATA_ROOT,
    out_root=LIFECYCLE_OUT,
    cfg=notebook_lifecycle_config(),
    seed=SEED,
    threads=THREADS,
)
```

Set `CITADEL_RUN_LIFECYCLE=0` only for a development run. Do not infer a new
lifecycle run from the presence of older files: the legacy manifest was
produced under Python 3.13.5 with a different numerical stack and records a
dirty worktree.

### Benign workload profiles

The dedicated profile fetches and validates only the 26 benign DDR inputs,
writes to a fresh isolated result root, and compares two independent runs:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope workload
uv run --frozen python scripts/reproduce.py verify-archive \
  --scope workload --require-materialized
uv run --frozen python scripts/reproduce.py notebook \
  --profile workload --preset smoke --data-mode real \
  --repeat --run-id reviewer-workload
```

The two output bundles are under `results/reproduced/reviewer-workload*/`.
Require `status: PASS` and `verification_coverage: COMPLETE` in the repeat
comparison. `--verify` is deliberately rejected because this audited snapshot
does not contain a canonical workload-profile reference.

For interactive inspection, export a fresh path such as
`CITADEL_RESULTS_ROOT=results/reproduced/reviewer-workload-interactive/notebook_run`
before starting Jupyter, then run only the self-contained cell named **Benign
workload profiles (Reviewer 1, Comment 6)**. The cell refuses a canonical or
existing output directory, so stale evidence cannot be mixed into the run.

### Intel workload-order stress test

This analysis uses only the 26 preserved benign DDR files:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope intel
uv run --frozen python scripts/reproduce.py verify-archive \
  --scope intel --require-materialized
uv run --frozen python scripts/reproduce.py intel-orders --run-id reviewer-intel-orders
```

The full default is both setups, ten nonoverlapping recording-block replicates,
and 10,000 bootstrap resamples. A one-replicate command is only a development
check. The output root is
`results/reproduced/reviewer-intel-orders/notebook_run/intel_workload_orders/`;
no full bundle is committed at the audited snapshot. The constructed boundaries
test workload-order and distribution sensitivity, not physical transition
latency. The adjacent `run_receipt.json` records the clean commit, hashes of all
26 inputs plus the wrapper, analyzer, notebook, external-source registry, and
lock/environment files, exact Python and package versions, platform,
NumPy/BLAS/threadpool configuration, the isolated validation-free utility-loader
mode, and the analyzer-manifest path and hash.

For an independent same-host repeatability check, add `--repeat`; the second
full run is written to `results/reproduced/reviewer-intel-orders-repeat/` and
compared under the repository contract. `--verify` instead compares with a
committed `results/notebook_run/intel_workload_orders/` reference and therefore
fails with an explicit missing-archive error at this snapshot. It becomes the
reviewer command once such a reference bundle is committed.

### Apple limited-observability analysis

Materialize the archived Apple CSV snapshot:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope apple --include-reference
uv run --frozen python scripts/reproduce.py preflight --scope apple
uv run --frozen python scripts/reproduce.py notebook \
  --profile apple --preset full --data-mode real \
  --verify --run-id reviewer-apple
```

Run the setup/utilities and Section 11. The external-source registry pins DICE
commit `b5e382e127e5ed3a187f6d328ab95729500ad7ae`; confirm that exact ref and the
tracked Apple CSV hashes before reanalysis. The existing Apple result manifest
records a dirty source tree and must be replaced, not edited, by a clean rerun
manifest.

### EXACT baseline utility

The notebook defines `notebook_run_exact_ets2026(...)`, but does not invoke it
and does not archive `results/notebook_run/ets_baseline/`. If a manuscript claim
depends on a CITADEL-internal EXACT baseline reproduction, run the utility from
a clean source snapshot, archive its complete result/manifest bundle, and add a
claim-level comparison. Until then, cite upstream EXACT lineage rather than an
unarchived local reproduction.

## 5. Regenerate Paper Figures and Tables

Run the notebook gallery cells only after their source result tables have been
reproduced. The principal output root is:

```text
results/notebook_run/tcad_ablation/paper_figures/
```

Validate each plotted source CSV, selected operating point, label, and
manuscript-rounded value. Do not require PNG/PDF SHA-256 equality across servers:
fonts, renderers, metadata, and compression can change bytes without changing
the scientific content. At the audited snapshot the gallery has no bundle-level
manifest and `tcad_detection_quality_paper_selected.csv` is absent.

## 6. Repeat Optional Live Hardware Campaigns

### Continuous Intel workload transitions

This requires the intended Setup A or Setup B Intel machine, exact PAMPAR and
Intel PCM revisions, and the needed PCM privileges. Inspect the plan first:

```bash
python3 scripts/run_intel_transition_campaign.py \
  --setup A \
  --pampar-root /absolute/path/to/PAMPAR \
  --pcm-bin /absolute/path/to/pcm/build/bin/pcm \
  --dry-run
```

After validating the paths and plan, remove `--dry-run`. Repeat separately with
`--setup B`. Analyze a completed campaign with:

```bash
python3 scripts/analyze_intel_transition_campaign.py \
  --campaign-dir data/telemetry/raw/intel_transition_campaigns/<campaign_id> \
  --output-root results/reproduced/intel-transition-analysis-<attempt>
```

Use a new `--output-root` for every analysis attempt. The analyzer rejects an
existing campaign-specific output directory so stale and regenerated evidence
cannot be mixed.

Accept a campaign only after every collection manifest reports completion, host
identity/tool revisions match the intended setup, phase/timestamp audits pass,
and individual run values have been inspected. No completed Intel transition
campaign is committed at the audited snapshot.

### Continuous Apple workload transitions

Inspect the randomized five-run plan without collecting:

```bash
python3 scripts/run_apple_transition_campaign.py --dry-run
```

Run the live campaign on the evaluated Apple host, then analyze it:

```bash
python3 scripts/run_apple_transition_campaign.py
python3 scripts/analyze_apple_transition_campaign.py
```

Record the Apple model/OS, sampling behavior, workload backend, browser network
state, phase completeness, and maximum sample gap. No completed Apple transition
campaign is committed at the audited snapshot.

For both live protocols, reproducibility means matching protocol, provenance,
and statistical analysis. Different hosts or collection times are not expected
to generate identical telemetry.

## 7. Repeat the Vivado Resource Sweep

The archived logs identify Vivado 2025.2 build 6299465, target
`xc7a200tfbg676-1`, and a 25 ns requested period. The strict launcher checks
that tool/build, executes all four configurations sequentially in a temporary
workspace, preserves each output in a fresh directory, parses the reports, and
compares the scientific fields with the archived summary:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope rtl
uv run --frozen python scripts/reproduce_rtl.py --dry-run
uv run --frozen python scripts/reproduce_rtl.py \
  --output-root results/reproduced/reviewer-rtl
```

Retain `reproduction_plan.json`, `run_manifest.json`, and
`comparison_report.json`. The manifest binds tool/part expectations and SHA-256
for RTL, Tcl, parser, reports, and parsed output. Raw report/checkpoint bytes are
archival evidence, not cross-host equality targets.

Important interpretation limit: the current RTL implements block-maximum
aggregation, while all four frozen selected configurations use median
aggregation. The existing reports therefore support a starter-datapath resource
estimate, not bit-exact functional realization of the selected configurations.
A functional deployment claim additionally needs the selected aggregation,
per-case constants/vectors, a SystemVerilog testbench, and an automated
software-versus-RTL comparison.

## 8. Acceptance Checklist

For every archived-data bundle used in a paper table or claim, retain this
checklist with the reviewer record:

- [ ] Full immutable source commit/tag recorded; worktree clean at process start.
- [ ] Every required Git LFS input is materialized and its content hash matches.
- [ ] Executed notebook cell/script, resolved config, and auxiliary hardware
      inputs are hashed.
- [ ] Python, complete dependency set, platform/architecture, BLAS backend,
      process-start hash seed, and thread limits are recorded.
- [ ] Output schema and row counts match.
- [ ] Selected cases, feature sets, fold assignments, and categorical decisions
      match exactly.
- [ ] Comparison reports say `status: PASS` and
      `verification_coverage: COMPLETE`; any `unverified_outputs` are excluded
      from the supported claim or supplied with an archived reference.
- [ ] Floating-point comparisons use predeclared `rtol`/`atol`; all
      manuscript-rounded values match.
- [ ] Each manuscript endpoint maps to a concrete output row.
- [ ] Volatile metadata and plot bytes are excluded from scientific equality.
- [ ] A merged bundle links every child manifest and the merge code.
- [ ] Newly generated files under ignored `results/` were deliberately added to
      the archive.

For live campaigns, replace numerical equality with protocol/host/tool
provenance and a predeclared statistical comparison. For Vivado, additionally
record the exact Vivado build, device database, part, constraints, and parsed
report fields.

## 9. What the Current Archive Does and Does Not Establish

The current archive directly supports inspection of the main TCAD, DROOP,
lifecycle, Apple limited-observability, and RTL result files. It provides strong,
clean, claim-linked reproduction evidence for the graph/ranking sensitivity
ranges. It does not yet provide clean source lineage for all older notebook
bundles, a committed Intel workload-order or workload-profile result bundle, an
invoked/archived EXACT baseline bundle, completed continuous-transition
campaigns, or a median-aggregation bit-exact RTL implementation.

These limitations do not assert that an analysis was not performed. They define
what an independent reviewer can verify from the archived repository alone.
