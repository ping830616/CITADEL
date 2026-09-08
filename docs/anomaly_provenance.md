# Anomaly provenance and labels

This audit distinguishes preserved source evidence from missing historical experiment records. It does not reconstruct an undocumented procedure or change the detector's data or labels.

## Real data and synthetic smoke checks

`data/external_sources.json` identifies `ping830616/X-OCTANE`, path `data/TELEMETRY_DATA`, as the source of the DDR snapshot. The preserved TCAD and lifecycle manifests point to `data/telemetry/processed/ddr_data`. These are processed telemetry files, not original acquisition logs.

The notebook has a separate synthetic generator for `data/sample/`, used in sample mode for pipeline checks. The real-data loader reads the recorded files. The DROOP adaptive branch adds differences, rolling ranges, deviations, and related derived features in `results/notebook_run/droop_adaptive_data`; that feature computation does not implement a voltage injection or generate a new physical event. These facts establish the current analysis path, not a complete audit of all preprocessing before the snapshot was preserved.

## Evidence by scenario

| Scenario | Platform | Preserved evidence | Unresolved details |
| --- | --- | --- | --- |
| DROOP | A and B | Collector scripts invoke setup-specific DROOP launchers; `operation.c` contains software voltage-control requests. | Original launcher arguments, effective offsets, voltage readback, event boundaries, and exact tool versions. |
| RH | A | Scenario files and a collection README that identifies TRRespass. | Run-specific launcher and configuration, version, event boundaries, and bit-flip confirmation. |
| SPECTRE | B | Scenario files, a collection README, and Spectre proof-of-concept source. | Exact binary/version, invocation, mitigation state, event boundaries, and logs confirming successful leakage. |

Source evidence was inspected at repository commit `520304689601ab62b53da9ac8420e22cefe20dcb`. Historical links below deliberately pin that commit, including its original directory spelling; they remain valid if the collection directory is later renamed.

## DROOP

The [preserved helper source](https://github.com/ping830616/CITADEL/blob/520304689601ab62b53da9ac8420e22cefe20dcb/TELEMETRY_COLECTION_SCRIPTS/just_droop/operation.c) opens `/dev/cpu/0/msr` for writing and contains a `voltage_change` function that writes at MSR offset `0x150`. Its control path constructs voltage-offset requests. This establishes the presence of software voltage-control code; it does not establish which arguments were used or whether the requests took effect on a particular platform. The source does not check the return value of that write in `voltage_change`.

For example, the preserved [DDR4 PI collector](https://github.com/ping830616/CITADEL/blob/520304689601ab62b53da9ac8420e22cefe20dcb/TELEMETRY_COLECTION_SCRIPTS/DDR4_PAMPAR_SCRIPTS/DDR4_RIG_PCM_COLLECT_PI_DROOP.sh) invokes `just_droop_ddr4.sh`, waits seven seconds, and launches PAMPAR plus PCM and auxiliary collectors. The [DDR5 PI collector](https://github.com/ping830616/CITADEL/blob/520304689601ab62b53da9ac8420e22cefe20dcb/TELEMETRY_COLECTION_SCRIPTS/DDR5_PAMPAR_SCRIPTS/DDR5_RIG_PCM_COLLECT_PI_DROOP.sh) names `just_droop_ddr5.sh` and waits twelve seconds. These examples request ten iterations, 1,000 PCM observations at a nominal 0.001-second interval, and 200 observations from each auxiliary helper. They show requested collection settings, not measured timing or proof that ten independent runs completed successfully.

The original setup-specific launchers and auxiliary collector implementations were absent from the inspected snapshot. No exact offset, waveform, achieved sampling interval, event onset/end, or effective voltage change can be recovered from these collector calls alone. Replacement launchers added later cannot establish the original settings.

Do not describe DROOP as purely workload-induced power stress or assert that voltage was never directly modified on the basis of this repository. Do not describe a verified physical voltage injection either. Until historical arguments and readback/logs are recovered, report the named scenario and this provenance limitation.

## RH and Spectre

The [collection README](https://github.com/ping830616/CITADEL/blob/520304689601ab62b53da9ac8420e22cefe20dcb/TELEMETRY_COLECTION_SCRIPTS/README.md) identifies TRRespass and a Spectre implementation as external collection tools. [Spectre source](https://github.com/ping830616/CITADEL/blob/520304689601ab62b53da9ac8420e22cefe20dcb/TELEMETRY_COLECTION_SCRIPTS/spectre_attack/spectre_poc.c) is preserved. A source file's presence does not prove successful execution or attack success in the saved collection runs. Repository defaults are not recovered historical invocation settings.

## Labels and time

`parse_scenario_workload_from_name` derives the scenario and workload from each filename. `load_telemetry_for_setup` assigns `is_anom = 0` for `BENIGN`, and `1` for every other scenario; it applies that value to every row in the file. If `time_idx` is missing, the loader creates a row index.

Thus, the evaluation uses scenario labels at the file level. It does not recover event onset and end times or independently label voltage excursions, bit flips, or successful speculative leakage. The classification target is the recorded scenario condition, not confirmed physical damage or attack success.

## Suggested manuscript edit

Insert a short “Anomaly provenance and labels” paragraph in the evaluation subsection that introduces DROOP, RH, and SPECTRE. Extend an existing provenance discussion instead of adding another large table. State:

- the preserved telemetry input path and separate synthetic smoke-test mode;
- the available evidence for each scenario;
- the missing historical DROOP arguments and unverified effective voltage change;
- the file-based labeling rule and absence of verified event boundaries.

This clarifies the available evidence but does not resolve the missing experimental settings. If a lab record or original launcher is recovered, update the description from that evidence before claiming a complete induction protocol.
