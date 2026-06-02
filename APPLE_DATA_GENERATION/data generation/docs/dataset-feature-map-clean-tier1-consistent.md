---
layout: default
title: Dataset Feature Map (Clean Tier1 Consistent)
---

# Dataset Feature Map: legacy clean Tier-1-consistent reference

This page explains the harmonized clean-schema reference that was used for an earlier release profile.

The current repository snapshot is stored at:

- `dataset/ITC_M2Pro_DATA/`

The historical clean reference described on this page used:

- `dataset/ITC_2026_M2Pro_DATA_clean_tier1_consistent/`

Profile:

- Tier-0 full
- Tier-1-alt core/full
- Tier-2 core/full
- Harmonized for consistent schema and no NaN cells

## Tier-0 Full (`54` columns)

File pattern: `tier0/*/tier0_full_5hz.csv`

### Time and Index

- `idx`: sample index.
- `ts_unix_s`: absolute UNIX time.
- `t_rel_s`: relative time from case start.
- `uptime_s`: system uptime.

### CPU Utilization

- `cpu_pct`: total CPU utilization.
- `cpu0_pct` ... `cpu11_pct`: per-core CPU utilization.
- `cpu_times_user_pct`, `cpu_times_system_pct`, `cpu_times_idle_pct`, `cpu_times_nice_pct`: CPU time breakdown.

### CPU Frequency

- `cpu_freq_current_mhz`, `cpu_freq_min_mhz`, `cpu_freq_max_mhz`: OS-reported frequency proxies.

### Scheduler/Interrupts

- `ctx_switches`, `interrupts`, `soft_interrupts`, `syscalls`: scheduling and interrupt counters.
- `load1`, `load5`, `load15`: load averages.

### Memory and Swap

- `mem_total_bytes`, `mem_available_bytes`, `mem_used_bytes`, `mem_free_bytes`
- `mem_active_bytes`, `mem_inactive_bytes`, `mem_wired_bytes`
- `mem_percent`
- `swap_total_bytes`, `swap_used_bytes`, `swap_free_bytes`, `swap_sin_bytes`, `swap_sout_bytes`, `swap_percent`

### Disk and Network Rates

- `disk_read_Bps`, `disk_write_Bps`, `disk_read_IOPS`, `disk_write_IOPS`
- `net_sent_Bps`, `net_recv_Bps`, `net_sent_Pps`, `net_recv_Pps`

### System State

- `pids_count`: number of visible processes.

## Tier-1-alt Core (`14` columns)

File pattern: `tier1_alt/*/tier1_alt_core_5hz.csv`

- `idx`: sample index.
- `cpu_power_w`, `gpu_power_w`, `ane_power_w`: power features.
- `cpu_temp_c`, `gpu_temp_c`, `soc_temp_c`: thermal features.
- `cpu_usage_pct`, `gpu_usage_pct`: usage features.
- `cpu_avg_freq_mhz`, `gpu_avg_freq_mhz`: frequency proxies.
- `cpu_residency_active_pct`, `gpu_residency_active_pct`: residency proxies.
- `fan_rpm`: fan speed proxy.

Note:

- This cleaned dataset is harmonized. Some Tier-1-alt fields that are not consistently exposed by laptop sensors are imputed to maintain a complete schema.

## Tier-1-alt Full (`21` columns)

File pattern: `tier1_alt/*/tier1_alt_full_5hz.csv`

- `idx`
- Power rails and totals: `all_power`, `cpu_power`, `gpu_power`, `ane_power`, `ram_power`, `gpu_ram_power`, `sys_power`
- CPU usage splits: `pcpu_usage_0`, `pcpu_usage_1`, `ecpu_usage_0`, `ecpu_usage_1`
- GPU usage splits: `gpu_usage_0`, `gpu_usage_1`
- Memory usage: `memory_ram_total`, `memory_ram_usage`, `memory_swap_total`, `memory_swap_usage`
- Temperatures: `temp_cpu_temp_avg`, `temp_gpu_temp_avg`
- `timestamp`

## Tier-2 Core (`10` columns)

File pattern: `tier2/*/tier2_core_5hz.csv`

- `idx`
- `samples_per_bucket`: number of aggregated trace samples.
- `unique_process_count`, `unique_thread_count`: process/thread diversity in bucket.
- `avg_core_id`, `max_core_id`: CPU core-id statistics from trace events.
- `total_weight_ns`, `avg_weight_ns`: event-weight time statistics.
- `running_fraction`: running-state fraction.
- `sentinel_count`: parser sentinel count.

## Tier-2 Full (`14` columns)

File pattern: `tier2/*/tier2_full_5hz.csv`

Contains Tier-2 core-like fields plus extra bucket timing/counter fields:

- `first_sample_time_ns`, `last_sample_time_ns`, `sample_span_ns`, `running_count`
- plus shared fields (`samples_per_bucket`, `unique_process_count`, `unique_thread_count`, `avg_core_id`, `max_core_id`, `total_weight_ns`, `avg_weight_ns`, `running_fraction`, `sentinel_count`)

## Practical Interpretation

- Tier-0 gives broad host telemetry.
- Tier-1-alt gives power/thermal/usage-oriented proxies for Apple Silicon.
- Tier-2 gives trace-derived runtime evidence.
- This cleaned release prioritizes case-aligned schema consistency for downstream modeling.
