#!/usr/bin/env bash

# Shared configuration and helpers for the Intel telemetry collectors.
# Override defaults in collection.env or set COLLECTION_CONFIG to another file.

COLLECTION_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COLLECTION_CONFIG="${COLLECTION_CONFIG:-${COLLECTION_ROOT}/collection.env}"

if [[ -f "${COLLECTION_CONFIG}" ]]; then
    # shellcheck disable=SC1090
    source "${COLLECTION_CONFIG}"
fi

PAMPAR_ROOT="${PAMPAR_ROOT:-}"
PCM_ROOT="${PCM_ROOT:-}"
PCM_BIN="${PCM_BIN:-}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${PWD}}"
ALLOW_OVERWRITE="${ALLOW_OVERWRITE:-NO}"
PCM_INTERVAL_S="${PCM_INTERVAL_S:-0.001}"
PCM_ITERATIONS="${PCM_ITERATIONS:-1000}"
SENSOR_SAMPLES="${SENSOR_SAMPLES:-200}"
SENSOR_INTERVAL_S="${SENSOR_INTERVAL_S:-0.005}"
MSR_CPU="${MSR_CPU:-0}"
MSR_REGISTER="${MSR_REGISTER:-0x198}"
RDMSR_BIN="${RDMSR_BIN:-$(command -v rdmsr 2>/dev/null || true)}"
SUDO_BIN="${SUDO_BIN:-sudo}"

DROOP_BIN="${DROOP_BIN:-${COLLECTION_ROOT}/just_droop/operation}"
ENABLE_DROOP="${ENABLE_DROOP:-NO}"
DROOP_ARGS_DDR4="${DROOP_ARGS_DDR4:-}"
DROOP_ARGS_DDR5="${DROOP_ARGS_DDR5:-}"
GL_COMMAND_DDR4="${GL_COMMAND_DDR4:-}"
GL_COMMAND_DDR5="${GL_COMMAND_DDR5:-}"

require_collection_tools() {
    if [[ -z "${PAMPAR_ROOT}" || ! -d "${PAMPAR_ROOT}" ]]; then
        echo "Set PAMPAR_ROOT to the PAMPAR checkout in ${COLLECTION_CONFIG}." >&2
        return 1
    fi
    if [[ -z "${PCM_BIN}" || ! -x "${PCM_BIN}" ]]; then
        echo "Set PCM_BIN to the Intel PCM executable in ${COLLECTION_CONFIG}." >&2
        return 1
    fi
    mkdir -p -- "${OUTPUT_ROOT}"
}

prepare_output_directory() {
    local target="${1:?output directory is required}"
    local output_root_resolved
    local target_resolved

    if [[ -z "${OUTPUT_ROOT}" || "${OUTPUT_ROOT}" != /* || "${OUTPUT_ROOT}" == "/" ]]; then
        echo "OUTPUT_ROOT must be a non-root absolute path." >&2
        return 1
    fi

    output_root_resolved="$(realpath -m -- "${OUTPUT_ROOT}")"
    target_resolved="$(realpath -m -- "${target}")"

    case "${target_resolved}" in
        "${output_root_resolved}"/*) ;;
        *)
            echo "Refusing output path outside OUTPUT_ROOT: ${target_resolved}" >&2
            return 1
            ;;
    esac

    if [[ -e "${target_resolved}" ]]; then
        if [[ "${ALLOW_OVERWRITE}" != "YES" ]]; then
            echo "Output already exists: ${target_resolved}" >&2
            echo "Choose a new OUTPUT_ROOT or set ALLOW_OVERWRITE=YES." >&2
            return 1
        fi
        rm -rf -- "${target_resolved}"
    fi

    mkdir -p -- "${target_resolved}"
}

run_privileged() {
    if [[ "$(id -u)" -eq 0 ]]; then
        "$@"
    else
        "${SUDO_BIN}" "$@"
    fi
}
