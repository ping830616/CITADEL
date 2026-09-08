#!/usr/bin/env bash

COLLECTION_ROOT="${COLLECTION_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)}"
COLLECTION_CALLER="${COLLECTION_CALLER:-${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}}"

collection_error() {
    printf 'CITADEL collection error: %s\n' "$*" >&2
    return 1
}

collection_timestamp_ns() {
    local value
    value="$(date +%s%N)"
    if [[ "${value}" == *N* ]]; then
        value="$(date +%s)000000000"
    fi
    printf '%s\n' "${value}"
}

require_positive_number() {
    local name="$1"
    local value="$2"
    awk -v value="${value}" 'BEGIN { exit !(value + 0 > 0) }' \
        || collection_error "${name} must be greater than zero (received '${value}')."
}

load_collection_config() {
    local config_path
    config_path="${CITADEL_COLLECTION_CONFIG:-${COLLECTION_ROOT}/collection_config.sh}"
    if [[ -f "${config_path}" ]]; then
        # shellcheck source=/dev/null
        source "${config_path}"
    fi

    : "${PAMPAR_ROOT:?Set PAMPAR_ROOT in collection_config.sh or the environment.}"
    : "${PCM_BIN:?Set PCM_BIN in collection_config.sh or the environment.}"

    COLLECTION_OUTPUT_ROOT="${COLLECTION_OUTPUT_ROOT:-${COLLECTION_ROOT}/output}"
    COLLECTION_TRIALS="${COLLECTION_TRIALS:-10}"
    PCM_INTERVAL_SECONDS="${PCM_INTERVAL_SECONDS:-0.001}"
    PCM_ITERATIONS="${PCM_ITERATIONS:-1000}"
    VOLTAGE_SAMPLES="${VOLTAGE_SAMPLES:-200}"
    TEMPERATURE_SAMPLES="${TEMPERATURE_SAMPLES:-200}"
    VOLTAGE_SAMPLE_INTERVAL_SECONDS="${VOLTAGE_SAMPLE_INTERVAL_SECONDS:-0.005}"
    TEMPERATURE_SAMPLE_INTERVAL_SECONDS="${TEMPERATURE_SAMPLE_INTERVAL_SECONDS:-0.005}"
    COLLECTION_PRIVILEGE_COMMAND="${COLLECTION_PRIVILEGE_COMMAND-sudo}"
    RDMSR_BIN="${RDMSR_BIN:-rdmsr}"
    SENSORS_BIN="${SENSORS_BIN:-sensors}"
    COLLECTION_STARTUP_SECONDS="${COLLECTION_STARTUP_SECONDS:-5}"
    BENIGN_PRETRIAL_SECONDS="${BENIGN_PRETRIAL_SECONDS:-10}"
    BENIGN_POSTTRIAL_SECONDS="${BENIGN_POSTTRIAL_SECONDS:-30}"
    DROOP_POSTTRIAL_SECONDS="${DROOP_POSTTRIAL_SECONDS:-40}"
    MASTER_GAP_SECONDS="${MASTER_GAP_SECONDS:-3}"

    require_positive_number COLLECTION_TRIALS "${COLLECTION_TRIALS}"
    require_positive_number PCM_INTERVAL_SECONDS "${PCM_INTERVAL_SECONDS}"
    require_positive_number PCM_ITERATIONS "${PCM_ITERATIONS}"
    require_positive_number VOLTAGE_SAMPLES "${VOLTAGE_SAMPLES}"
    require_positive_number TEMPERATURE_SAMPLES "${TEMPERATURE_SAMPLES}"
    require_positive_number VOLTAGE_SAMPLE_INTERVAL_SECONDS "${VOLTAGE_SAMPLE_INTERVAL_SECONDS}"
    require_positive_number TEMPERATURE_SAMPLE_INTERVAL_SECONDS "${TEMPERATURE_SAMPLE_INTERVAL_SECONDS}"

    [[ -d "${PAMPAR_ROOT}" ]] \
        || collection_error "PAMPAR_ROOT is not a directory: ${PAMPAR_ROOT}"
    [[ -x "${PCM_BIN}" ]] \
        || collection_error "PCM_BIN is not executable: ${PCM_BIN}"
}

run_privileged() {
    if [[ -n "${COLLECTION_PRIVILEGE_COMMAND:-}" ]]; then
        "${COLLECTION_PRIVILEGE_COMMAND}" "$@"
    else
        "$@"
    fi
}

collection_platform() {
    local name
    name="$(basename -- "${COLLECTION_CALLER}")"
    case "${name}" in
        DDR4_*) printf 'DDR4\n' ;;
        DDR5_*) printf 'DDR5\n' ;;
        *) collection_error "Cannot infer DDR4 or DDR5 from ${name}." ;;
    esac
}

collection_condition() {
    local name
    name="$(basename -- "${COLLECTION_CALLER}")"
    if [[ "${name}" == *_DROOP.sh ]]; then
        printf 'DROOP\n'
    else
        printf 'benign\n'
    fi
}

git_revision_or_unavailable() {
    local path="$1"
    git -C "${path}" rev-parse HEAD 2>/dev/null || printf 'unavailable\n'
}

verify_expected_revision() {
    local label="$1"
    local path="$2"
    local expected="$3"
    local actual
    [[ -z "${expected}" ]] && return 0
    actual="$(git_revision_or_unavailable "${path}")"
    if [[ "${actual}" != "${expected}" ]]; then
        collection_error "${label} revision ${actual} does not match documented revision ${expected}."
    fi
}

record_collection_metadata() {
    local output_dir="$1"
    local platform="$2"
    local condition="$3"
    local metadata="${output_dir}/collection_metadata.txt"
    local pcm_root pcm_version
    pcm_root="${PCM_ROOT:-$(cd -- "$(dirname -- "${PCM_BIN}")/../.." 2>/dev/null && pwd || true)}"
    pcm_version="$("${PCM_BIN}" --version 2>&1 | sed -n '1p' || true)"

    {
        printf 'schema_version=1\n'
        printf 'created_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf 'platform=%s\n' "${platform}"
        printf 'condition=%s\n' "${condition}"
        printf 'collection_run_id=%s\n' "${CITADEL_RUN_ID}"
        printf 'collection_script=%s\n' "$(basename -- "${COLLECTION_CALLER}")"
        printf 'pampar_root=%s\n' "${PAMPAR_ROOT}"
        printf 'pampar_commit=%s\n' "$(git_revision_or_unavailable "${PAMPAR_ROOT}")"
        printf 'pampar_expected_commit=%s\n' "${PAMPAR_EXPECTED_COMMIT:-not_set}"
        printf 'pcm_binary=%s\n' "${PCM_BIN}"
        printf 'pcm_version=%s\n' "${pcm_version:-unavailable}"
        printf 'pcm_commit=%s\n' "$(git_revision_or_unavailable "${pcm_root:-/nonexistent}")"
        printf 'pcm_expected_commit=%s\n' "${PCM_EXPECTED_COMMIT:-not_set}"
        printf 'pcm_requested_interval_s=%s\n' "${PCM_INTERVAL_SECONDS}"
        printf 'pcm_iterations=%s\n' "${PCM_ITERATIONS}"
        printf 'voltage_interface=MSR_0x198_via_rdmsr\n'
        printf 'voltage_unit=V\n'
        printf 'voltage_samples=%s\n' "${VOLTAGE_SAMPLES}"
        printf 'voltage_requested_interval_s=%s\n' "${VOLTAGE_SAMPLE_INTERVAL_SECONDS}"
        printf 'temperature_interface=lm_sensors_sensors_u\n'
        printf 'temperature_unit=degree_Celsius\n'
        printf 'temperature_samples=%s\n' "${TEMPERATURE_SAMPLES}"
        printf 'temperature_requested_interval_s=%s\n' "${TEMPERATURE_SAMPLE_INTERVAL_SECONDS}"
        printf 'collection_startup_delay_s=%s\n' "${COLLECTION_STARTUP_SECONDS}"
        printf 'benign_pretrial_delay_s=%s\n' "${BENIGN_PRETRIAL_SECONDS}"
        printf 'benign_posttrial_delay_s=%s\n' "${BENIGN_POSTTRIAL_SECONDS}"
        printf 'droop_posttrial_delay_s=%s\n' "${DROOP_POSTTRIAL_SECONDS}"
        printf 'privilege_command=%s\n' "${COLLECTION_PRIVILEGE_COMMAND:-none}"
        printf 'hostname=%s\n' "$(hostname)"
        printf 'kernel=%s\n' "$(uname -srmo)"
    } > "${metadata}"
}

prepare_output_dir() {
    local workload="$1"
    local platform condition output_dir pcm_root
    platform="$(collection_platform)"
    condition="$(collection_condition)"
    CITADEL_RUN_ID="${CITADEL_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
    export CITADEL_RUN_ID
    output_dir="${COLLECTION_OUTPUT_ROOT}/${CITADEL_RUN_ID}/${platform}/${condition}/${workload}"

    if [[ -e "${output_dir}" ]]; then
        collection_error "Output already exists: ${output_dir}. Choose a new CITADEL_RUN_ID."
    fi
    mkdir -p -- "${output_dir}"

    verify_expected_revision PAMPAR "${PAMPAR_ROOT}" "${PAMPAR_EXPECTED_COMMIT:-}"
    pcm_root="${PCM_ROOT:-$(cd -- "$(dirname -- "${PCM_BIN}")/../.." 2>/dev/null && pwd || true)}"
    verify_expected_revision PCM "${pcm_root:-/nonexistent}" "${PCM_EXPECTED_COMMIT:-}"
    record_collection_metadata "${output_dir}" "${platform}" "${condition}"
    printf '%s\n' "${output_dir}"
}

trial_log_event() {
    local output_dir="$1"
    local trial="$2"
    local event="$3"
    local details="${4:-}"
    local log="${output_dir}/trial_events.csv"
    if [[ ! -e "${log}" ]]; then
        printf 'timestamp_unix_ns,trial,event,details\n' > "${log}"
    fi
    details="${details//\"/\"\"}"
    printf '%s,%s,%s,"%s"\n' "$(collection_timestamp_ns)" "${trial}" "${event}" "${details}" >> "${log}"
}

wait_for_collection_pids() {
    local output_dir="$1"
    local trial="$2"
    shift 2
    local pid status=0
    trial_log_event "${output_dir}" "${trial}" process_wait "pids=$*"
    for pid in "$@"; do
        if ! wait "${pid}"; then
            status=1
            trial_log_event "${output_dir}" "${trial}" process_failed "pid=${pid}"
        fi
    done
    if [[ "${status}" -eq 0 ]]; then
        trial_log_event "${output_dir}" "${trial}" trial_complete all_processes_completed
    else
        trial_log_event "${output_dir}" "${trial}" trial_failed one_or_more_processes_failed
    fi
    collection_pids=()
    return "${status}"
}

terminate_collection_pids() {
    local pid
    for pid in "${collection_pids[@]:-}"; do
        if kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" 2>/dev/null || true
        fi
    done
}
