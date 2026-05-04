# Telemetry Data Schema

The TCAD extension uses CSV files with one file per setup, scenario, and workload.

## File Naming

```text
<platform>_<scenario>_<workload>.csv
```

Examples:

```text
DDR4_benign_dft.csv
DDR5_DROOP_mm.csv
SERVER1_AGING_gl.csv
```

The loader maps `DDR4` to setup `A` and `DDR5` to setup `B` for ETS compatibility. New platforms should use explicit setup metadata in `data/platforms/`.

## Required Semantic Fields

The loader can derive these fields from filenames, but processed snapshots should include them explicitly:

- `setup`
- `scenario`
- `workload`
- `time_idx`

All other numeric columns are treated as telemetry candidates unless listed as metadata.

## Platform Metadata

Create one JSON file per setup:

```json
{
  "setup": "SERVER_XEON",
  "cpu_model": "replace-me",
  "cores_threads": "replace-me",
  "dram": "replace-me",
  "process_node_nm": null,
  "die_area_mm2": null,
  "sampling_period_ms": null,
  "telemetry_sources": ["pcm", "lm_sensors", "msr"]
}
```

## Missing Features

Do not fill missing platform telemetry with arbitrary zeros. Record unavailable features in metadata and run one of:

- per-platform ranking and detection
- intersection-feature experiments
- explicit missingness-aware comparison
