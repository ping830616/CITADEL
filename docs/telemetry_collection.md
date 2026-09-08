# Telemetry Collection and Reproducibility

## Scope

CITADEL separates two reproducibility targets:

1. **Collection reproduction** requires compatible hardware, operating system access, monitoring tools, workloads, and event generators.
2. **Analysis reproduction** begins with the preserved CSV inputs and uses the pinned CITADEL environment and notebook.

The public artifact supports analysis reproduction from the preserved inputs. The revised collection directory supplies portable configuration and replacement voltage and temperature collectors for new Intel campaigns. Because several historical helpers and external tool commits were absent from the original artifact, the replacement collectors are not presented as bit for bit reproductions of the original acquisition software.

## Evaluated Intel platforms

| Item | Setup A | Setup B |
| --- | --- | --- |
| Processor | Intel Core i5-7600K | Intel Core i5-12600K |
| Memory | 4 x 4 GB DDR4 | 2 x 16 GB DDR5 |
| Operating system | Ubuntu 20.04.6 LTS | Ubuntu 20.04.6 LTS |
| Kernel | Linux 5.15.0-101-generic | Linux 5.15.0-101-generic |
| Recorded scenarios | BENIGN, DROOP, RH or TRRespass | BENIGN, DROOP, SPECTRE |

The available records do not establish purchase date, prior operating hours, firmware revision, ambient conditions, cooling history, device lot, process corner, transistor aging state, or manufacturer guardband.

## Preserved acquisition sequence

Each PAMPAR launcher requests ten trials. For a benign trial, the script waits, starts the workload, starts Intel PCM, starts the voltage collector, and then starts the temperature collector. The event launchers add the event process and a platform specific settling delay before the workload. The scripts pass `0.001` as the Intel PCM interval argument and `1000` as the iteration limit. They pass `200` as the requested observation count to each sensor collector.

Intel PCM is invoked in this form:

```text
sudo <PCM_BIN> 0.001 -i=1000 -csv=<OUTPUT_FILE>
```

The scripts invoke Intel PCM and MSR reads with elevated privileges. They launch the collectors in a fixed software order; the historical implementation had no shared hardware trigger. The replacement voltage and temperature collectors add epoch timestamps, elapsed times, sample indices, and read status so new traces can be aligned by trial and time.

## Interfaces

### Performance, memory, power, and energy telemetry

Intel PCM supplies processor, package, cache, memory, and supported power or energy fields. The available columns depend on the processor and PCM build. Preserve the unmodified PCM header with every raw trace and record the PCM executable version and Git commit with `record_environment.sh`.

### Voltage

The replacement voltage collector reads MSR `0x198` on the configured logical processor with `rdmsr`. It extracts bits 47 through 32 and divides the encoded value by 8192 to report volts. This value is reported through a processor register; it is not a process corner measurement.

### Temperature

The replacement temperature collector reads Linux `hwmon` inputs whose driver name is `coretemp`. The kernel exposes these values in millidegrees Celsius. The collector divides each value by 1000 and records the source path and channel label. This is the documented temperature source for new collection. The exact implementation of the unavailable historical temperature helper cannot be recovered from the original repository.

## Tool provenance

Run the following command on every collection host before a campaign:

```bash
TELEMETRY_COLLECTION_SCRIPTS/record_environment.sh \
  "$OUTPUT_ROOT/collection_environment.tsv"
```

The output records the operating system, kernel, processor model, tool paths, available tool versions, Git commits, dirty checkout status, binary hashes, launch arguments, requested intervals, iteration limits, and MSR settings. Preserve this file with the traces.

Collection scripts refuse to replace an existing workload directory unless `ALLOW_OVERWRITE=YES` is set in the collection configuration. Use a new `OUTPUT_ROOT` for each campaign whenever possible.

The original artifact did not record exact Intel PCM, PAMPAR, Plundervolt, TRRespass, or Spectre commits. These historical versions must be reported as not recorded unless the original collection machines or experiment records can recover them. Do not replace the historical values with current repository commits.

## Missing values

The replacement collectors emit an empty value and a nonzero status when a hardware reading fails. Analysis drops a row when all candidate telemetry values are missing. It fills other missing values with means from benign calibration data when available, or with global means otherwise, and subtracts the same means. Constant features are removed. Conditional graph estimation uses a feature median for nonfinite entries and uses zero only when no finite median remains after filtering.

## Preserved data

The main Intel analysis uses inputs under `data/telemetry/processed/ddr_data/`. Git LFS must materialize these files before the notebook is run. These processed inputs permit reproduction of the reported analysis but do not replace collection reproduction on compatible hardware.

The supplemental Apple inputs and their separate collection provenance are under `data/telemetry/raw/apple_data/` and `APPLE_DATA_GENERATION/`.
