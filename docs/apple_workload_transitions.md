# Repeated Rapid Benign Workload Transition Experiment

This experiment measures CITADEL behavior during abrupt benign workload changes on the available Apple platform. It does not test Intel telemetry, firmware transitions, controlled temperature changes, voltage control, or physical aging.

## Preferred Notebook Run

1. Update the environment and open `notebooks/exact_tcad_all_experiments.ipynb` from the repository root.
2. Run the repository import cell, Section 1 reproducibility configuration, and Section 2 integrated utilities.
3. In Section 12, set `RUN_APPLE_TRANSITION_CAMPAIGN = True`.
4. Run the collection cell once. Do not close the computer or allow it to sleep.
5. Return the switch to `False` after collection.
6. Run the analysis cell. It analyzes every complete run and displays the campaign summary and figure.

The default campaign has five independent runs. Each run uses a recorded seed, a different randomized complete workload order in every cycle, two calibration cycles, three evaluation cycles, 60 seconds per workload, and a requested 5 Hz sampling rate. A two minute cool down separates runs. The total is about 108 minutes plus short schema probes and analysis time.

`PY_STATS` allocates 100,000,000 float32 values, approximately 0.37 GiB. `PY_AI` records whether it used MPS, CPU, or the NumPy fallback. `BROWSER` requires working network access for representative activity.

## Command Line Use

A dry run prints every run seed, randomized order, and estimated duration without collecting data:

```text
python3 scripts/run_apple_transition_campaign.py --dry-run
```

The full default campaign is:

```text
python3 scripts/run_apple_transition_campaign.py
```

To analyze the newest complete campaign:

```text
python3 scripts/analyze_apple_transition_campaign.py
```

Every collection is stored without overwriting an earlier run under:

```text
data/telemetry/raw/apple_transition_campaigns/<campaign_id>/runs/<run_id>/
```

The campaign manifest records the seeds, intended settings, return codes, and completion state. Every run manifest records its phase orders, platform, sampling behavior, workload backend, source hashes, and unavailable signals. A run is rejected if a consecutive sample gap exceeds two seconds.

## Frozen Per Run Evaluation

Each run is processed independently to prevent information leakage across runs. The first two complete cycles provide calibration data. The first 50 samples, approximately 10 seconds, of every calibration phase are excluded. The remaining samples define the normalization, stable conditional ranking, eight selected features, score, and threshold. These quantities remain frozen for all three evaluation cycles in that run.

Preprocessing is declared before result inspection:

- Cumulative context switch, interrupt, syscall, and swap input or output counters are divided by elapsed time after differencing.
- Rolling load averages are excluded because they retain prior phase history.
- Absolute memory and swap occupancy, process count, and static frequency limits are excluded because they represent persistent host state or metadata rather than an immediate workload response.
- Nonfinite and constant calibration features are removed.

The generated `transition_preprocessing_audit.csv` records the action and reason for every numeric signal.

The detector uses uniform weights, lambda 0.5, a 50 sample mean decision block, and the 0.99 quantile of calibration block scores as its threshold. A transition window is the first three blocks following a scheduled switch. Stabilization requires three consecutive blocks below the threshold. The comparison rule requires two consecutive threshold exceedances before reporting an alarm.

## Across Run Reporting

The campaign summary preserves every run result and reports the number of runs, mean, sample standard deviation, minimum, maximum, and a 95 percent bootstrap interval for each metric. The publication figure shows individual run values with the mean and sample standard deviation. The bootstrap interval describes uncertainty for this collected run set; it is not a population guarantee.

Primary artifacts are written under:

```text
results/notebook_run/apple_transition_campaigns/<campaign_id>/
```

They include:

```text
all_run_rule_results.csv
all_run_event_results.csv
campaign_metric_summary.csv
all_run_selected_features.csv
campaign_feature_selection_frequency.csv
fig_transition_campaign_variation.png
campaign_paper_ready_result.txt
campaign_analysis_manifest.json
runs/<run_id>/transition_preprocessing_audit.csv
runs/<run_id>/transition_rule_summary.csv
runs/<run_id>/transition_event_summary.csv
runs/<run_id>/run_manifest.json
```

Do not use the generated paper sentence until the campaign and all run manifests report `complete`, the expected Apple platform is recorded, every workload phase is present, and the figure and per run values have been inspected. All phases are benign; an alarm is therefore a false positive, not evidence of a reliability, safety, or security event.
