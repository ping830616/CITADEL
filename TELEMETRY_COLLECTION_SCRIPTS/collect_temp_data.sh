#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=collection_env.sh
source "${SCRIPT_DIR}/collection_env.sh"

trial="${1:?usage: collect_temp_data.sh TRIAL OUTPUT_DIRECTORY [SAMPLES]}"
output_directory="${2:?usage: collect_temp_data.sh TRIAL OUTPUT_DIRECTORY [SAMPLES]}"
samples="${3:-${SENSOR_SAMPLES}}"

shopt -s nullglob
temperature_inputs=()
for name_path in /sys/class/hwmon/hwmon*/name; do
    if [[ "$(<"${name_path}")" == "coretemp" ]]; then
        hwmon_directory="$(dirname -- "${name_path}")"
        for input_path in "${hwmon_directory}"/temp*_input; do
            temperature_inputs+=("${input_path}")
        done
    fi
done

if ((${#temperature_inputs[@]} == 0)); then
    echo "No Linux hwmon coretemp inputs were found." >&2
    echo "Load the coretemp driver and verify /sys/class/hwmon before collection." >&2
    exit 1
fi

mkdir -p -- "${output_directory}"
output_file="${output_directory}/temperature_${trial}.csv"
printf '%s\n' 'timestamp_ns,elapsed_s,sample_index,channel,temperature_c,source,status' > "${output_file}"

start_ns="$(date +%s%N)"
for ((sample_index = 0; sample_index < samples; sample_index++)); do
    timestamp_ns="$(date +%s%N)"
    elapsed_s="$(awk -v now="${timestamp_ns}" -v start="${start_ns}" 'BEGIN {printf "%.9f", (now-start)/1000000000}')"

    for input_path in "${temperature_inputs[@]}"; do
        label_path="${input_path%_input}_label"
        channel="$(basename -- "${input_path%_input}")"
        if [[ -r "${label_path}" ]]; then
            channel="$(<"${label_path}")"
        fi
        channel="${channel//,/;}"

        temperature_c=""
        status="read_error"
        if raw_temperature="$(<"${input_path}")" && [[ "${raw_temperature}" =~ ^-?[0-9]+$ ]]; then
            temperature_c="$(awk -v value="${raw_temperature}" 'BEGIN {printf "%.3f", value/1000}')"
            status="ok"
        fi

        printf '%s,%s,%s,%s,%s,%s,%s\n' \
            "${timestamp_ns}" "${elapsed_s}" "${sample_index}" \
            "${channel}" "${temperature_c}" "${input_path}" "${status}" \
            >> "${output_file}"
    done

    if ((sample_index + 1 < samples)); then
        sleep "${SENSOR_INTERVAL_S}"
    fi
done
