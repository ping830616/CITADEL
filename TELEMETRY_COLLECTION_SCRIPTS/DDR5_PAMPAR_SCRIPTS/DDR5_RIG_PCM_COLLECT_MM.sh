#!/usr/bin/env bash
# Author | Eduardo Ortega
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COLLECTION_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
COLLECTION_CALLER="${BASH_SOURCE[0]}"
# shellcheck source=../collection_common.sh
source "${COLLECTION_ROOT}/collection_common.sh"
load_collection_config

collection_pids=()
trap terminate_collection_pids EXIT
trap 'terminate_collection_pids; exit 130' INT TERM
folder="mm"
folder="$(prepare_output_dir "${folder}")"
dp_pcm="${PCM_ITERATIONS}"
dp_msr="${VOLTAGE_SAMPLES}"
dp_sensor="${TEMPERATURE_SAMPLES}"
echo "***PAMPAR MM***"
sleep "${COLLECTION_STARTUP_SECONDS}"
for ((i = 1; i <= COLLECTION_TRIALS; i++))
do
    echo "STARTING TRACE $i"
    collection_pids=()
    trial_log_event "${folder}" "${i}" trial_start
    sleep "${BENIGN_PRETRIAL_SECONDS}"
    trial_log_event "${folder}" "${i}" workload_and_collectors_launch_begin
    "${PAMPAR_ROOT}/Apps/MM/pthread" 16 5000 &
    collection_pids+=("$!")
    run_privileged "${PCM_BIN}" "${PCM_INTERVAL_SECONDS}" -i="${dp_pcm}" -csv="${folder}/log_${i}.csv" &
    collection_pids+=("$!")
    "${COLLECTION_ROOT}/collect_volt_data.sh" "${i}" "${folder}" "${dp_msr}" &
    collection_pids+=("$!")
    "${COLLECTION_ROOT}/collect_temp_data.sh" "${i}" "${folder}" "${dp_sensor}" &
    collection_pids+=("$!")
    wait_for_collection_pids "${folder}" "${i}" "${collection_pids[@]}"
    sleep "${BENIGN_POSTTRIAL_SECONDS}"
done
