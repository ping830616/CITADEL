---
layout: default
title: Tier-1 Data
---

# Tier-1 Sources

## Purpose

Tier-1 records hardware-proxy telemetry and converts it into case-aligned CSV files. On Apple Silicon, the recommended Tier-1 path is `tier1_alt`, which uses `macmon` and can fall back to `powermetrics` when a `macmon` collection attempt fails.

## Recommended Tier-1 on Apple Silicon (`tier1_alt`)

### Source and Sampling

- primary source: `macmon`
- fallback source: `powermetrics`
- rate: `5 Hz`
- typical duration: `1000 s`

### Command

```bash
python generate_dataset.py --phase tier1_alt --duration_s 1000 --out_dir ./data --tier1_alt_bin macmon
```

This path is included in the public repository and is part of the default `recommended` workflow.

### Outputs

Per case:

- `macmon_raw.jsonl`
- `tier1_alt_core_5hz.csv`
- `tier1_alt_full_5hz.csv`

Global:

- `tier1_alt_schema_global.json`
- `manifest_tier1_alt.csv`

### Practical Signal Notes

On Apple Silicon laptops, the most reliable Tier-1 signals are usually:

- CPU, GPU, and ANE power
- CPU and GPU usage
- CPU and GPU temperature

Frequency and residency fields can be sparse, especially when fallback telemetry is used. Some channels, such as `soc_temp_c` or `fan_rpm`, may remain unavailable depending on the machine and the exposed sensors.

## Legacy Tier-1 (`powermetrics`)

Legacy Tier-1 remains available for compatibility and portability across Macs that have `powermetrics` but do not have `macmon`.

### Source and Sampling

- source: `powermetrics`
- rate: `5 Hz` (`-i 200`)
- typical duration: `1000 s`

### Command

```bash
python generate_dataset.py --phase tier1 --duration_s 1000 --out_dir ./data
```

### Outputs

Per case:

- `powermetrics_raw.txt`
- `tier1_core_5hz.csv`
- `tier1_full_5hz.csv`

Global:

- `tier1_schema_global.json`
- `manifest_tier1.csv`

## Portable Behavior

`portable` mode chooses the best available Tier-1 path on the current machine:

- `Tier-1-alt` when `macmon` is available
- legacy `Tier-1` when `powermetrics` is available but `macmon` is not
- no Tier-1 collection when neither tool is available

## Probe Temperature Support

Before a long run, you can probe whether numeric temperature keys are exposed:

```bash
python tools/probe_tier1_temperature.py --samples 3 --interval_ms 1000 --out_raw ./data/tier1_temp_probe.txt
```
