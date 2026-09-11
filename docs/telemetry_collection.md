# Telemetry Collection and Provenance

## Reproducibility boundary

CITADEL supports two different reproduction paths:

- **Analysis reproduction** starts from the 78 preserved, processed DDR4 and DDR5 CSV files in `data/telemetry/processed/ddr_data`. This path does not require the original collection hardware.
- **New trace collection** uses `TELEMETRY_COLLECTION_SCRIPTS` on a compatible Intel Linux system. It requires PAMPAR, Intel PCM, MSR access, and lm-sensors. A DROOP run also requires a processor specific voltage safety review and explicit configuration.

The collection scripts record the selected paths, Git revisions, requested intervals, sample counts, privilege command, host, kernel, and process completion events. They do not prove that a new host is electrically equivalent to either original platform.

## Historical provenance and limits

The collection directory came from X-OCTANE commit `cd669b97327deb1169f12cf8dfe45b08a5ed5ada` and entered CITADEL in commit `02df22ef29ffdb50584b17e19a7b3fabf2712e6c`. The X-OCTANE history contained the PAMPAR workload scripts and the MSR utilities, but it never contained `collect_volt_data.sh`, `collect_temp_data.sh`, `just_droop_ddr4.sh`, or `just_droop_ddr5.sh`.

Consequently, the following facts cannot be recovered from the historical artifact:

- the exact PAMPAR and Intel PCM revisions installed on the original hosts;
- the requested intervals used by the original auxiliary voltage and temperature collectors;
- the exact lm-sensors chips and labels mapped to the processed `TEMP_*` columns;
- the original SH image file, which was named `moon_3000.jpg` but was not committed;
- the program that aligned the 200 auxiliary samples with each 1,000 row PCM trial.

The restored helpers define a reproducible protocol for new collections. They do not retroactively establish these missing historical details. The preserved analysis inputs remain the source of truth for reproducing the paper results.

The repository stores the DROOP utility as source rather than as a host specific binary. Build it on the target machine with `make -C TELEMETRY_COLLECTION_SCRIPTS/just_droop clean all`. The utility resets both configured voltage planes after a normal run and on `SIGINT` or `SIGTERM`, but DROOP experimentation still requires an independent recovery plan for host or power failures.

## Reference revisions for new collections

Use these exact revisions for a new reference collection. Every run checks and records the PAMPAR and PCM commits when the paths are Git checkouts.

| Component | Repository | Reference revision | Role |
| --- | --- | --- | --- |
| PAMPAR | `https://github.com/adrianomg/PAMPAR` | `568430be779f5bf1d0bfddca35bc796adc215262` | 13 PThreads workloads |
| Intel PCM | `https://github.com/intel/pcm` | `ee01a82b75f9a570c005303cd9ec1a2032c2e88b` | Processor counters, memory traffic, energy, and PCM thermal headroom |
| Included DROOP utility | `TELEMETRY_COLLECTION_SCRIPTS/just_droop/operation.c` | CITADEL collection commit | MSR `0x150` offset writer, disabled by default |
| Included Spectre proof of concept | `TELEMETRY_COLLECTION_SCRIPTS/spectre_attack/spectre_poc.c` | CITADEL collection commit | Optional event generator retained for provenance |
| Plundervolt reference | `https://github.com/KitMurdock/plundervolt` | `a7313c268d7c27ac3eb806d3ed99019788c5f605` | Related external reference, not invoked by the PAMPAR scripts |
| TRRespass reference | `https://github.com/vusec/trrespass` | `7ea523a4149daf1f1c4d8b099c2b3584f973d086` | Related external reference, not invoked by the PAMPAR scripts |

Only the Spectre C source is archived. A precompiled Linux executable is not
portable, is not needed for archived-data reanalysis, and is intentionally
excluded. If an authorized live collection needs this optional event generator,
compile the preserved source on the isolated target host and record the compiler,
flags, source hash, and executable hash in that campaign's manifest.

Clone and pin the two required tools:

```bash
git clone https://github.com/adrianomg/PAMPAR.git
git -C PAMPAR checkout 568430be779f5bf1d0bfddca35bc796adc215262

git clone https://github.com/intel/pcm.git
git -C pcm checkout ee01a82b75f9a570c005303cd9ec1a2032c2e88b
```

Build PAMPAR using its root Makefile. Build PCM using the instructions for the pinned revision and confirm that `build/bin/pcm` is executable.

## Host requirements and privileges

The restored collection path targets Linux on a supported Intel processor. Install `msr-tools` and `lm-sensors`, then verify the intended host before collecting data:

```bash
sudo modprobe msr
sudo rdmsr 0x198
sensors -u
```

Intel PCM and `rdmsr` require elevated access in the reference configuration. `COLLECTION_PRIVILEGE_COMMAND` defaults to `sudo` and is written to `collection_metadata.txt`. Set it to an empty string only if the current account already has the required permissions.

## Configuration

Copy the example configuration and edit its absolute paths:

```bash
cp TELEMETRY_COLLECTION_SCRIPTS/collection_config.example.sh \
   TELEMETRY_COLLECTION_SCRIPTS/collection_config.sh
```

The local configuration is ignored by Git. Important variables include:

- `PAMPAR_ROOT` and `PAMPAR_EXPECTED_COMMIT`;
- `PCM_ROOT`, `PCM_BIN`, and `PCM_EXPECTED_COMMIT`;
- `COLLECTION_OUTPUT_ROOT` and `COLLECTION_TRIALS`;
- `PCM_INTERVAL_SECONDS` and `PCM_ITERATIONS`;
- `VOLTAGE_SAMPLES`, `TEMPERATURE_SAMPLES`, and the two auxiliary requested intervals;
- `PAMPAR_SH_INPUT`, `PAMPAR_SH_HEIGHT`, and `PAMPAR_SH_WIDTH` for the uncommitted SH image;
- the platform specific DROOP offsets, which have no defaults.

The example requests ten trials, 1,000 PCM iterations, a PCM interval of 0.001 seconds, and 200 samples from each auxiliary collector. The two 0.005 second auxiliary intervals are explicit reference settings for new collections. They are not claimed as recovered values from the original experiments.

## Workload commands

Each workload script invokes the PAMPAR `pthread` binary. The table shows the arguments retained from the original DDR4 and DDR5 scripts. Paths shown as variables are resolved from `collection_config.sh`.

| Workload | DDR4 arguments | DDR5 arguments |
| --- | --- | --- |
| DFT | `4 32768` | `16 50000` |
| DJ | `4 16384 ${PAMPAR_ROOT}/Apps/DJ/inputDJ/1024.txt` | `16 16384 ${PAMPAR_ROOT}/Apps/DJ/inputDJ/1024.txt` |
| DP | `4 50000000000` | `16 100000000000` |
| GL | `4 ${PAMPAR_ROOT}/Apps/GL/inputGL/1024.txt` | `16 ${PAMPAR_ROOT}/Apps/GL/inputGL/1024.txt` |
| GS | `4 1300` | `16 1300` |
| HA | `4 10000 300000` | `16 10000 1200000` |
| JA | `4 4096` | `16 4096` |
| MM | `4 4096` | `16 5000` |
| NI | `4 5000000000` | `16 5000000000` |
| OE | `4 300000` | `16 300000` |
| PI | `4 4000000000` | `16 8000000000` |
| SH | `${PAMPAR_SH_INPUT} ${PAMPAR_SH_HEIGHT} ${PAMPAR_SH_WIDTH} 4` | `${PAMPAR_SH_INPUT} ${PAMPAR_SH_HEIGHT} ${PAMPAR_SH_WIDTH} 16` |
| TR | `4 2500` | `16 2500` |

The GL scripts previously called missing `GL_bchmark.sh` files. They now invoke the pinned PAMPAR GL binary and its committed 1,024 by 1,024 input directly. The SH scripts require an explicit image because the historical 3,000 by 3,000 input was not committed.

For every trial, the PCM command is:

```bash
sudo "${PCM_BIN}" "${PCM_INTERVAL_SECONDS}" \
  -i="${PCM_ITERATIONS}" \
  -csv="${output_directory}/log_${trial}.csv"
```

With the example configuration, this becomes `sudo pcm 0.001 -i=1000 -csv=...`. The 0.001 value is the requested reporting interval, not a guarantee that the host can deliver exactly one millisecond between rows.

## Voltage and temperature sources

`collect_volt_data.sh` invokes `rdmsr 0x198`. It extracts bits 47:32 and divides the encoded integer by 8,192 to produce `cpu_voltage_v`. The output preserves both the raw hexadecimal MSR value and the derived voltage in volts.

`collect_temp_data.sh` invokes `sensors -u`. It records each `temp*_input` value as a long form CSV row with the lm-sensors chip, sensor label, attribute, and temperature in degrees Celsius. This records the actual interface and mapping for every new run. It does not assert that the original processed `TEMP_CORE_*`, `TEMP_ACPI_*`, and `TEMP_PCI_*` fields came from the same chip labels.

Intel PCM also emits `TEMP` fields. PCM defines these values as thermal headroom in degrees Celsius relative to `TjMax`, where zero corresponds to the maximum junction temperature. These PCM fields are distinct from the auxiliary absolute temperature readings.

## Synchronization and completion

The scripts use the following sequence for each trial:

1. Write a nanosecond timestamp for `trial_start`.
2. For a DROOP trial, start the disabled by default DROOP helper and retain the original lead delay. DDR4 uses seven seconds except GL and SH, which use eight seconds. DDR5 uses 12 seconds except GL, which uses 14 seconds.
3. Write `workload_and_collectors_launch_begin`, then start the PAMPAR workload, Intel PCM, voltage collector, and temperature collector in that order as background processes.
4. Record every process identifier and wait for all four processes, plus the DROOP process when applicable.
5. Write `trial_complete` only if every process exits successfully. Otherwise, write `process_failed` and `trial_failed`, then return a nonzero status.
6. Apply the retained 30 second benign or 40 second DROOP cooldown before the next trial.

The master scripts use one run identifier across all 13 workloads and wait for each workload script before starting the next one. They retain a three second gap between workloads. Interrupt and termination traps stop any tracked child processes.

This procedure records launch order and completion. It does not claim simultaneous hardware sampling. PCM and the two auxiliary collectors maintain their own timestamps or sample indices. The restored scripts leave their streams separate and do not interpolate or join them.

For a continuously observed workload switch, use `scripts/run_intel_transition_campaign.py`. Each campaign run starts one Intel PCM process, keeps it active while randomized PAMPAR workload processes change, and records the phase start and end times plus every workload invocation. `scripts/analyze_intel_transition_campaign.py` aligns PCM Date and Time values with those events. This new protocol is distinct from the historical per workload files and is documented in `docs/intel_continuous_workload_transitions.md`.

## Output files

Each invocation creates a new directory:

```text
${COLLECTION_OUTPUT_ROOT}/${CITADEL_RUN_ID}/${platform}/${condition}/${workload}/
```

The directory contains:

- `collection_metadata.txt`: configuration, revisions, source interfaces, units, requested intervals, privileges, and host information;
- `trial_events.csv`: trial timestamps, launch events, process identifiers, failures, and completion;
- `log_<trial>.csv`: Intel PCM output;
- `voltage_<trial>.csv`: raw MSR value and derived voltage;
- `temperature_<trial>.csv`: long form lm-sensors readings.

Existing output directories are never deleted. Reusing a run identifier and workload path causes an error.

## Missing values and preprocessing

The collection scripts do not impute missing measurements. A failed PCM, voltage, temperature, workload, or DROOP process marks the trial as failed. Incomplete files must not be padded or silently promoted to complete trials.

For analysis of the preserved processed CSV files, the notebook:

1. removes the autogenerated unnamed index column and trims header whitespace;
2. derives setup, scenario, workload, time index, and sample label metadata;
3. removes rows for which every numeric telemetry candidate is missing;
4. fills remaining missing numeric values with the corresponding benign mean when benign samples exist, or otherwise with the global feature mean;
5. subtracts the same benign or global mean from each numeric feature;
6. excludes constant features from downstream ranking.

The repository does not contain the historical program that joined PCM, voltage, and temperature streams into the preserved wide CSV files. Therefore, byte for byte regeneration of those processed collection files is not claimed. Analysis reproduction begins with the preserved CSV inputs and is independently covered by `docs/reproducibility.md`.

## Signal dictionary

[`telemetry_dictionary.csv`](telemetry_dictionary.csv) has one row for every candidate field in the preserved DDR4 and DDR5 schemas. It records the platform, exact CSV field name, scope, metric, physical meaning, source interface, unit, requested interval information, measured or derived status, historical availability, and missing value treatment.
