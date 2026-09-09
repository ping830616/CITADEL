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

## Interpretation Boundary

The workload files were originally collected separately. The repository does not preserve event identifiers that verify the historical trial boundaries, and it does not contain a continuous Intel trace spanning live workload switches. The analysis therefore calls the ten nonoverlapping units **recording block replicates**, not independent physical trials.

The constructed boundaries test sensitivity to abrupt changes in the workload distribution and to randomized workload order. They do not reproduce the short physical transient of a continuously observed switch. A claim about switch latency or a hardware transition window requires a new continuous Intel collection.

## Preprocessing

Intel PCM columns are retained as interval metrics. Temperature and voltage columns are converted to first differences within each original workload recording before any randomized sequence is assembled. This prevents the analysis from creating a false jump by subtracting absolute values across separately collected files. Nonfinite values are imputed from calibration means, and nonfinite or constant calibration columns are removed. Each run writes a preprocessing audit.

## Notebook Run

Open `notebooks/exact_tcad_all_experiments.ipynb`. In a fresh kernel, run the repository import cell, Section 1, Section 2, and Section 12. The Section 12 code cell calls:

```text
python3 scripts/analyze_intel_workload_orders.py
```

Command line options can reduce the run for a development check:

```text
python3 scripts/analyze_intel_workload_orders.py --setups A --replicates 1 --bootstrap-resamples 1000 --output /tmp/citadel_intel_order_check
```

Do not use a one block development check as a paper result.

## Outputs

The full run writes these artifacts under `results/notebook_run/intel_workload_orders/`:

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
