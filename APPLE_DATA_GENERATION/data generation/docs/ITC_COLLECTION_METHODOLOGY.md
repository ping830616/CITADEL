# ITC Dataset Collection Methodology (Tier-0 to Tier-2, macOS)

This document describes the macOS collection workflow used to build the DICE ITC dataset and the public workflow that now reproduces that procedure as closely as possible on supported Apple Silicon hosts.

## 1) Case Design

- workloads (`4`): `BROWSER`, `VIDEO_SW`, `PY_AI`, `PY_STATS`
- conditions (`6`): `NOMINAL`, `CACHE`, `TLB`, `BRANCH`, `MEMBW`, `ATOMIC`
- total cases: `4 x 6 = 24`
- stable case ID format: `WORKLOAD__CONDITION`

## 2) Tier Definitions

### Tier-0

- source: `psutil` counters at `5 Hz`
- processed output per case: `tier0_full_5hz.csv`
- schema strategy:
  - perform a short probe pass
  - retain fields that are observed at least once
  - persist a global schema as `tier0_schema_global.json`

### Tier-1-alt (recommended Apple Silicon Tier-1 path)

- primary source: `macmon`
- runtime fallback: `powermetrics`
- processed outputs per case:
  - `tier1_alt_core_5hz.csv`
  - `tier1_alt_full_5hz.csv`
- raw artifact per case: `macmon_raw.jsonl`
- global schema: `tier1_alt_schema_global.json`

### Tier-1 (legacy compatibility path)

- source: `powermetrics`
- raw artifact per case: `powermetrics_raw.txt`
- processed outputs per case:
  - `tier1_core_5hz.csv`
  - `tier1_full_5hz.csv`
- global schema: `tier1_schema_global.json`

### Tier-2

- source: `xcrun xctrace` with `Time Profiler`
- raw artifacts per case:
  - `xctrace.trace`
  - `xctrace_export.xml`
- processed outputs per case:
  - `tier2_core_5hz.csv`
  - `tier2_full_5hz.csv`
- global schema: `tier2_schema_global.json`

## 3) Recommended Public Collection Commands

### 3.1 One-command Apple Silicon profile

```bash
python generate_dataset.py --phase recommended --duration_s 1000 --out_dir ./data
```

This runs `Tier-0`, `Tier-1-alt`, and `Tier-2`.

### 3.2 Capability-aware portable profile

```bash
python generate_dataset.py --phase portable --duration_s 1000 --out_dir ./data
```

This runs `Tier-0` everywhere, then chooses the best available higher-tier path on the current host.

### 3.3 Tier-by-tier sequence

```bash
python generate_dataset.py --phase tier0 --duration_s 1000 --out_dir ./data
python generate_dataset.py --phase tier1_alt --duration_s 1000 --out_dir ./data --tier1_alt_bin macmon
python generate_dataset.py --phase tier2 --duration_s 1000 --out_dir ./data --tier2_template "Time Profiler"
```

## 4) Output Layout

A full collection tree contains:

```text
data/
  tier0/<CASE_ID>/tier0_full_5hz.csv
  tier1_alt/<CASE_ID>/macmon_raw.jsonl
  tier1_alt/<CASE_ID>/tier1_alt_core_5hz.csv
  tier1_alt/<CASE_ID>/tier1_alt_full_5hz.csv
  tier1/<CASE_ID>/powermetrics_raw.txt
  tier1/<CASE_ID>/tier1_core_5hz.csv
  tier1/<CASE_ID>/tier1_full_5hz.csv
  tier2/<CASE_ID>/xctrace.trace
  tier2/<CASE_ID>/xctrace_export.xml
  tier2/<CASE_ID>/tier2_core_5hz.csv
  tier2/<CASE_ID>/tier2_full_5hz.csv
  meta/<CASE_ID>/meta_tier{0,1,1_alt,2}.json
  logs/<CASE_ID>/*.log
  manifest_tier0.csv
  manifest_tier1.csv
  manifest_tier1_alt.csv
  manifest_tier2.csv
  tier0_schema_global.json
  tier1_schema_global.json
  tier1_alt_schema_global.json
  tier2_schema_global.json
```

The released `ITC_M2Pro_DATA` folder is a processed export of that fuller tree.

## 5) Validation

### Full collection tree

```bash
python tools/repair_itc_dataset.py --root ./data --tier1_mode alt
python tools/validate_itc_dataset.py --root ./data --tier1_mode alt --check_tier2
```

### Processed public-style snapshot

```bash
python tools/export_release_snapshot.py --root ./data --out_dir ./ITC_M2Pro_DATA_export --tier1_mode alt
python tools/validate_itc_dataset.py --root ./ITC_M2Pro_DATA_export --tier1_mode alt --check_tier2 --processed_only
```

## 6) Timing

At `24` cases and `1000 s` per case, the nominal collection window is `6 h 40 m` per tier. Observed wall-clock time is longer because schema generation, parsing, trace export, and occasional reruns add overhead. On the reference Apple Silicon collection tree used for the released dataset, the observed totals were approximately:

- `Tier-0`: `7 h 11 m`
- `Tier-1-alt`: `8 h 02 m`
- `Tier-2`: `9 h 31 m`

## 7) Portability Interpretation

The workflow is portable in the sense that it adapts to the telemetry interfaces available on the current machine. It is not hardware-neutral. Another Apple Silicon Mac can often reproduce the same procedure, but a different machine may expose different Tier-1 signals, may lack Tier-2 support, or may produce a different schema.
