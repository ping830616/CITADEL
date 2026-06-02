# DICE ITC Data Generation (macOS)

DICE provides an end-to-end pipeline for generating the three-tier telemetry dataset used by the DICE draft and notebook:

- `Tier-0`: unprivileged operating-system telemetry collected through `psutil`
- `Tier-1-alt` (recommended on Apple Silicon): `macmon` telemetry with automatic `powermetrics` fallback when collection fails at runtime
- `Tier-1` (legacy): direct `powermetrics` telemetry
- `Tier-2`: profiler-derived runtime evidence collected through `xcrun xctrace` and parsed into case-aligned CSV files

The repository now supports the public Apple Silicon collection procedure directly from Python. A fresh full collection produces raw artifacts, processed CSVs, schemas, manifests, metadata, and logs. The released `dataset/ITC_M2Pro_DATA/` folder is a stripped processed snapshot of that fuller collection tree.

## Start Here

1. Read the dataset narrative and assumptions: [docs/data-description.md](docs/data-description.md)
2. Check the current release status and known platform limits: [docs/current-dataset-status.md](docs/current-dataset-status.md)
3. Review machine-specific constraints and portability notes: [docs/hardware-compatibility.md](docs/hardware-compatibility.md)
4. Follow the practical collection runbook: [docs/end-to-end.md](docs/end-to-end.md)
5. Review the collection methodology used for the ITC dataset: [docs/ITC_COLLECTION_METHODOLOGY.md](docs/ITC_COLLECTION_METHODOLOGY.md)
6. Use the feature references if you need harmonized column descriptions: [docs/feature-dictionary.md](docs/feature-dictionary.md) and [docs/dataset-feature-map-clean-tier1-consistent.md](docs/dataset-feature-map-clean-tier1-consistent.md)
7. For crash-aware recollection and early-warning manifests: [docs/crash-evidence.md](docs/crash-evidence.md)
8. For safe user-space crash experiments on a daily laptop: [docs/controlled-crash-harness.md](docs/controlled-crash-harness.md)
9. For workload-matched crash studies across the original four workloads: [docs/workload-matched-crash-matrix.md](docs/workload-matched-crash-matrix.md)

## Dataset Release

This repository includes the released processed snapshot:

- `dataset/ITC_M2Pro_DATA/`
- coverage report: `dataset/ITC_M2Pro_DATA/no_nan_report.json`

That folder is not a full raw collection tree. It contains the processed tier outputs used by the released experiments. A fresh collection run writes additional raw artifacts, logs, manifests, schemas, and metadata under the output root.

## Quick Start

All commands below assume your working directory is `DICE/"data generation"`.

```bash
cd DICE/"data generation"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional dependency for the `PY_AI` workload:

```bash
pip install torch
```

## Collection Profiles

### Recommended Apple Silicon Profile

`generate_dataset.py` now defaults to:

```bash
python generate_dataset.py --phase recommended --duration_s 1000 --out_dir ./data
```

This profile runs:

- `Tier-0`
- `Tier-1-alt`
- `Tier-2`

It is the closest public match to the procedure behind the released `ITC_M2Pro_DATA` snapshot. It requires:

- macOS
- `powermetrics`
- `macmon`
- Xcode tooling with a working `xcrun xctrace`

### Portable Profile

If you want the repo to collect the best supported data on the current machine, use:

```bash
python generate_dataset.py --phase portable --duration_s 1000 --out_dir ./data
```

Portable mode behaves as follows:

- always runs `Tier-0`
- prefers `Tier-1-alt` when `macmon` is available
- falls back to legacy `Tier-1` when `powermetrics` is available but `macmon` is not
- runs `Tier-2` only when `xctrace` is available and licensed
- skips unsupported tiers cleanly with an explicit message

This makes the workflow portable across different hosts, but it does not guarantee identical schemas or identical tier availability on every machine.

### Legacy Compatibility Profiles

- `--phase both` = `tier0 + tier1`
- `--phase all` = `tier0 + tier1 + tier2`

These legacy modes are still available for compatibility, but they do not match the current Apple Silicon release profile because they use legacy `Tier-1` instead of `Tier-1-alt`.

## Practical Apple Silicon Workflow

### 1. Check the required tools

```bash
macmon --help
powermetrics --help
xcrun xctrace version
```

### 2. Choose an output folder

```bash
OUT="$PWD/data"
mkdir -p "$OUT"
```

### 3. Run the recommended public collection path

```bash
python generate_dataset.py --phase recommended --duration_s 1000 --out_dir "$OUT" --tier1_alt_bin macmon --tier2_template "Time Profiler"
```

To capture reproducible crash evidence during recollection, add:

```bash
python generate_dataset.py \
  --phase recommended \
  --duration_s 1000 \
  --out_dir "$OUT" \
  --tier1_alt_bin macmon \
  --tier2_template "Time Profiler" \
  --capture_crash_evidence \
  --crash_log_grace_s 60
```

This writes `crash_evidence/crash_events.csv` plus per-case copied diagnostic reports and filtered `log show` windows.
After `early_warning_crash_alignment.csv` has been exported, you can also generate draft-ready crash evidence cards with `python ../tools/generate_crash_evidence_cards.py ...` as documented in [docs/crash-evidence.md](docs/crash-evidence.md).

If you want **real crash artifacts** without risking a full-machine crash on your laptop, use the dedicated crash harness:

```bash
python generate_crash_harness_dataset.py \
  --phase recommended \
  --duration_s 300 \
  --out_dir ./data_crash_harness \
  --tier1_alt_bin macmon \
  --tier2_template "Time Profiler" \
  --capture_crash_evidence \
  --capture_crash_screenshot
```

That path is terminal-first. The notebook is used later for analysis.

If you want the same crash-aware workflow extended across the original four workloads and five anomaly families, use the workload-matched crash matrix:

```bash
python generate_workload_matched_crash_dataset.py \
  --phase recommended \
  --duration_s 240 \
  --out_dir ./dataset/ITC_M2Pro_DATA/workload_crash_pilots/data_workload_crash_matrix \
  --schedule_profile staggered \
  --tier1_alt_bin macmon \
  --tier2_template "Time Profiler" \
  --capture_crash_evidence \
  --capture_crash_screenshot \
  --wrapper_gui
```

That path creates one `NOMINAL` case plus `*_CONTROL` and `*_ABORT` variants for each selected anomaly family under each original workload. `--schedule_profile staggered` gives each workload a different anomaly-onset/crash target so the warning and lead-time results are less synchronized across workloads. By default, this keeps the crash pilots under `dataset/ITC_M2Pro_DATA/workload_crash_pilots/` so they stay next to the main ITC dataset without mixing with the released anomaly bundle. Start smaller with `--workloads` and `--stressors` if you want a pilot run first.

These crash-pilot folders are still large and may include copied crash evidence, screenshots, logs, and reruns. The current GitHub repository tracks the four one-workload pilot roots through Git LFS. Normal goal: a plain `git clone` should give you the whole DICE repo on your laptop. If the crash-pilot payload does not materialize correctly, repair just that part afterward with Git LFS or a known-good local copy.

If a plain clone leaves `workload_crash_pilots/.../crash_events.csv`, copied diagnostic reports, or per-case crash logs incomplete, run:

```bash
git lfs install
git lfs pull --include="data generation/dataset/ITC_M2Pro_DATA/workload_crash_pilots/**"
```

If the payload is still incomplete afterward, point the notebook at a local materialized `workload_crash_pilots/` tree instead.

The lightweight manifest entry points remain `dataset/ITC_M2Pro_DATA/workload_crash_pilots/README.md` and `dataset/ITC_M2Pro_DATA/workload_crash_pilots/pilot_manifest.csv`. Those files document the exact `BROWSER/BRANCH`, `PY_AI/CACHE`, `PY_STATS/ATOMIC`, and `VIDEO_SW/MEMBW` pilot commands even when the full LFS payload is not present locally.

Quick check:

```bash
PILOT_CSV="dataset/ITC_M2Pro_DATA/workload_crash_pilots/data_workload_crash_pilot_real_browser_branch/crash_evidence/crash_events.csv"
sed -n '1,3p' "$PILOT_CSV"
```

If the file starts with `version https://git-lfs.github.com/spec/v1`, you only have the pointer stub and the crash-pilot notebook sections will not be able to parse the pilot cases yet.

If the pilot payload still does not materialize, copy it from a known-good local source:

```bash
rsync -a "/absolute/path/to/materialized/workload_crash_pilots/" \
  "$PWD/data generation/dataset/ITC_M2Pro_DATA/workload_crash_pilots/"
```

If you only want a lightweight released-results clone, you can start with:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/ping830616/DICE.git
```

After collection, you can either run:

```bash
cd DICE
python tools/train_eval_dice_pipeline.py \
  --root "data generation/data_crash_harness" \
  --feature_profile mixed \
  --protocol global \
  --out_dir "data generation/data_crash_harness/results_dice_crash_harness_mixed"
```

or open `dice_results_analysis.ipynb` and run `8F. Controlled Crash-Harness Analysis` for the crash-focused notebook summary, early-warning alignment table, and evidence-card preview.

For the workload-matched crash matrix, analyze the new dataset root with:

```bash
cd DICE
python tools/train_eval_dice_pipeline.py \
  --root "data generation/dataset/ITC_M2Pro_DATA/workload_crash_pilots/data_workload_crash_matrix" \
  --feature_profile mixed \
  --protocol global \
  --out_dir "data generation/dataset/ITC_M2Pro_DATA/workload_crash_pilots/data_workload_crash_matrix/results_dice_workload_crash_mixed"
```

Then open `dice_results_analysis.ipynb` and run `8G. Workload-Matched Crash Matrix` if you want the notebook-side summary, lead-time tables, and crash-card preview for that dataset. The notebook auto-detects the newest `ITC_M2Pro_DATA/workload_crash_pilots/data_workload_crash_*` dataset root first, then falls back to the older `data generation/data_workload_crash_*` locations.

If your repo clone was created with `GIT_LFS_SKIP_SMUDGE=1` and the pilot payload was never pulled, override the notebook to use a local materialized crash-pilot root before running the crash-card cells.

If you prefer to run the tiers separately:

```bash
python generate_dataset.py --phase tier0 --duration_s 1000 --out_dir "$OUT"
python generate_dataset.py --phase tier1_alt --duration_s 1000 --out_dir "$OUT" --tier1_alt_bin macmon
python generate_dataset.py --phase tier2 --duration_s 1000 --out_dir "$OUT" --tier2_template "Time Profiler"
```

### 4. Validate the full collection tree

```bash
python tools/repair_itc_dataset.py --root "$OUT" --tier1_mode alt
python tools/validate_itc_dataset.py --root "$OUT" --tier1_mode alt --check_tier2
```

## Matching the Released `ITC_M2Pro_DATA` Snapshot

The released snapshot is a processed export of the fuller collection tree. After collecting data into a full output directory, create a matching stripped snapshot with:

```bash
python tools/export_release_snapshot.py --root "$OUT" --out_dir ./ITC_M2Pro_DATA_export --tier1_mode alt
```

This export keeps the processed tier CSV files and regenerates `no_nan_report.json` for the exported snapshot.

To validate a processed snapshot that does not include raw artifacts, manifests, or schema files, use:

```bash
python tools/validate_itc_dataset.py --root ./ITC_M2Pro_DATA_export --tier1_mode alt --check_tier2 --processed_only
```

## Timing

At the default `duration_s=1000` and `24` cases, the nominal collection window is:

- `Tier-0`: about `6 h 40 m`, plus about `10 s` once for the initial schema probe
- `Tier-1-alt`: about `6 h 40 m`, plus parsing overhead
- `Tier-1`: about `6 h 40 m`, plus parsing and `sudo` startup overhead
- `Tier-2`: about `6 h 40 m`, plus trace-export overhead

On the reference Apple Silicon collection tree used for the released dataset, the observed wall-clock times were approximately:

- `Tier-0`: `7 h 11 m`
- `Tier-1-alt`: `8 h 02 m`
- `Tier-2`: `9 h 31 m`

During collection, `generate_dataset.py` prints:

- the current case ID
- the elapsed time for that case
- the elapsed time for the current tier
- the estimated remaining time

## Validate and Inspect Existing Data

```bash
# Validate a full legacy Tier-0 + Tier-1 tree
python tools/validate_itc_dataset.py --root ./data --tier1_mode powermetrics

# Validate a full recommended Tier-0 + Tier-1-alt + Tier-2 tree
python tools/validate_itc_dataset.py --root ./data --tier1_mode alt --check_tier2

# Validate a processed public snapshot
python tools/validate_itc_dataset.py --root ./dataset/ITC_M2Pro_DATA --tier1_mode alt --check_tier2 --processed_only

# Rebuild manifests after reruns
python tools/repair_itc_dataset.py --root ./data --tier1_mode alt

# Build a model-ready NaN-free copy
python tools/ensure_no_nan_dataset.py --root ./data --tier1_mode alt --out_dir ./data_clean_no_nan --min_coverage_ratio 0.95

# Probe Tier-1 temperature support before long captures
python tools/probe_tier1_temperature.py --samples 3 --interval_ms 1000 --out_raw ./data/tier1_temp_probe.txt
```

## Repository Layout

```text
DICE/
  README.md
  data generation/
    generate_dataset.py
    docs/
      end-to-end.md
      hardware-compatibility.md
      methodology.md
      tier0.md
      tier1.md
      tier2.md
      ITC_COLLECTION_METHODOLOGY.md
    src/dice/
      cfg.py
      macos_collectors.py
      workloads.py
      tier0_collect_schema.py
      powermetrics_parse_full.py
      tier1_alt_macmon.py
      tier2_xctrace_parse.py
      run_itc_two_phase.py
      crash_evidence.py
    tools/
      export_release_snapshot.py
      validate_itc_dataset.py
      repair_itc_dataset.py
      rerun_cases.py
      ensure_no_nan_dataset.py
      probe_tier1_temperature.py
```
