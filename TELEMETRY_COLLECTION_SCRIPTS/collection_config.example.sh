#!/usr/bin/env bash
# Copy this file to collection_config.sh and edit the machine-specific paths.
# collection_config.sh is ignored by Git.

# External tools. The documented revisions are reproducible reference versions
# for new collections; the revisions used for the preserved historical traces
# were not recorded in the original artifact.
PAMPAR_ROOT="/absolute/path/to/PAMPAR"
PAMPAR_EXPECTED_COMMIT="568430be779f5bf1d0bfddca35bc796adc215262"

PCM_ROOT="/absolute/path/to/pcm"
PCM_BIN="${PCM_ROOT}/build/bin/pcm"
PCM_EXPECTED_COMMIT="ee01a82b75f9a570c005303cd9ec1a2032c2e88b"

# Output and trial controls.
COLLECTION_OUTPUT_ROOT="${COLLECTION_ROOT}/output"
COLLECTION_TRIALS=10
PCM_INTERVAL_SECONDS="0.001"
PCM_ITERATIONS=1000
VOLTAGE_SAMPLES=200
TEMPERATURE_SAMPLES=200

# These are explicit settings for a new collection. The original auxiliary
# collector intervals were not preserved, so set them to the values used on
# the target machine and retain collection_metadata.txt with the results.
VOLTAGE_SAMPLE_INTERVAL_SECONDS="0.005"
TEMPERATURE_SAMPLE_INTERVAL_SECONDS="0.005"

# Privileged PCM and MSR access. Set to an empty string only when the current
# user already has the required permissions.
COLLECTION_PRIVILEGE_COMMAND="sudo"
RDMSR_BIN="rdmsr"

# The restored temperature collector uses lm-sensors and records every
# temp*_input value reported by `sensors -u`, including the chip and label.
SENSORS_BIN="sensors"

# The original SH input image was not included in PAMPAR or X-OCTANE. Supply
# the exact image and dimensions before running an SH collection.
PAMPAR_SH_INPUT="/absolute/path/to/moon_3000.jpg"
PAMPAR_SH_HEIGHT=3000
PAMPAR_SH_WIDTH=3000

# Voltage-droop collection is disabled unless explicitly enabled. The C helper
# writes voltage offsets through MSR 0x150 and can destabilize the machine.
CITADEL_ENABLE_DROOP=0
DROOP_OPERATION_BIN="${COLLECTION_ROOT}/just_droop/operation"

# No historical offset values were committed. Do not fill these fields by
# guesswork. Use values approved for each specific processor and test setup.
DROOP_DDR4_START_MV=""
DROOP_DDR4_END_MV=""
DROOP_DDR4_STEP_MV=""
DROOP_DDR5_START_MV=""
DROOP_DDR5_END_MV=""
DROOP_DDR5_STEP_MV=""

# Delays retained from the original workload scripts.
COLLECTION_STARTUP_SECONDS=5
BENIGN_PRETRIAL_SECONDS=10
BENIGN_POSTTRIAL_SECONDS=30
DROOP_POSTTRIAL_SECONDS=40
MASTER_GAP_SECONDS=3
