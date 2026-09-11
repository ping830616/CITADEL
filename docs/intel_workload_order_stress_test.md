# Intel Benign Workload Order Stress Test

This experiment evaluates whether a CITADEL reference calibrated on benign Intel telemetry remains compatible with held out benign workload orders. It uses the preserved Setup A DDR4 and Setup B DDR5 PAMPAR recordings in `data/telemetry/processed/ddr_data/`.

## What The Experiment Supports

For each setup, the analysis uses ten nonoverlapping 1000 row recording blocks from each of the 13 benign workload files. Every recording block is divided into five disjoint 200 sample segments. Two randomized workload cycles provide calibration data and three separately randomized cycles provide evaluation data. Feature selection, normalization, scoring, and the decision threshold are learned from the two calibration cycles and then frozen.

The test reports benign false positive rates for:

- all held out decision blocks;
- the first decision block after each constructed workload boundary;
- later decision blocks within each workload phase; and
- the current decision rule and a two block persistence rule.

Every recording block is reported separately. The summary includes the mean, sample standard deviation, minimum, maximum, and a 95 percent bootstrap interval across the ten blocks for each setup.

The 1 percent threshold uses the finite sample corrected upper calibration rank with strict score exceedance. With 104 calibration blocks, this selects the maximum calibration score rather than a linearly interpolated 0.99 sample quantile, whose effective exceedance probability is too coarse at this sample size. Because 156 evaluation blocks still provide a coarse false positive estimate, reference staleness is not declared whenever the observed rate merely exceeds 1 percent. The analysis uses a one sided exact binomial test against the 1 percent target at alpha 0.05 and retains the unadjusted comparison as an audit column. This separates statistically supported incompatibility from ordinary finite sample variation under the Bernoulli model. The per replicate false positive rates and their mean and sample standard deviation remain the primary evidence because consecutive decision blocks may not be statistically independent. The persistence rule is a sensitivity comparison and should not replace the deployed rule without a separate anomaly detection analysis.

## Interpretation Boundary

The workload files were originally collected separately. The repository does not preserve event identifiers that verify the historical trial boundaries, and it does not contain a continuous Intel trace spanning live workload switches. The analysis therefore calls the ten nonoverlapping units **recording block replicates**, not independent physical trials.

The constructed boundaries test sensitivity to abrupt changes in the workload distribution and to randomized workload order. They do not reproduce the short physical transient of a continuously observed switch. A claim about switch latency or a hardware transition window requires a new continuous Intel collection.

Use `docs/intel_continuous_workload_transitions.md` to collect the required independent physical runs on Intel hardware.

## Preprocessing

Intel PCM columns are retained as interval metrics. Temperature and voltage columns are converted to first differences within each original workload recording before any randomized sequence is assembled. This prevents the analysis from creating a false jump by subtracting absolute values across separately collected files. Nonfinite values are imputed from calibration means, and nonfinite or constant calibration columns are removed. Each run writes a preprocessing audit.

## Reproducible Run

Use the locked wrapper for reviewer or archival evidence:

```text
uv run --frozen python scripts/reproduce.py fetch-lfs --scope intel
uv run --frozen python scripts/reproduce.py intel-orders --run-id reviewer-intel-orders
```

The wrapper requires a clean checkout and the exact locked runtime by default,
writes only beneath a new `results/reproduced/<run-id>/` root, and records a
receipt containing the commit, 26 input hashes, source and environment-file
hashes, exact package versions, platform, NumPy/BLAS/threadpool details, and
analyzer-manifest hash.
The analyzer loads only shared notebook definitions under an isolated
validation-free smoke/sample environment, then restores the caller environment.
The workload-order analysis itself separately requires, validates, and hashes
the exact 26 benign Intel recordings; non-benign DDR LFS objects are not needed.
Add `--repeat` to execute two isolated full runs and compare all scientific
tables. Use `--verify` only when the repository snapshot contains a committed
`results/notebook_run/intel_workload_orders/` reference; the current audited
snapshot does not.

To compare results copied back from two different servers, keep each complete
`notebook_run/` directory and run:

```text
uv run --frozen python scripts/verify_reproducibility.py compare \
  --reference-root results/reproduced/server-a/notebook_run \
  --candidate-root results/reproduced/server-b/notebook_run \
  --profile intel-orders \
  --report results/reproduced/intel_server_comparison.json
```

The comparison is row-order independent through declared scientific identity
keys. Numeric cells use `rtol=1e-9` and `atol=5e-11`; schemas, workload orders,
alarm decisions, and selected-feature membership must agree exactly.

## Notebook Run

Open `notebooks/exact_tcad_all_experiments.ipynb`. In a fresh kernel, run the repository import cell, Section 1, Section 2, and Section 12. The Section 12 code cell calls the development analyzer with the notebook's configured output root:

```text
python3 scripts/analyze_intel_workload_orders.py --output <RESULTS_ROOT>/intel_workload_orders
```

Direct analyzer invocation is for development only. It requires an explicit,
previously nonexistent output directory and refuses reuse so that stale files
cannot be mixed with a new run. Command line options can reduce the run for a
development check:

```text
python3 scripts/analyze_intel_workload_orders.py --setups A --replicates 1 --bootstrap-resamples 1000 --output /tmp/citadel_intel_order_check
```

Do not use a one block development check as a paper result.

## Outputs

The wrapper writes these artifacts under
`results/reproduced/<run-id>/notebook_run/intel_workload_orders/`. A reviewed
bundle may later be promoted to the canonical
`results/notebook_run/intel_workload_orders/` archive:

```text
intel_workload_order_run_results.csv
intel_workload_order_block_results.csv
intel_workload_order_summary.csv
intel_workload_order_by_workload.csv
intel_workload_order_selected_features.csv
intel_workload_order_feature_frequency.csv
fig_intel_workload_order_variation.png
intel_workload_order_paper_text.txt
run_manifest.json
runs/setup_<A-or-B>_block_<01-through-10>/
```

Before reporting the result, confirm that the manifest is complete, `git_dirty` is false for the submitted commit, both setups have ten recording block replicates, and all individual values and the figure have been inspected.
