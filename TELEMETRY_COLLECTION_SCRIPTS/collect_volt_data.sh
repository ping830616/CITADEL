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
output_file="${output_dir}/voltage_${trial}.csv"

command -v "${RDMSR_BIN}" >/dev/null 2>&1 \
    || collection_error "rdmsr executable not found: ${RDMSR_BIN}"
require_positive_number SAMPLE_COUNT "${sample_count}"
mkdir -p -- "${output_dir}"
printf 'sample_index,timestamp_unix_ns,msr_0x198_raw,cpu_voltage_v\n' > "${output_file}"

for ((sample = 0; sample < sample_count; sample++)); do
    raw="$(run_privileged "${RDMSR_BIN}" 0x198)"
    raw="${raw#0x}"
    [[ "${raw}" =~ ^[0-9A-Fa-f]+$ ]] \
        || collection_error "rdmsr returned a non-hexadecimal value: ${raw}"
    encoded=$(( (0x${raw} >> 32) & 0xffff ))
    voltage="$(awk -v value="${encoded}" 'BEGIN { printf "%.8f", value / 8192.0 }')"
    printf '%s,%s,0x%s,%s\n' \
        "${sample}" "$(collection_timestamp_ns)" "${raw}" "${voltage}" >> "${output_file}"
    if (( sample + 1 < sample_count )); then
        sleep "${VOLTAGE_SAMPLE_INTERVAL_SECONDS}"
    fi
done
