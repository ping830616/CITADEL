# Rapid Benign Workload Transition Experiment

This supplemental experiment supports the response to Reviewer 1, Comment 9. It measures CITADEL behavior during abrupt benign workload changes on the available Apple platform. It does not test Intel telemetry, firmware transitions, controlled temperature changes, voltage control, or physical aging.

## Run From The Notebook

1. Update the environment and open `notebooks/exact_tcad_all_experiments.ipynb` from the repository root.
2. Run the notebook setup and integrated utility cells.
3. The full Apple design space sweep in Section 11 is not required for this experiment.
4. In Section 12, set `RUN_APPLE_TRANSITION_COLLECTION = True`.
5. Run the collection cell once. The default protocol records three cycles of `BROWSER`, `PY_AI`, `PY_STATS`, and `VIDEO_SW`, with 60 seconds per workload and a requested 5 Hz sampling rate.
6. Return the switch to `False` so the workload sequence is not launched again accidentally.
7. Run the analysis cell. It automatically selects the newest trace whose collection manifest has status `complete`.

The default collection lasts about 12 minutes plus a five second schema probe. `PY_STATS` allocates 100,000,000 float32 values, approximately 0.37 GiB. `PY_AI` uses Torch when it is installed and records whether it used MPS, CPU, or the NumPy fallback. `BROWSER` follows the preserved workload definition and therefore requires working network access for representative activity.

## Optional Command Line Preflight

The notebook calls the following collector. A dry run checks the platform, dependencies, planned phase order, duration, AI backend, and expected `PY_STATS` allocation without launching workloads or writing a trace.

```text
python scripts/collect_apple_workload_transitions.py --dry-run
```

The full default command is:

```text
python scripts/collect_apple_workload_transitions.py
```

Each real run creates a new timestamped directory under:

```text
data/telemetry/raw/apple_transitions/<run_id>/
```

It contains the continuous telemetry stream, scheduled phase boundaries, the retained Tier 0 schema, and a collection manifest. Interrupted, failed, or timing invalid runs remain available for diagnosis but are not selected by the notebook analysis. By default, the collector rejects a run when any consecutive sample starts are separated by more than two seconds; this catches system sleep or a prolonged process suspension.

## Frozen Evaluation Protocol

The analysis uses only preserved stable nominal Tier 0 traces for calibration and threshold selection. Within each workload trace, the first 70 percent is used for benign calibration and the remaining 30 percent for threshold validation. Monotonic host counters are converted to rates before fitting. The stable conditional telemetry ranking selects eight features from calibration data only.

The frozen CINTAS configuration uses uniform weights, lambda 0.5, a 50 sample mean decision block, and the 0.99 quantile of stable validation block scores as its threshold. No parameter is updated during the transition trace. A transition window is the first three decision blocks following each scheduled switch. Score stabilization requires three consecutive blocks below the frozen threshold. The reference is marked stale when the observed benign false positive rate exceeds eta, where eta is 0.01. The comparison rule requires two consecutive threshold exceedances before reporting an alarm.

These values are explicit notebook parameters. If any value is changed, report the change and use the generated manifest to identify the exact configuration.

## Required Result Checks

Do not copy the generated sentence into the rebuttal or manuscript until all of the following are true:

- `collection_manifest.json` reports `status: complete` and the expected Apple hardware.
- The manifest reports the intended workload order, three cycles, 60 second dwell time, and 5 Hz requested sampling.
- The AI backend and any unavailable telemetry fields are disclosed.
- `transition_rule_summary.csv` contains both `current` and `persistence` rows.
- `transition_event_summary.csv` contains one row per scheduled switch.
- The score figure shows all workload boundaries and no unexplained collection gaps.
- `run_manifest.json` identifies the trace, stable nominal inputs, selected features, threshold, configuration, commit, and hashes.

The analysis writes:

```text
results/notebook_run/apple_workload_transitions/transition_rule_summary.csv
results/notebook_run/apple_workload_transitions/transition_event_summary.csv
results/notebook_run/apple_workload_transitions/transition_block_scores.csv
results/notebook_run/apple_workload_transitions/stable_validation_block_scores.csv
results/notebook_run/apple_workload_transitions/transition_selected_features.csv
results/notebook_run/apple_workload_transitions/fig_apple_workload_transition_scores.png
results/notebook_run/apple_workload_transitions/paper_ready_result.txt
results/notebook_run/apple_workload_transitions/run_manifest.json
```

All recorded phases are benign workload labels. A threshold exceedance is therefore counted as a false positive; it is not evidence of a reliability, safety, or security event.
