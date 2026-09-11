# Cross-Machine Reproducibility

The supported target is scientific equivalence from an immutable CITADEL
checkout and the archived inputs. This means exact configuration, schemas,
categorical decisions, selected configurations, and feature sets, plus numeric
agreement within the predeclared tolerance. It does not mean byte-identical
plots, timestamps, Vivado reports, or newly collected hardware telemetry.

For the complete reviewer procedure and the evidence status of every bundle,
use the [reviewer reproduction guide](reviewer_reproduction.md) and
[artifact inventory](../reproducibility/artifact_inventory.md).

## Canonical Environment

CITADEL pins CPython 3.11.15, every direct dependency, and the complete
cross-platform dependency graph in `uv.lock`:

```bash
uv python install 3.11.15
uv sync --frozen
uv lock --check
```

The alternative Conda specification has the same Python and direct package
pins:

```bash
conda env create -f environment.yml
conda activate citadel-slm
```

Use `uv run --frozen python ...` for the commands below. The launcher starts
child processes with seed 123, one numerical thread, UTC, a fixed locale, and a
noninteractive plotting backend. Manifests record the source state, environment
files, package versions, NumPy build/BLAS information, active thread pools,
configuration, and input/output hashes.

## Immutable Checkout and Scoped LFS

```bash
export GIT_LFS_SKIP_SMUDGE=1
git clone https://github.com/ping830616/CITADEL.git
cd CITADEL
git checkout <full-artifact-commit-or-tag>
git lfs install
git status --porcelain
```

The last command must be empty before a comparison-grade run. Fetch only the
profile being reproduced:

```bash
uv run --frozen python scripts/reproduce.py fetch-lfs --scope workload
uv run --frozen python scripts/reproduce.py fetch-lfs --scope core
uv run --frozen python scripts/reproduce.py fetch-lfs --scope sensitivity
uv run --frozen python scripts/reproduce.py fetch-lfs --scope apple
uv run --frozen python scripts/reproduce.py fetch-lfs --scope intel
uv run --frozen python scripts/reproduce.py fetch-lfs --scope rtl
```

These commands fetch computational inputs only. Before a command using
`--verify`, repeat that profile's fetch with `--include-reference` so the
archived comparison outputs are materialized without making ordinary
generation depend on its predecessor.

The preflight rejects pointer stubs instead of passing them to pandas. Check the
repository inventory before execution:

```bash
uv run --frozen python scripts/reproduce.py verify-archive --scope source
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope core --include-reference
uv run --frozen python scripts/reproduce.py verify-archive \
  --scope core --require-materialized
```

## Isolated, Headless Runs

First run the no-download synthetic repeat check:

```bash
uv run --frozen python scripts/reproduce.py notebook \
  --profile smoke --preset smoke --data-mode sample \
  --repeat --run-id reviewer-smoke
```

Then run the needed archived-data profile:

```bash
# Benign workload characterization from exactly 26 inputs. This snapshot has
# no workload-profile reference, so use a repeat comparison, not --verify.
uv run --frozen python scripts/reproduce.py notebook \
  --profile workload --preset smoke --data-mode real \
  --repeat --run-id reviewer-workload

# Full TCAD, DROOP, workload profile, lifecycle, sensitivity, and fixed-point outputs
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope core --include-reference
uv run --frozen python scripts/reproduce.py notebook \
  --profile core --preset full --data-mode real \
  --verify --run-id reviewer-core

# Focused graph/ranking sensitivity without the full DSE
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope sensitivity --include-reference
uv run --frozen python scripts/reproduce.py sensitivity \
  --verify --run-id reviewer-sensitivity

# Apple limited-observability reanalysis
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope apple --include-reference
uv run --frozen python scripts/reproduce.py notebook \
  --profile apple --preset full --data-mode real \
  --verify --run-id reviewer-apple

# Intel workload-order analysis from preserved benign recordings
uv run --frozen python scripts/reproduce.py intel-orders \
  --run-id reviewer-intel-orders
```

Runs are written under `results/reproduced/<run-id>/`; they never overwrite the
archived reference. Use `--repeat` to compare two independent executions of the
same profile. A full core run is a long job, so the focused sensitivity and
synthetic smoke profiles are useful gates before scheduling it.

For the Intel command, `--repeat` performs two full, isolated workload-order
runs and compares their CSVs by scientific row identity with `rtol=1e-9` and
`atol=5e-11`; categorical values, selected features, alarms, workload orders,
and schemas remain exact. Each run receipt binds the clean source commit and
hashes of the 26 benign DDR inputs, analyzer, notebook, environment files, and
analyzer manifest to the locked Python/package versions and
NumPy/BLAS/threadpool runtime. It also hashes the wrapper and external-source
registry and records that notebook utilities were loaded in an isolated
validation-free smoke/sample mode; the actual analysis still validates and
hashes exactly the 26 benign inputs. The optional `--verify` flag uses the same
contract against a committed Intel
archive. It fails clearly when, as in the current audited snapshot, that
archive is intentionally absent.

## Comparison Contract

`reproducibility/result_contract.json` and
`scripts/verify_reproducibility.py` implement the acceptance rules:

- exact CSV/JSON structure, strings, booleans, case IDs, and selected features;
- exact row order for positional tables, with order-independent matching only
  where the contract declares scientific identity keys or unordered feature sets;
- numeric values compared with default `rtol=1e-10` and `atol=1e-12`;
- explicit failure for missing results or reference/candidate LFS pointers;
- volatile host, timestamp, absolute-path, duration, and rendering metadata
  excluded from scientific equivalence.

An optional candidate-only output is listed as `SKIPPED_NO_REFERENCE` under
`unverified_outputs`, changes `status` to `PASS_WITH_UNVERIFIED`, and changes
`verification_coverage` to `PARTIAL`; it is not silently treated as equivalent.
Full claim-level equivalence therefore requires both `status: PASS` and
`verification_coverage: COMPLETE`. `PASS_WITH_UNVERIFIED` returns exit code zero
so optional-output workflows can finish, but those listed outputs remain outside
the verified claim. Notebook completion
alone is not an equivalence result. PNG/PDF files may be inspected visually,
but their bytes are not portable across font and renderer stacks.

`--allow-runtime-mismatch` is a development escape hatch. When supplied to the
notebook wrapper, it disables both the outer version rejection and the matching
in-notebook strict-runtime gate; the resulting preflight receipt still records
the observed mismatch and must not be presented as a canonical run.

## Docker

The image pins the Linux CPython base by digest and installs from `uv.lock`:

```bash
docker build --platform linux/amd64 -t citadel-repro .
docker run --rm --platform linux/amd64 \
  -v "$PWD:/workspace/CITADEL" -w /workspace/CITADEL \
  citadel-repro python scripts/reproduce.py notebook \
  --profile smoke --preset smoke --data-mode sample \
  --repeat --run-id docker-smoke
```

Mounting the immutable checkout makes its Git state and selected LFS objects
visible inside the image. The CI workflow runs the locked numerical smoke on
Ubuntu and macOS and compares their normalized scientific fingerprint.

## Vivado and Live Hardware

Vivado reproduction requires version 2025.2, SW Build 6299465, target
`xc7a200tfbg676-1`, its device database/license, and the checked-in RTL/Tcl:

```bash
uv run --frozen python scripts/reproduce_rtl.py --dry-run
uv run --frozen python scripts/reproduce_rtl.py \
  --output-root results/reproduced/reviewer-rtl
```

The launcher compares parsed configuration/resource fields exactly and timing
or power numerically. Raw report and checkpoint bytes are not equality targets.
The present RTL is a block-maximum starter datapath; the paper points use median
aggregation, so this evidence must not be described as a bit-exact realization
of all four configurations.

Intel and Apple collection campaigns are different: a seed reproduces the
schedule, not the physical samples. Retain the exact host, OS/CPU, privileges,
tool and workload revisions/hashes, phase events, sampling audit, and statistical
acceptance result. Follow
[the Intel transition runbook](intel_continuous_workload_transitions.md) or
[the Apple transition runbook](apple_workload_transitions.md).

## Legacy Results

Older TCAD, DROOP, lifecycle, Apple, and figure bundles include dirty, stale, or
partial provenance. Automation does not retroactively make those manifests
clean. The [legacy provenance audit](../reproducibility/legacy_provenance.md)
identifies the limitation of each bundle; a replacement must come from a clean
run with a passing comparison report.
