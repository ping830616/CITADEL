#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=collection_env.sh
source "${SCRIPT_DIR}/collection_env.sh"

trial="${1:?usage: collect_volt_data.sh TRIAL OUTPUT_DIRECTORY [SAMPLES]}"
output_directory="${2:?usage: collect_volt_data.sh TRIAL OUTPUT_DIRECTORY [SAMPLES]}"
samples="${3:-${SENSOR_SAMPLES}}"

if [[ -z "${RDMSR_BIN}" || ! -x "${RDMSR_BIN}" ]]; then
    echo "rdmsr is unavailable. Install msr-tools and set RDMSR_BIN." >&2
    exit 1
fi

mkdir -p -- "${output_directory}"
output_file="${output_directory}/voltage_${trial}.csv"
printf '%s\n' 'timestamp_ns,elapsed_s,sample_index,msr,raw_hex,voltage_v,status' > "${output_file}"

start_ns="$(date +%s%N)"
for ((sample_index = 0; sample_index < samples; sample_index++)); do
    timestamp_ns="$(date +%s%N)"
    elapsed_s="$(awk -v now="${timestamp_ns}" -v start="${start_ns}" 'BEGIN {printf "%.9f", (now-start)/1000000000}')"
    raw_hex=""
    voltage_v=""
    status="read_error"

    if raw_hex="$(run_privileged "${RDMSR_BIN}" -p "${MSR_CPU}" "${MSR_REGISTER}" 2>/dev/null)"; then
        raw_hex="${raw_hex#0x}"
        raw_hex="${raw_hex//[[:space:]]/}"
        if [[ "${raw_hex}" =~ ^[0-9A-Fa-f]+$ ]]; then
            raw_value=$((16#${raw_hex}))
            voltage_code=$(((raw_value >> 32) & 0xffff))
            voltage_v="$(awk -v code="${voltage_code}" 'BEGIN {printf "%.6f", code/8192}')"
            status="ok"
        else
            status="parse_error"
        fi
    fi

    printf '%s,%s,%s,%s,%s,%s,%s\n' \
        "${timestamp_ns}" "${elapsed_s}" "${sample_index}" \
        "${MSR_REGISTER}" "${raw_hex}" "${voltage_v}" "${status}" \
        >> "${output_file}"

    if ((sample_index + 1 < samples)); then
        sleep "${SENSOR_INTERVAL_S}"
    fi
done
