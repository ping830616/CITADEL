#!/usr/bin/env bash
set -euo pipefail

COLLECTION_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COLLECTION_CALLER="${BASH_SOURCE[0]}"
# shellcheck source=collection_common.sh
source "${COLLECTION_ROOT}/collection_common.sh"
load_collection_config

if [[ "$#" -ne 3 ]]; then
    printf 'Usage: %s TRIAL OUTPUT_DIRECTORY SAMPLE_COUNT\n' "$(basename -- "$0")" >&2
    exit 2
fi

trial="$1"
output_dir="$2"
sample_count="$3"
output_file="${output_dir}/temperature_${trial}.csv"

command -v "${SENSORS_BIN}" >/dev/null 2>&1 \
    || collection_error "lm-sensors executable not found: ${SENSORS_BIN}"
require_positive_number SAMPLE_COUNT "${sample_count}"
mkdir -p -- "${output_dir}"
printf 'sample_index,timestamp_unix_ns,chip,sensor_label,attribute,temperature_c\n' > "${output_file}"

for ((sample = 0; sample < sample_count; sample++)); do
    timestamp="$(collection_timestamp_ns)"
    sensor_output="$("${SENSORS_BIN}" -u)"
    parsed="$(printf '%s\n' "${sensor_output}" | awk -v sample="${sample}" -v timestamp="${timestamp}" '
        /^[^[:space:]:]+$/ {
            chip=$0
            next
        }
        /^[[:space:]]+[^[:space:]].*:$/ {
            label=$0
            sub(/^[[:space:]]+/, "", label)
            sub(/:$/, "", label)
            next
        }
        /^[[:space:]]+temp[0-9]+_input:/ {
            attribute=$1
            sub(/:$/, "", attribute)
            value=$2
            gsub(/"/, "\"\"", chip)
            gsub(/"/, "\"\"", label)
            printf "%s,%s,\"%s\",\"%s\",%s,%s\n", sample, timestamp, chip, label, attribute, value
        }
    ')"
    [[ -n "${parsed}" ]] \
        || collection_error "sensors -u returned no temp*_input channels."
    printf '%s\n' "${parsed}" >> "${output_file}"
    if (( sample + 1 < sample_count )); then
        sleep "${TEMPERATURE_SAMPLE_INTERVAL_SECONDS}"
    fi
done
