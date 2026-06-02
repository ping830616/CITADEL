---
layout: default
title: Tier-0 Data
---

# Tier-0 (Host-Level Telemetry)

Tier-0 is the host-level telemetry layer in DICE. It is collected from operating-system counters through `psutil`, and it is intended to represent what can be measured cheaply and consistently on a deployed laptop without deep tracing infrastructure.

## Collection Semantics

Tier-0 is sampled at 5 Hz. A standard run uses `duration_s=1000`, which produces 5,000 time samples per case. Each case writes one file named `tier0_full_5hz.csv`.

To reduce persistent missingness, Tier-0 uses a probe-driven schema step before full collection. The collector runs a short probe window, keeps only fields that become non-NaN at least once, and writes the resulting global schema to `tier0_schema_global.json`. This schema is then reused across all cases in the run.

## Signal Types in Tier-0

Tier-0 features include timing columns, aggregate CPU usage and CPU time breakdowns, per-core usage percentages, load averages, process-level CPU statistics, memory and swap states, disk and network throughput rates, and system-level counts such as PID count and uptime.

## Interpretation for Anomaly Detection

Tier-0 captures broad runtime behavior, not fine-grained microarchitectural internals. As a result, anomalies that strongly affect host-visible behavior tend to separate more clearly in Tier-0 space.

In the DICE setting, `ATOMIC`, `CACHE`, and `MEMBW` usually show stronger separability in Tier-0 because they induce contention and pressure patterns that move host-level counters more directly. `BRANCH` and `TLB` are harder because their signatures are more microarchitectural and often overlap with benign runtime variability in system-level telemetry.

## Command

```bash
python generate_dataset.py --phase tier0 --duration_s 1000 --out_dir ./data
```
