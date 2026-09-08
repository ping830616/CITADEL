#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=collection_env.sh
source "${SCRIPT_DIR}/collection_env.sh"

output_file="${1:-${OUTPUT_ROOT}/collection_environment.tsv}"
mkdir -p -- "$(dirname -- "${output_file}")"
printf '%s\n' $'field\tvalue' > "${output_file}"

record() {
    local field="$1"
    local value="$2"
    value="${value//$'\t'/ }"
    value="${value//$'\n'/ }"
    printf '%s\t%s\n' "${field}" "${value:-not_available}" >> "${output_file}"
}

git_head() {
    local repository="$1"
    if [[ -n "${repository}" && -d "${repository}/.git" ]]; then
        git -C "${repository}" rev-parse HEAD 2>/dev/null || true
    fi
}

git_dirty() {
    local repository="$1"
    if [[ -n "${repository}" && -d "${repository}/.git" ]]; then
        if [[ -n "$(git -C "${repository}" status --porcelain 2>/dev/null)" ]]; then
            printf '%s' yes
        else
            printf '%s' no
        fi
    fi
}

file_sha256() {
    local file="$1"
    if [[ -n "${file}" && -f "${file}" ]]; then
        sha256sum -- "${file}" 2>/dev/null | awk '{print $1}' || true
    fi
}

command_version() {
    local executable="$1"
    if [[ -n "${executable}" && -x "${executable}" ]]; then
        "${executable}" --version 2>&1 | head -n 1 || true
    fi
}

record timestamp_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
record kernel "$(uname -srvmo)"
record os_release "$(. /etc/os-release 2>/dev/null && printf '%s %s' "${NAME:-}" "${VERSION_ID:-}" || true)"
record cpu_model "$(lscpu 2>/dev/null | awk -F: '/Model name/ {sub(/^[[:space:]]+/, "", $2); print $2; exit}')"
record pcm_root "${PCM_ROOT}"
record pcm_binary "${PCM_BIN}"
record pcm_version "$(command_version "${PCM_BIN}")"
record pcm_binary_sha256 "$(file_sha256 "${PCM_BIN}")"
record pcm_git_commit "$(git_head "${PCM_ROOT}")"
record pcm_git_dirty "$(git_dirty "${PCM_ROOT}")"
record pampar_root "${PAMPAR_ROOT}"
record pampar_git_commit "$(git_head "${PAMPAR_ROOT}")"
record pampar_git_dirty "$(git_dirty "${PAMPAR_ROOT}")"
record plundervolt_git_commit "$(git_head "${PLUNDERVOLT_ROOT:-}")"
record trrespass_git_commit "$(git_head "${TRRESPASS_ROOT:-}")"
record spectre_git_commit "$(git_head "${SPECTRE_ROOT:-}")"
record droop_binary "${DROOP_BIN}"
record droop_binary_sha256 "$(file_sha256 "${DROOP_BIN}")"
record droop_args_ddr4 "${DROOP_ARGS_DDR4}"
record droop_args_ddr5 "${DROOP_ARGS_DDR5}"
record game_of_life_command_ddr4 "${GL_COMMAND_DDR4}"
record game_of_life_command_ddr5 "${GL_COMMAND_DDR5}"
record rdmsr_binary "${RDMSR_BIN}"
record rdmsr_version "$(command_version "${RDMSR_BIN}")"
record pcm_interval_s "${PCM_INTERVAL_S}"
record pcm_iterations "${PCM_ITERATIONS}"
record sensor_samples "${SENSOR_SAMPLES}"
record sensor_interval_s "${SENSOR_INTERVAL_S}"
record msr_cpu "${MSR_CPU}"
record msr_register "${MSR_REGISTER}"

echo "Wrote ${output_file}"
