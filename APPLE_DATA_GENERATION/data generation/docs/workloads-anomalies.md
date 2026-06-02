---
layout: default
title: Workloads and Anomalies
---

# Workloads and Anomalies

## Workloads

| Workload | Description |
|---|---|
| `BROWSER` | Network + parsing style behavior via repeated HTTP fetches. |
| `VIDEO_SW` | Software video-style frame operations (grayscale, downsample, compress/decompress). |
| `PY_AI` | Alternating tensor and matrix math (Torch/Numpy). |
| `PY_STATS` | Large-array streaming stats and memory update pattern. |

## Detailed Workload Profiles

### `BROWSER`

Motivation: `BROWSER` represents interactive, bursty host behavior with mixed network and CPU activity, which is common in user-facing workloads.

Dominant Tier signals:

- Tier-0: `net_sent_Bps`, `net_recv_Bps`, `cpu_pct`, `load1`, and scheduler counters (`ctx_switches`, `interrupts`) show short bursts and idle gaps.
- Tier-1-alt: `cpu_power_w` and `cpu_usage_pct` usually rise in bursts; thermal channels (`cpu_temp_c`, `gpu_temp_c`) tend to move gradually.
- Tier-2: bucket-level `running_fraction`, `unique_process_count`, and `unique_thread_count` often reflect frequent scheduling variation.

Expected anomaly sensitivity:

- Stronger: `ATOMIC` (contention and scheduler pressure can stand out).
- Moderate: `CACHE`, `MEMBW`.
- Harder: `BRANCH`, `TLB` (their signatures are subtler in host-level mixed interactive behavior).

### `VIDEO_SW`

Motivation: `VIDEO_SW` emulates software video-processing pipelines with sustained frame transforms and compression/decompression loops.

Dominant Tier signals:

- Tier-0: sustained `cpu_pct`, elevated load averages, and memory/system counters become more stable than in bursty interactive workloads.
- Tier-1-alt: `cpu_power_w` and `cpu_usage_pct` are typically elevated; thermal channels trend upward over longer windows.
- Tier-2: `running_fraction` and time-weight statistics (`total_weight_ns`, `avg_weight_ns`) often show sustained compute occupancy.

Expected anomaly sensitivity:

- Stronger: `CACHE`, `MEMBW`.
- Moderate: `ATOMIC`.
- Harder: `BRANCH`, `TLB`.

### `PY_AI`

Motivation: `PY_AI` models AI-style numerical kernels by alternating Torch and NumPy matrix-heavy phases.

Dominant Tier signals:

- Tier-0: high compute pressure appears in `cpu_pct`, load, and memory activity (`mem_active_bytes`, swap-related counters depending on pressure).
- Tier-1-alt: power and usage channels (`cpu_power_w`, `gpu_power_w`, `cpu_usage_pct`, `gpu_usage_pct`) can reflect phase changes when MPS/GPU is active.
- Tier-2: process/thread activity and running-state features (`running_fraction`, `unique_thread_count`) can show phase transitions between compute modes.

Expected anomaly sensitivity:

- Stronger: `MEMBW`, `CACHE`.
- Moderate: `ATOMIC`.
- Harder: `BRANCH`; `TLB` can remain subtle unless address-translation pressure dominates runtime behavior.

### `PY_STATS`

Motivation: `PY_STATS` stresses large-array statistical streaming behavior with repeated reductions and periodic in-place updates.

Dominant Tier signals:

- Tier-0: memory and CPU counters (`mem_used_bytes`, `mem_active_bytes`, `cpu_pct`, load averages) often show sustained bandwidth-oriented behavior.
- Tier-1-alt: `cpu_power_w`, `cpu_usage_pct`, and thermal channels usually track a long-running CPU-bound pattern.
- Tier-2: bucket-level runtime fields (`samples_per_bucket`, `running_fraction`, `total_weight_ns`) commonly reflect steady execution with lower burstiness.

Expected anomaly sensitivity:

- Stronger: `MEMBW`, `CACHE`, often `ATOMIC`.
- Moderate to harder: `TLB`, depending on working-set and paging patterns.
- Harder: `BRANCH` in many runs due to overlap with benign runtime variability.

## Stressors

| Stressor | Class | Description |
|---|---|---|
| `NOMINAL` | Nominal | No extra stress thread; baseline behavior. |
| `CACHE` | Anomaly | Cache pressure using strided access patterns. |
| `TLB` | Anomaly | TLB pressure using random page-level touches. |
| `BRANCH` | Anomaly | High branch unpredictability loop. |
| `MEMBW` | Anomaly | Memory bandwidth pressure with large-buffer updates. |
| `ATOMIC` | Anomaly | Lock/atomic contention with multithread increments. |

## Labeling Rule

- `NOMINAL` stressor -> class label `NOMINAL`
- any other stressor -> class label `ANOMALY`

## Total Cases

`4 workloads x 6 stressors = 24` case folders per tier.
