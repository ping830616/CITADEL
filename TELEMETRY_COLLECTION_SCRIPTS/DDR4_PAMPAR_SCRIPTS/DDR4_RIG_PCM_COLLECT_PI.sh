#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../collection_env.sh
source "${SCRIPT_DIR}/../collection_env.sh"
require_collection_tools

# Author | Eduardo Ortega
folder="${OUTPUT_ROOT}/pi"
prepare_output_directory "$folder"
dp_pcm="${PCM_ITERATIONS}"
dp_msr="${SENSOR_SAMPLES}"
dp_sensor="$dp_msr"
echo "***PAMPAR PI***"
sleep 5
for i in {1..10}
do
    echo "STARTING TRACE $i"
    sleep 10
    "${PAMPAR_ROOT}/Apps/PI/pthread" 4 4000000000 &
    run_privileged "${PCM_BIN}" "${PCM_INTERVAL_S}" -i="${dp_pcm}" -csv="${folder}/log_${i}.csv" &
    "${COLLECTION_ROOT}/collect_volt_data.sh" "$i" "$folder" "$dp_msr" &
    "${COLLECTION_ROOT}/collect_temp_data.sh" "$i" "$folder" "$dp_sensor"
    sleep 30
done
