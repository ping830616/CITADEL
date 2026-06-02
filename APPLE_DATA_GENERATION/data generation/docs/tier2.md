---
layout: default
title: Tier-2 Data
---

# Tier-2 (`xctrace` Telemetry)

## Purpose

Tier-2 adds profiler-derived runtime evidence from Instruments. In the released Apple Silicon workflow, it complements Tier-0 and Tier-1 with trace-based execution summaries.

## Source and Requirements

- source: `xcrun xctrace`
- default template: `Time Profiler`
- host requirement: macOS with Xcode tooling and an accepted Xcode license

Preflight check:

```bash
xcrun xctrace version
```

## Collection Command

```bash
python generate_dataset.py --phase tier2 --duration_s 1000 --out_dir ./data --tier2_template "Time Profiler"
```

`recommended` mode also runs Tier-2 automatically on supported Apple Silicon hosts:

```bash
python generate_dataset.py --phase recommended --duration_s 1000 --out_dir ./data
```

`portable` mode runs Tier-2 only when `xctrace` is available and licensed:

```bash
python generate_dataset.py --phase portable --duration_s 1000 --out_dir ./data
```

## Outputs

Per case:

- `xctrace.trace`
- `xctrace_export.xml`
- `tier2_core_5hz.csv`
- `tier2_full_5hz.csv`

Global:

- `tier2_schema_global.json`
- `manifest_tier2.csv`

## Tier-2 Core Fields

The current release schema is trace-bucket based. The core Tier-2 fields are:

- `avg_core_id`
- `avg_weight_ns`
- `max_core_id`
- `running_fraction`
- `samples_per_bucket`
- `sentinel_count`
- `total_weight_ns`
- `unique_process_count`
- `unique_thread_count`

The full Tier-2 schema adds timing-span and count fields such as `first_sample_time_ns`, `last_sample_time_ns`, `running_count`, and `sample_span_ns`.

Older parser versions may emit a legacy CPU/memory/IO-oriented Tier-2 schema. The current parser supports both the current trace-bucket export format and older legacy formats.

## Timing

At the default `duration_s=1000` and `24` cases:

- nominal capture window: about `6 h 40 m`
- practical runtime: nominal capture window plus trace-export and parsing overhead

On the reference local collection tree used for the released dataset, Tier-2 took about `9 h 31 m` in total.

## Notes

- Tier-2 output depends on the local Time Profiler export structure and on the availability of Xcode tooling.
- The public repository includes the full Tier-2 collection and parsing path for supported macOS hosts.
- If you need a stripped public-style dataset folder after a full Tier-2 run, use `tools/export_release_snapshot.py`.
