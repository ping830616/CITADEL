# CITADEL

**CITADEL**—Conditional Interdependence in Telemetry Analytics and Drift-Aware
Edge Learning—is a reproducible research artifact for hardware-aware CINTAS
telemetry analysis. It includes the Intel DDR and Apple telemetry snapshots,
the primary notebook, graph/ranking sensitivity analysis, lifecycle analysis,
fixed-point and RTL evidence, and protocols for new hardware measurements.

The supported end-to-end entry point is
[`notebooks/exact_tcad_all_experiments.ipynb`](notebooks/exact_tcad_all_experiments.ipynb).
For reviewer runs, use [`scripts/reproduce.py`](scripts/reproduce.py): it checks
the source/runtime/data state, fixes seeds and numerical thread counts before
Python starts, executes selected notebook sections headlessly, and writes to an
isolated directory instead of overwriting the archive.

## Reviewer Quick Start

### 1. Check out an immutable source snapshot

Replace `<artifact-commit-or-tag>` with the full commit or release tag cited by
the manuscript. Do not use a moving branch name as the experiment identifier.
Skipping LFS smudge avoids downloading the complete multi-gigabyte archive
before the desired experiment is known.

```bash
export GIT_LFS_SKIP_SMUDGE=1
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git checkout <artifact-commit-or-tag>
git lfs install
git rev-parse HEAD
git status --porcelain
```

The final command must print nothing for a comparison-grade run.

### 2. Install the exact environment

The canonical environment is CPython **3.11.15** plus the complete dependency
resolution in `uv.lock`:

```bash
uv python install 3.11.15
uv sync --frozen
uv lock --check
```

`requirements.txt` and `environment.yml` retain the same direct pins for users
who cannot use `uv`, but `uv sync --frozen` is the primary reviewer path. The
launcher also sets seed 123, one numerical thread, UTC, a fixed locale, and the
noninteractive Matplotlib backend before starting the notebook kernel.

### 3. Run the lightweight deterministic check

This executes two isolated runs on bundled synthetic data and compares them. It
is a quick code/environment check; it does not reproduce a paper-scale result.

```bash
uv run --frozen python scripts/reproduce.py notebook \
  --profile smoke --preset smoke --data-mode sample \
  --repeat --run-id reviewer-smoke
```

The two runs are stored under `results/reproduced/reviewer-smoke/` and
`results/reproduced/reviewer-smoke-repeat/`, with the comparison report beside
the second run.

## Reproduce Archived-Data Results

Fetch only the Git LFS objects required by the selected experiment. The wrapper
fails closed if an input remains an LFS pointer, the Python/package pins do not
match, real data are unavailable, or the checkout is dirty.
By default `fetch-lfs` downloads computational inputs only. Add
`--include-reference` when the subsequent command uses `--verify`, so archived
comparison outputs are materialized as well.

### Benign workload profiles

This focused profile consumes exactly the 26 benign DDR recordings and can be
repeated without downloading anomaly or legacy result bundles:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope workload
uv run --frozen python scripts/reproduce.py verify-archive \
  --scope workload --require-materialized
uv run --frozen python scripts/reproduce.py notebook \
  --profile workload --preset smoke --data-mode real \
  --repeat --run-id reviewer-workload
```

The audited snapshot has no canonical workload-profile result bundle, so
`--verify` is deliberately rejected for this profile. The repeat comparison
must report `status: PASS` and `verification_coverage: COMPLETE`.

### Full TCAD/DROOP/lifecycle core

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope core --include-reference
uv run --frozen python scripts/reproduce.py verify-archive \
  --scope core --require-materialized
uv run --frozen python scripts/reproduce.py notebook \
  --profile core --preset full --data-mode real \
  --verify --run-id reviewer-core
```

The `full` preset is required to reconstruct the paper operating-point search;
`smoke` and `balanced` are development grids. The archived source-machine log
for the standard plus DROOP branches was approximately 15 hours, so a full run
should be scheduled as a long job. Add `--repeat` only when resources permit a
second full execution.

At the audited baseline, workload-profile, paper-text replacement, and new
four-case golden-vector outputs have no canonical reference. A core comparison
that otherwise agrees therefore reports `PASS_WITH_UNVERIFIED`/`PARTIAL`, not
full equivalence; each listed candidate-only output must be archived and then
rechecked before claiming `PASS`/`COMPLETE` for every core result.

### Focused graph/ranking sensitivity

This re-evaluates the four frozen paper operating points without repeating the
full design-space search:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope sensitivity --include-reference
uv run --frozen python scripts/reproduce.py verify-archive \
  --scope sensitivity --require-materialized
uv run --frozen python scripts/reproduce.py sensitivity \
  --verify --run-id reviewer-sensitivity
```

See [Graph and ranking sensitivity evidence](docs/graph_ranking_sensitivity.md)
for the one-at-a-time protocol and claim-to-row mapping.

### Apple limited-observability analysis

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope apple --include-reference
uv run --frozen python scripts/reproduce.py verify-archive \
  --scope apple --require-materialized
uv run --frozen python scripts/reproduce.py notebook \
  --profile apple --preset full --data-mode real \
  --verify --run-id reviewer-apple
```

The external-source registry pins the Apple snapshot to DICE commit
`b5e382e127e5ed3a187f6d328ab95729500ad7ae`; the archive manifest additionally
binds the tracked CSV content hashes.

### Intel workload-order stress test

This is an archived-data analysis of the preserved benign DDR recordings, not
a measurement of a continuously sampled physical transition:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope intel
uv run --frozen python scripts/reproduce.py verify-archive \
  --scope intel --require-materialized
uv run --frozen python scripts/reproduce.py intel-orders \
  --run-id reviewer-intel-orders
```

The command uses both setups, ten nonoverlapping recording-block replicates,
two calibration cycles, three held-out evaluation cycles, and 10,000 bootstrap
resamples. It writes a run receipt containing the clean source commit, all 26
input hashes, hashes of the launcher, analyzer, notebook, external-source
registry, and environment files, locked Python/package versions, platform and
NumPy/BLAS/threadpool details, the validation-free notebook utility-loader mode,
and the analyzer-manifest hash. Add `--repeat` to run the full protocol
twice in separate directories and compare every scientific CSV under the
declared tolerance contract. `--verify` compares against
`results/notebook_run/intel_workload_orders/` when that archival bundle is
present; the current audited snapshot deliberately reports that full bundle as
not archived. See the [Intel workload-order protocol](docs/intel_workload_order_stress_test.md).

### Archive integrity without running an experiment

The checked-in archive inventory covers ordinary Git files and Git LFS object
identities. Pointer metadata are enough for an inventory check; actual analysis
requires materialized inputs.

```bash
uv run --frozen python scripts/reproduce.py verify-archive --scope source
uv run --frozen python scripts/reproduce.py verify-archive --scope all
```

After fetching a profile, add `--require-materialized` for that scope. Available
scopes are `source`, `workload`, `core`, `sensitivity`, `apple`, `intel`, `rtl`,
and `all`.

## What “the Same Result” Means

[`reproducibility/result_contract.json`](reproducibility/result_contract.json)
defines scientific equivalence. Result comparison requires exact schemas,
categorical values, selected configurations, and nonnumeric fields. Row order
is exact for positional tables; rules with declared identity keys permit only
serialization reordering, and explicitly declared feature-list columns are
compared as unordered sets.
Numeric CSV cells use declared tolerances (by default `rtol=1e-10` and
`atol=1e-12`) because low-order floating-point bits can vary across CPU, BLAS,
and operating-system implementations. Manuscript-rounded values should agree.
When an optional candidate output has no reference counterpart, the report
lists it under `unverified_outputs` with `SKIPPED_NO_REFERENCE` and sets
`status` to `PASS_WITH_UNVERIFIED` and `verification_coverage` to `PARTIAL`; it
is never silently counted as verified. That status keeps a zero process exit
code for optional-output workflows, but it does not establish full equivalence.

PNG/PDF bytes, timestamps, absolute paths, host strings, run durations, and raw
Vivado report bytes are not cross-platform equality targets. Plot renderers,
fonts, compression, and tool session metadata can change those bytes while the
underlying tables and parsed metrics remain equivalent.

Generated runs live under `results/reproduced/<run-id>/`. Each receipt records
the source commit, runtime audit, input preflight, notebook hash, selected cells,
output root, and completion state. Comparison reports contain an explicit
`PASS`, `PASS_WITH_UNVERIFIED`, or `FAIL` plus `COMPLETE` or `PARTIAL`
verification coverage; notebook completion alone is not evidence of agreement.

## Reproduce the Vivado Resource Sweep

Vivado reproduction is separate from Python reanalysis. It requires **Vivado
2025.2, SW Build 6299465**, the matching device database and license, target
`xc7a200tfbg676-1`, and the checked-in RTL/Tcl inputs. Inspect the exact plan
first, then run all four configurations into a fresh directory:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope rtl
uv run --frozen python scripts/reproduce_rtl.py --dry-run
uv run --frozen python scripts/reproduce_rtl.py \
  --output-root results/reproduced/reviewer-rtl
```

The RTL launcher refuses a different Vivado release/build, parses the new
reports, and compares exact configuration/resource fields plus tolerance-based
timing and power fields with the archived summary. The image-independent Python
parser is [`scripts/parse_vivado_rtl_sweep.py`](scripts/parse_vivado_rtl_sweep.py).

The current RTL uses block-maximum aggregation, whereas the frozen paper
operating points use median aggregation. Accordingly, this sweep is
starter-datapath resource evidence, not a claim of bit-exact implementation of
all selected configurations. The Vivado launcher and full Docker image have not
been claimed as locally executed by the portability audit; reviewers should
retain their generated plan, manifest, comparison report, and CI evidence.

## Repeat Live Hardware Collection

Live collection is a protocol replication, not archived-data equality. New
measurements on different hosts or at different times are independent samples
and should be evaluated with the documented quality gates and statistical
comparisons.

- Intel continuous transitions require the intended Setup A or B server,
  pinned PAMPAR and Intel PCM builds, PCM privileges, and the commands in the
  [Intel transition runbook](docs/intel_continuous_workload_transitions.md).
- Apple continuous transitions require an evaluated Apple host and the workload
  backends described in the
  [Apple transition runbook](docs/apple_workload_transitions.md).
- Original DDR acquisition context, labels, and known historical limits are in
  [Telemetry collection](docs/telemetry_collection.md) and
  [Anomaly provenance and labels](docs/anomaly_provenance.md).

No completed continuous-transition campaign is represented as an archived
cross-machine-identical result.

## Optional Container

The pinned Docker definition provides a Linux CPython 3.11.15 environment. The
repository is mounted so Git provenance and the selected LFS objects remain
visible to the launcher:

```bash
docker build --platform linux/amd64 -t citadel-repro .
docker run --rm --platform linux/amd64 \
  -v "$PWD:/workspace/CITADEL" -w /workspace/CITADEL \
  citadel-repro python scripts/reproduce.py notebook \
  --profile smoke --preset smoke --data-mode sample \
  --repeat --run-id docker-smoke
```

This is a reproducible recipe, not a statement that a Docker build or a full
paper run was completed during the repository portability audit. Use the CI run
attached to the cited artifact commit as the execution record.

## Evidence Status and Known Limits

Automation cannot retroactively repair provenance. Some preserved TCAD, DROOP,
lifecycle, Apple, figure, fixed-point, and RTL outputs are valuable evidence but
have dirty, stale, partial, or missing legacy manifests. The graph/ranking
sensitivity bundle is the strongest clean claim-linked archived bundle. The
repository now discloses these states so a reviewer can distinguish a verified
archive, a clean new rerun, an unarchived expected output, and a hardware-only
protocol.

- [Reviewer reproduction guide](docs/reviewer_reproduction.md): detailed
  commands, acceptance checks, and interpretation boundaries
- [Artifact inventory](reproducibility/artifact_inventory.md): bundle-by-bundle
  producer, inputs, expected outputs, and audit status
- [Legacy provenance audit](reproducibility/legacy_provenance.md): recorded
  commits, dirty states, stale links, and replacement-manifest requirements
- [Machine-readable inventory](reproducibility/artifact_inventory.json): status
  data suitable for automated review

Do not describe a legacy bundle as newly reproduced until its clean rerun and
comparison report pass. No multi-gigabyte full core run, Apple run, live
hardware campaign, or Vivado sweep is claimed to have been executed as part of
the portability audit.

## Repository Map

- `notebooks/`: primary experiment notebook and paper-result gallery
- `scripts/`: deterministic launcher, scientific verifier, focused analyses,
  hardware collectors, and Vivado tooling
- `reproducibility/`: checksum inventory, result contract, artifact audit, and
  legacy-provenance disclosure
- `configs/`: paper and development experiment configurations
- `data/`: pinned external-source registry and Git LFS telemetry snapshots
- `results/`: archived evidence; new reviewer runs use `results/reproduced/`
- `rtl/cintas/`: CINTAS SystemVerilog starter datapath
- `docs/`: detailed experiment, hardware, and interpretation runbooks

## Detailed Guides

- [Reviewer reproduction](docs/reviewer_reproduction.md)
- [End-to-end result methodology](docs/tcad_end_to_end_result_methodology.md)
- [Requirements traceability](docs/tcad_requirements_traceability.md)
- [ASU/Vivado server runbook](docs/asu_server_runbook.md)
- [RTL validation plan](docs/rtl_plan.md)
- [EXACT-to-CITADEL extension](docs/exact_to_citadel_extension.md)

## Relationship to EXACT

CITADEL starts from the portable EXACT codebase and adds stable conditional
telemetry-graph learning, hardware-aware design-space exploration, fixed-point
sensitivity, hardware-cost modeling, lifecycle drift checking, RTL/FPGA
evidence, and auditable result manifests. In the manuscript, describe the EXACT
result as an **EXACT baseline reproduction inside CITADEL** only after that
internal bundle has been run and archived; otherwise cite the pinned upstream
lineage and state the boundary explicitly.
