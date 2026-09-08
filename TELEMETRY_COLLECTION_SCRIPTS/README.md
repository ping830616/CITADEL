# Telemetry Collection Scripts

These scripts collect processor counters and operating condition telemetry for CITADEL Setups A and B. Setup A is the DDR4 platform and Setup B is the DDR5 platform.

Collection requires a compatible Intel Linux host, access to Intel PCM and model specific registers, a compiled PAMPAR checkout, and lm-sensors. Analysis reproduction uses the preserved CSV files under `data/telemetry/processed/ddr_data` and does not require the original hardware.

## Configure a collection host

1. Clone and check out the documented PAMPAR and Intel PCM revisions in [`docs/telemetry_collection.md`](../docs/telemetry_collection.md).
2. Build PAMPAR and Intel PCM on the collection host.
3. Install `msr-tools` and `lm-sensors`, load the `msr` kernel module, and verify that `rdmsr 0x198` and `sensors -u` expose the intended channels.
4. Copy `collection_config.example.sh` to `collection_config.sh` and edit the absolute paths and platform settings.
5. Run one workload script from either `DDR4_PAMPAR_SCRIPTS` or `DDR5_PAMPAR_SCRIPTS`. The master scripts run all 13 PAMPAR workloads in sequence.

For example:

```bash
cp TELEMETRY_COLLECTION_SCRIPTS/collection_config.example.sh \
   TELEMETRY_COLLECTION_SCRIPTS/collection_config.sh

TELEMETRY_COLLECTION_SCRIPTS/DDR4_PAMPAR_SCRIPTS/DDR4_RIG_PCM_COLLECT_DFT.sh
```

Each workload script requests ten trials by default. It launches the workload, Intel PCM, the voltage collector, and the temperature collector as concurrent processes. The script records launch and completion events, waits for every process, and marks a trial as failed if any process returns a nonzero status. Results are written to a new run directory instead of deleting an earlier collection.

## Restored helpers

- `collect_volt_data.sh` reads MSR `0x198` and converts bits 47:32 to volts using the retained `value / 8192` conversion.
- `collect_temp_data.sh` reads every `temp*_input` channel reported by `sensors -u` and records the lm-sensors chip and label.
- `just_droop_ddr4.sh` and `just_droop_ddr5.sh` call the included MSR offset utility only after explicit hardware specific settings and `CITADEL_ENABLE_DROOP=1` are provided.

The DROOP helpers write voltage offsets through MSR `0x150` and can crash or damage an unsupported system. They are disabled by default. Never copy voltage settings from another processor without a platform specific safety review.

## Historical limits

The original X-OCTANE history did not contain the four helper scripts, exact external tool revisions, the auxiliary collector intervals, or the historical lm-sensors chip mapping. The files here provide a complete and versioned procedure for new collections, but they do not retroactively establish those missing facts for the preserved traces. See the detailed provenance and data dictionary:

- [`docs/telemetry_collection.md`](../docs/telemetry_collection.md)
- [`docs/telemetry_dictionary.csv`](../docs/telemetry_dictionary.csv)

Related projects used by the original experimental workflow include [PAMPAR](https://github.com/adrianomg/PAMPAR), [Intel PCM](https://github.com/intel/pcm), [Plundervolt](https://github.com/KitMurdock/plundervolt), [TRRespass](https://github.com/vusec/trrespass), and the in-repository Spectre proof of concept. Cite the corresponding works when using those tools.
