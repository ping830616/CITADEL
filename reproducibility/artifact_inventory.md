# CITADEL Artifact Inventory

This inventory records the reproduction entry point, data dependency, expected
outputs, and provenance state of each CITADEL evidence bundle. It is an audit of
repository snapshot `b2541355b8e5f4853e63976a05af00b99244bde6`; it does not
upgrade a legacy result merely because the result is present in Git or Git LFS.
The machine-readable counterpart is [`artifact_inventory.json`](artifact_inventory.json).

The reproducibility hardening added after that baseline snapshot does not
rewrite historical evidence. It supplies an exact Python/lockfile environment,
scoped LFS preflight, isolated headless execution, repeat/archive comparison,
an invoked lifecycle stage, post-merge TCAD and post-figure Apple manifests,
four-case q8/q15 golden-vector export, a hashed RTL report manifest, and a
strict Vivado reproduction launcher. A bundle moves out of its historical
status only after a clean new run and its comparison report are archived.

## Evidence Classes

- **Archived-data reanalysis** starts from a fixed telemetry snapshot. A
  successful repeat should preserve row counts, selected configurations and
  selected-feature sets, and reproduce reported numerical values within a
  declared tolerance. Plot files are not expected to be byte-identical across
  operating systems and font stacks.
- **Live collection** launches workloads and collects new measurements on a
  physical host. Seeds and commands can reproduce the protocol, but new raw
  samples are independent observations and are not expected to equal the
  archived measurements.
- **Vivado-only reproduction** requires the disclosed AMD/Xilinx tool release,
  device database, and license. It is separate from Python reanalysis and from
  open-source RTL simulation.

## Status Vocabulary

| Status | Meaning |
|---|---|
| `ARCHIVED_CLEAN_VERIFIED` | A clean-source run, input/output hashes, runtime pins, and a claim-level check are present. |
| `ARCHIVED_LEGACY_DIRTY` | Outputs and a manifest are present, but the manifest records a dirty worktree or otherwise cannot identify the exact source tree. |
| `ARCHIVED_PARTIAL` | Some outputs are present, but a bundle-level manifest or a required functional artifact is absent. |
| `EXPECTED_NOT_ARCHIVED` | Code or a notebook cell describes the experiment, but the expected result bundle is not committed. |
| `PROTOCOL_ONLY` | Collection/analysis code and a protocol are present, but no completed campaign is archived. |

The current reviewer wrapper is `scripts/reproduce.py`. It provides scoped LFS
fetch/preflight commands, isolated headless notebook execution, repeat runs, and
scientific-result comparison through `scripts/verify_reproducibility.py`. The
status column below still describes the preserved evidence at the audited
snapshot; new automation does not retroactively make a dirty legacy manifest
clean.

## Bundle Matrix

| Bundle | Evidence class | Producer / entry point | Archived root | Audit status | Reviewer interpretation |
|---|---|---|---|---|---|
| Processed Intel DDR snapshot | Archived input | External X-OCTANE snapshot identified by `data/external_sources.json`; historical helpers in `TELEMETRY_COLLECTION_SCRIPTS/` | `data/telemetry/processed/ddr_data/` | `ARCHIVED_PARTIAL` | All 78 analysis inputs are tracked, and the external source commit is pinned. The repository does not preserve a per-run acquisition manifest or the unavailable historical event boundaries. Reanalysis should use this snapshot rather than claim an identical recollection. |
| Standard and integrated TCAD DSE | Archived-data reanalysis | Notebook Section 4, `TCAD_PRESET = "full"` | `results/notebook_run/tcad_ablation/` | `ARCHIVED_LEGACY_DIRTY` | The manifest records commit `08cf2368999a9eea3b234a931d899f704a4f0169`, `git_dirty: true`, Python 3.11.15, and the standard RH/SPECTRE branch. The root summary and fold files were later replaced by integrated standard+DROOP tables, so their current content is not the content hashed by that manifest. |
| DROOP adaptive derived data | Archived-data reanalysis | Notebook Section 4 transient-feature generation cell | `results/notebook_run/droop_adaptive_data/` | `ARCHIVED_PARTIAL` | Fifty-two derived BENIGN/DROOP files are tracked, but no derived-data manifest ties them to source file hashes, transformation code, and output hashes as one bundle. |
| DROOP adaptive DSE, `p=0.975` | Archived-data reanalysis | Notebook Section 4 DROOP branch | `results/notebook_run/droop_adaptive_ablation/p0_975/` | `ARCHIVED_LEGACY_DIRTY` | Result tables, causal outputs, resolved config, and a manifest are present. The manifest records commit `08cf236...`, `git_dirty: true`, and Python 3.11.15. |
| DROOP adaptive DSE, `p=0.99` | Archived-data reanalysis | Notebook Section 4 DROOP branch | `results/notebook_run/droop_adaptive_ablation/p0_99/` | `ARCHIVED_LEGACY_DIRTY` | Result tables, causal outputs, resolved config, and a manifest are present. The manifest records commit `08cf236...`, `git_dirty: true`, and Python 3.11.15. |
| Combined DROOP adaptive tables | Archived-data reanalysis | Notebook Section 4 merge after the two quantile runs | `results/notebook_run/droop_adaptive_ablation/` | `ARCHIVED_PARTIAL` | Combined summary, fold, selected-feature, best-setting, and figure outputs are present, but no parent manifest records the two child manifests and merge code. |
| Graph- and ranking-sensitivity study | Archived-data reanalysis | `python scripts/run_graph_sensitivity.py`, or the named notebook launch cell | `results/notebook_run/graph_sensitivity/` | `ARCHIVED_CLEAN_VERIFIED` | The run manifest records clean source commit `0e8155e778af425fd7e25280ae9f4d412f53aca7`, Python 3.11.15, one thread, pinned numerical packages, 144 input records, nine output records, four passing baseline gates, and `claim_status: PASS`. This is the strongest current evidence bundle. |
| Lifecycle drift and recalibration | Archived-data reanalysis | Notebook utility `notebook_run_lifecycle_drift(...)` | `results/notebook_run/lifecycle_drift/` | `ARCHIVED_LEGACY_DIRTY` | Tables, causal outputs, figure, config, and manifest are present. The manifest records commit `f030e7e...`, `git_dirty: true`, Python 3.13.5, NumPy 2.3.2, pandas 2.3.1, and scikit-learn 1.7.1. The audited `b254135` snapshot defined the utility but did not invoke it; the post-audit core profile now invokes it and fails if required lifecycle outputs are absent. |
| Benign workload profiles | Archived-data reanalysis | Notebook cell “Benign workload profiles (Reviewer 1, Comment 6)” | `results/notebook_run/workload_profiles/` | `EXPECTED_NOT_ARCHIVED` | Stored notebook output says the experiment ran, but the result directory, plots, supporting CSVs, and manifest are not committed at this snapshot. |
| Apple limited-observability study | Archived-data reanalysis | Notebook Section 11 | `results/notebook_run/apple_limited_observability/` | `ARCHIVED_LEGACY_DIRTY` | Tables, causal outputs, figures, and manifest are present. The manifest records commit `08cf236...`, `git_dirty: true`, and Python 3.11.15. `data/external_sources.json` now pins upstream DICE commit `b5e382e127e5ed3a187f6d328ab95729500ad7ae`; analysis should verify that ref and the archived Apple CSV hashes. |
| Intel workload-order stress test | Archived-data reanalysis | `uv run --frozen python scripts/reproduce.py intel-orders`; direct analyzer/notebook use is development-only | `results/notebook_run/intel_workload_orders/` | `EXPECTED_NOT_ARCHIVED` | The locked wrapper writes isolated results and a source/input/runtime/manifest receipt, but no full output bundle is committed. The constructed workload boundaries test order/distribution sensitivity, not a continuously measured physical switch transient. |
| EXACT baseline reproduction | Archived-data reanalysis | Notebook utilities `run_ets2026(...)` and `notebook_run_ets2026(...)` | `results/notebook_run/ets_baseline/` | `EXPECTED_NOT_ARCHIVED` | The functions are defined, but the current notebook does not invoke them and no result bundle is committed. Do not cite a CITADEL-internal EXACT reproduction until it is actually run and archived. |
| Paper tables and figures | Derived from archived analysis | Notebook Section 5 and later gallery cells | `results/notebook_run/tcad_ablation/paper_figures/` | `ARCHIVED_PARTIAL` | Multiple gallery tables and figures are present. They have no gallery-level manifest; the final audit now requires the actually generated `gallery_table1_selected_operating_points.csv`. Validate the underlying CSV values rather than PNG byte hashes. |
| Fixed-point golden vectors | Derived from archived analysis | Notebook Section 9 | `results/notebook_run/fpga/` | `ARCHIVED_PARTIAL` | Only `cintas_setupA_q18_golden_vectors.csv` is present. There is no vector-bundle manifest and no complete per-operating-point set of model constants and vectors for all four selected cases. |
| RTL/FPGA resource sweep | Vivado-only reproduction | `scripts/vivado_cintas_synth.tcl`, followed by `scripts/parse_vivado_rtl_sweep.py` | `results/notebook_run/rtl_sweep/` | `ARCHIVED_PARTIAL` | Four Vivado report directories and `rtl_resource_summary.csv` are present, but no sweep manifest hashes the RTL, Tcl, parser, tool build, part database, arguments, and reports. The current RTL aggregates by block maximum, whereas the four frozen paper operating points use median aggregation; treat the reports as starter-datapath resource evidence, not bit-exact implementation of those four configurations. |
| Continuous Intel transition campaign | Live collection | `scripts/run_intel_transition_campaign.py`, then `scripts/analyze_intel_transition_campaign.py` | Raw: `data/telemetry/raw/intel_transition_campaigns/<campaign_id>/`; results: `results/notebook_run/intel_transition_campaigns/<campaign_id>/` | `PROTOCOL_ONLY` | Requires the intended Intel host, pinned PAMPAR and Intel PCM builds, privileges, and a new measurement campaign. No completed campaign is committed. |
| Continuous Apple transition campaign | Live collection | `scripts/run_apple_transition_campaign.py`, then `scripts/analyze_apple_transition_campaign.py` | Raw: `data/telemetry/raw/apple_transition_campaigns/<campaign_id>/`; results: `results/notebook_run/apple_transition_campaigns/<campaign_id>/` | `PROTOCOL_ONLY` | Requires an Apple host and live workload backends. No completed campaign is committed. New readings should be compared statistically, not by file hash. |

## Expected Outputs by Producer

### Notebook Section 4: paper-scale DSE

Standard/integrated outputs:

```text
results/notebook_run/tcad_ablation/
  run_manifest.json
  tcad_config_resolved.json
  tcad_ablation_standard_summary.csv
  tcad_ablation_standard_fold_results.csv
  tcad_ablation_summary.csv
  tcad_ablation_fold_results.csv
  tcad_selected_features.csv
  causal/SETUP_{A,B}_{causal_edges,causal_nodes,feature_ranks}.csv
```

DROOP-adaptive outputs:

```text
results/notebook_run/droop_adaptive_data/*.csv
results/notebook_run/droop_adaptive_ablation/p0_975/
  run_manifest.json
  tcad_config_resolved.json
  tcad_ablation_summary.csv
  tcad_ablation_fold_results.csv
  tcad_selected_features.csv
  causal/*.csv
results/notebook_run/droop_adaptive_ablation/p0_99/
  (same file set)
results/notebook_run/droop_adaptive_ablation/
  droop_adaptive_summary_all_quantiles.csv
  droop_adaptive_fold_results_all_quantiles.csv
  droop_adaptive_selected_features_all_quantiles.csv
  droop_adaptive_best_by_setup.csv
  fig_droop_adaptive_mcc_vs_block_length.png
```

### Focused graph/ranking sensitivity runner

Current computational inputs are the exact standard-DDR and derived-DROOP CSV
inventories plus `configs/graph_sensitivity_feature_universes.json` and the
locked source/environment files. Archived TCAD summaries, ranks, and edges are
historical provenance for freezing that registry; the runner does not read them.

```text
results/notebook_run/graph_sensitivity/
  README.md
  protocol.json
  selected_operating_points.json
  graph_sensitivity_summary.csv
  graph_sensitivity_fold_results.csv
  graph_sensitivity_selected_features.csv
  graph_sensitivity_feature_ranks.csv
  graph_sensitivity_graph_edges.csv
  graph_sensitivity_claims.json
  run_manifest.json
```

### Lifecycle utility

```text
results/notebook_run/lifecycle_drift/
  lifecycle_config_resolved.json
  lifecycle_recalibration_summary.csv
  lifecycle_recalibration_by_scenario.csv
  lifecycle_recalibration_windows.csv
  lifecycle_feature_rank_stability.csv
  lifecycle_causal/*.csv
  figures/fig_lifecycle_recalibration_fpr_tpr.png
  run_manifest.json
```

### Workload profile cell

```text
results/notebook_run/workload_profiles/
  workload_profiles.png
  workload_profiles.pdf
  feature_metadata.csv
  feature_statistics.csv
  domain_variance.csv
  workload_profiles.csv
  input_quality.csv
  workload_rationale.csv
  manifest.json
```

### Apple limited-observability cell

```text
results/notebook_run/apple_limited_observability/
  apple_observability_inventory.csv
  apple_observability_fold_results.csv
  apple_observability_summary.csv
  apple_observability_best_by_scenario.csv
  apple_selected_features.csv
  apple_workload_best_by_observability.csv
  apple_workload_summary.csv
  tier*/causal/*.csv
  paper_figures/*.png
  run_manifest.json
```

### Intel workload-order runner

```text
results/notebook_run/intel_workload_orders/
  intel_workload_order_run_results.csv
  intel_workload_order_block_results.csv
  intel_workload_order_summary.csv
  intel_workload_order_by_workload.csv
  intel_workload_order_selected_features.csv
  intel_workload_order_feature_frequency.csv
  fig_intel_workload_order_variation.png
  intel_workload_order_paper_text.txt
  run_manifest.json
  runs/setup_<A-or-B>_block_<01-through-10>/*
```

### Live campaigns

The live Intel collector writes a campaign manifest and per-run PCM, phase,
invocation, and collection-manifest files. The analyzer writes aggregate rule,
stabilization, feature-selection, parse-audit, figure, paper-text, and analysis
manifest outputs. The live Apple collector writes a campaign manifest and
per-run trace/phase/run-manifest files. Its analyzer writes per-run rule/event
results plus aggregate metric, feature, figure, paper-text, and analysis
manifest outputs. Exact layouts are specified in
[`docs/intel_continuous_workload_transitions.md`](../docs/intel_continuous_workload_transitions.md)
and [`docs/apple_workload_transitions.md`](../docs/apple_workload_transitions.md).

## Known Missing or Unlinked Artifacts at the Audited Snapshot

- The complete `workload_profiles/` result bundle.
- The complete `intel_workload_orders/` result bundle.
- The complete `ets_baseline/` result bundle.
- `results/notebook_run/paper_tbd_replacements.csv`.
- A gallery-level manifest remains desirable; the underlying gallery CSVs are
  nevertheless covered by the archive inventory and scientific comparison contract.
- A clean rerun using the new final integrated-DSE manifest written after the
  standard and DROOP tables are merged.
- A derived-data manifest for `droop_adaptive_data/`.
- A gallery-level manifest for paper figures/tables.
- An archived clean run of the new four-case fixed-point vector/index export,
  plus an automated SystemVerilog equivalence test.
- A new Vivado synthesis rerun (the existing reports now have a checksum
  manifest and strict reproduction launcher, but remain starter-datapath
  evidence).
- Completed continuous Intel or Apple transition campaigns.

The repository-wide `.gitignore` currently ignores `results/`. Existing tracked
artifacts remain tracked, but a newly generated canonical artifact must be added
deliberately; otherwise a clean-looking `git status` is not proof that the new
bundle was archived.
