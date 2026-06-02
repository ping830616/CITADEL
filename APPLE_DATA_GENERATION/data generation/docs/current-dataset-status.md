---
layout: default
title: Current Dataset Status
---

# Current Dataset Status (Apple macOS Collection)

This page summarizes the observed status of the current local dataset profile (`tier0 + tier1_alt + tier2`).

## Snapshot

- Cases expected: `24`
- Sampling per case: `5000` rows (`5001` CSV lines with header)
- Tier folder completeness:
  - `tier0`: `24/24` case folders
  - `tier1_alt`: `24/24` case folders
  - `tier2`: `24/24` case folders
- Per-case CSV line checks: pass (`5001` lines each)

## Tier-1-alt Availability Notes

Observed feature coverage behavior on this Mac:

- Reliable: `cpu_power_w`, `gpu_power_w`, `ane_power_w`, `cpu_usage_pct`, `gpu_usage_pct`, `cpu_temp_c`, `gpu_temp_c`
- Sparse: `cpu_avg_freq_mhz`, `gpu_avg_freq_mhz`, `cpu_residency_active_pct`, `gpu_residency_active_pct`
- Not exposed: `soc_temp_c`, `fan_rpm`

This is a platform/tooling exposure constraint, not a folder alignment issue.

## Tier-2 Schema Note

Current Tier-2 core schema is trace-bucket based (`samples_per_bucket`, `unique_process_count`, etc.).
Legacy CPU/memory/IO core fields may appear in older parser versions.

## Required Cleanup Before Release

If reruns were performed, manifests can contain duplicate lines. Rebuild before publishing:

```bash
python tools/repair_itc_dataset.py --root ./data --tier1_mode alt
python tools/validate_itc_dataset.py --root ./data --tier1_mode alt --check_tier2
```

## Optional Release Artifact (No-NaN Harmonized Copy)

To publish a consistent, no-NaN dataset copy for model ingestion:

```bash
python tools/ensure_no_nan_dataset.py \
  --root ./data \
  --tier1_mode alt \
  --keep_all_nan_columns \
  --min_coverage_ratio 0.0 \
  --fallback_fill global_median \
  --out_dir ./data_clean_tier1_consistent
```

This keeps column alignment stable across cases and imputes residual missing values.

For this repository, the current stored dataset snapshot is:

- `dataset/ITC_M2Pro_DATA/`
- Coverage report: `dataset/ITC_M2Pro_DATA/no_nan_report.json`

The older harmonized clean-schema reference remains documented here:

- [Dataset Feature Map (Clean Tier1 Consistent)](dataset-feature-map-clean-tier1-consistent.md)
