# Legacy Provenance Audit

This page prevents preserved output from being mistaken for clean, fully linked
archival evidence. It records the manifest state observed at repository snapshot
`b2541355b8e5f4853e63976a05af00b99244bde6`.

The current notebook and launchers repair the producer-side gaps (clean-start
provenance, final post-merge/post-figure hashes, lifecycle invocation, scoped
inputs, repeat comparisons, and strict RTL parsing). Those changes do not alter
the table below: only a clean rerun can replace a historical dirty manifest.

## Existing Run Manifests

| Bundle | Recorded source | Dirty at run | Recorded runtime | Current assessment |
|---|---|---:|---|---|
| Graph/ranking sensitivity | `0e8155e778af425fd7e25280ae9f4d412f53aca7` | No | Python 3.11.15; NumPy 2.1.3; pandas 2.2.3; scikit-learn 1.6.1; SciPy 1.17.1; one thread | Clean archival evidence. `archival_provenance_status` and `claim_status` are both `PASS`; all four baseline validations pass. |
| Standard TCAD DSE | `08cf2368999a9eea3b234a931d899f704a4f0169` | Yes | Python 3.11.15; macOS ARM | Legacy evidence. Its manifest describes the standard RH/SPECTRE run, while the root summary and fold paths now hold later integrated standard+DROOP content. |
| DROOP DSE, `p=0.975` | `08cf2368999a9eea3b234a931d899f704a4f0169` | Yes | Python 3.11.15; macOS ARM | Legacy evidence. Child outputs are present, but exact source state is unidentified. |
| DROOP DSE, `p=0.99` | `08cf2368999a9eea3b234a931d899f704a4f0169` | Yes | Python 3.11.15; macOS ARM | Legacy evidence. Child outputs are present, but exact source state is unidentified. |
| Lifecycle drift | `f030e7ef08b7351bc3bcb6df0b2ccb3266d292f9` | Yes | Python 3.13.5; NumPy 2.3.2; pandas 2.3.1; scikit-learn 1.7.1; macOS ARM | Legacy evidence and a different numerical stack from the current Python 3.11 environment. |
| Apple limited observability | `08cf2368999a9eea3b234a931d899f704a4f0169` | Yes | Python 3.11.15; macOS ARM | Legacy result evidence. The current source registry now pins upstream DICE commit `b5e382e127e5ed3a187f6d328ab95729500ad7ae`; a clean rerun should verify that ref and every archived input hash. |

The TCAD, DROOP, lifecycle, and Apple manifests record older hashes for
`requirements.txt` and `environment.yml` than the files at the audited snapshot.
They also do not hash the notebook source and every controlling config/hardware
input. A new clean run must create a new manifest; editing the legacy manifest
would erase rather than repair provenance.

## What a Replacement Manifest Must Bind

A submission-quality manifest should record all of the following at process
start, before output files are written:

1. Full repository commit and complete `git status --porcelain`; a canonical
   bundle must start clean.
2. SHA-256 for every executed script or notebook cell, resolved configuration,
   hardware-cost input, and telemetry input.
3. Python implementation/version, direct and transitive packages, operating
   system and architecture, NumPy/SciPy build configuration, BLAS backend, and
   effective thread-pool limits.
4. Seed values, `PYTHONHASHSEED` as observed at process start, fold identifiers,
   tie-breaking policy, and output schema/row counts.
5. SHA-256 for every output and a bundle-level link to child manifests when
   multiple runs are merged.
6. Scientific acceptance checks: exact categorical selections and feature sets,
   numerical tolerance checks, and paper-rounded claim checks.

Timestamp, duration, absolute path, host name, and plot-rendering metadata are
volatile provenance. They should not be used as cross-machine equality targets.

## Cross-Machine Acceptance Contract

Use three distinct comparisons:

- **Exact:** source commit, input hashes, configuration, schema, row counts,
  selected case identifiers, selected features, and categorical decisions.
- **Tolerance based:** floating-point scores and metrics. The tolerance must be
  declared before the rerun, and the manuscript-rounded values must agree.
- **Informational only:** wall-clock time, timestamps, host/platform strings, PNG
  and PDF bytes, and new physical telemetry measurements.

Bitwise equality is realistic only within a canonical image on the same
architecture and numerical backend. Fixed seeds and one thread do not by
themselves force the same low-order floating-point bits across BLAS libraries,
CPUs, and operating systems.

## Reproduction-Tool Validation State

The new frozen `uv` environment has been resolved locally under exact CPython
3.11.15 on macOS ARM, with the direct versions in `pyproject.toml`, `uv.lock`,
`requirements.txt`, and `environment.yml` aligned. The deterministic synthetic
CINTAS smoke produced normalized fingerprint
`96aa3d6cc3ca4a18608411f7aa5921fc34eff633a622e460fc15bf62ccdf85bc`
on that host. The CI workflow is designed to compare this check on Ubuntu 24.04
and macOS 14; its definition is not evidence of a passing remote workflow, so
the run attached to the final artifact commit must be inspected. Docker was not
available for a local image build during this audit. No multi-gigabyte full DSE,
Apple, or live hardware campaign was rerun as part of the tooling audit.

## Hardware-Specific Boundary

The existing Vivado logs identify Vivado 2025.2, build 6299465, target
`xc7a200tfbg676-1`, and a 25 ns requested period. Repeating that sweep requires
that tool build, its device database, a valid license, and the identical RTL/Tcl
inputs. Even then, synthesis reports should be checked by parsed numerical
fields rather than report-file hashes.

The current `rtl/cintas/cintas_stream.sv` implements block-maximum aggregation.
The four frozen selected configurations use median aggregation. Until the RTL
implements the selected aggregation or the evidence is explicitly labeled as a
maximum-aggregation proxy, the sweep does not establish bit-exact realization
of those four configurations.
