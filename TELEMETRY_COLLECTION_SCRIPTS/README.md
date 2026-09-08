# Intel Telemetry Collection

This directory separates collection on compatible Intel hardware from analysis of the preserved telemetry inputs. The analysis workflow does not require the original collection systems.

## Historical record

The preserved PAMPAR scripts show the collection order, workload arguments, Intel PCM command, trial count, and nominal collector counts used for Setups A and B. The original repository did not retain the voltage, temperature, DROOP, or Game of Life helper scripts, and it did not record the exact commits of the external tools. This revision supplies documented replacement helpers for future collection. It does not claim that their timing is identical to the unavailable historical helpers.

The original scripts request:

- Intel PCM interval argument: `0.001` seconds
- Intel PCM iteration limit: `1000`
- voltage collector samples: `200`
- temperature collector samples: `200`
- PAMPAR trials requested by each collection script: `10`

## Requirements

- Linux on a compatible Intel processor
- Bash, Git, `awk`, and `coreutils`
- Intel PCM built from a recorded commit
- PAMPAR built from a recorded commit
- `msr-tools` and access to `/dev/cpu/*/msr`
- the Linux `coretemp` driver and readable `hwmon` temperature inputs
- scenario tools needed for the selected experiment

The DROOP utility changes processor voltage through an MSR. It can crash the host, corrupt data, or damage unsupported hardware. It is disabled unless `ENABLE_DROOP=YES`, and it also requires explicit platform arguments. Review the source and use it only on hardware for which you have authorization and a recovery plan.

## Configuration

Copy the example file and edit its absolute paths:

```bash
cp TELEMETRY_COLLECTION_SCRIPTS/collection.env.example \
   TELEMETRY_COLLECTION_SCRIPTS/collection.env
```

Required variables are `PAMPAR_ROOT`, `PCM_BIN`, and `OUTPUT_ROOT`; set `PCM_ROOT` when PCM was built from a Git checkout. The scripts no longer assume `~/PAMPAR` or `~/pcm`. They refuse to replace an existing workload directory by default. Choose a new output root for each run, or set `ALLOW_OVERWRITE=YES` only when the existing data may be deleted.

Before collection, record the environment and dependency commits:

```bash
TELEMETRY_COLLECTION_SCRIPTS/record_environment.sh \
  "$OUTPUT_ROOT/collection_environment.tsv"
```

The record includes Git commits, dirty checkout status, and binary hashes where available. If the original collection machines or checkouts remain available, run this command there and preserve its output. The historical Intel PCM, PAMPAR, Plundervolt, TRRespass, and Spectre commits cannot be recovered from the earlier repository snapshot alone.

## Data sources and units

| Output | Interface | Unit | Status |
| --- | --- | --- | --- |
| Intel PCM CSV | Intel PCM performance monitoring interfaces | Tool dependent | Direct counters and PCM derived metrics |
| `voltage_<trial>.csv` | MSR `0x198` through `rdmsr` | volts | Register value converted by `code / 8192` |
| `temperature_<trial>.csv` | Linux `hwmon` entries exposed by `coretemp` | degrees Celsius | Millidegrees Celsius converted by `/ 1000` |

These interfaces do not provide a process corner measurement. The paper therefore describes them as processor counters and operating condition telemetry rather than complete PVT measurements.

## Timing and synchronization

The PAMPAR scripts start each component in a fixed software sequence. A DROOP process, when selected, starts first and is followed by the platform specific settling delay preserved in each script. The workload then starts, followed by Intel PCM, the voltage collector, and the temperature collector. The historical scripts did not use a shared hardware trigger.

The replacement voltage and temperature collectors record an epoch timestamp, elapsed time, and sample index for every observation. `SENSOR_INTERVAL_S` is a requested sleep interval, not a real time guarantee. Scheduling delay can change the achieved interval. Intel PCM writes its own CSV output. Align streams by trial identifier and recorded time; do not assume exact simultaneous sampling.

## Missing values and preprocessing

The replacement collectors leave a failed reading empty and record a status value. They never substitute zero for a failed hardware reading.

The analysis notebook applies the following procedure to candidate telemetry features:

1. Drop rows for which every candidate feature is missing.
2. Fill remaining missing values with means computed from benign calibration data when those data are available; otherwise use global means.
3. Subtract the same means used for filling.
4. Remove constant candidate features before calibration and scoring.

For conditional graph estimation, nonfinite values are replaced by the feature median. A zero fallback is used only when no finite median remains after feature filtering.

## Running the preserved launchers

Run the platform master script from any directory after setting `COLLECTION_CONFIG` or creating `collection.env`:

```bash
export COLLECTION_CONFIG=/absolute/path/to/collection.env
TELEMETRY_COLLECTION_SCRIPTS/DDR4_PAMPAR_SCRIPTS/master_PAMPAR_DDR4.sh
```

Use a different `OUTPUT_ROOT` for benign and event campaigns because the launchers retain the original per workload directory names.

## External projects

- [PAMPAR](https://github.com/adrianomg/PAMPAR)
- [Intel PCM](https://github.com/intel/pcm)
- [Plundervolt](https://github.com/KitMurdock/plundervolt)
- [TRRespass](https://github.com/vusec/trrespass)
- [Spectre proof of concept](https://gist.github.com/anonymous/99a72c9c1003f8ae0707b4927ec1bd8a)

Record the exact commit of every checkout used in a new campaign. A repository URL without a commit does not identify a reproducible tool version.
