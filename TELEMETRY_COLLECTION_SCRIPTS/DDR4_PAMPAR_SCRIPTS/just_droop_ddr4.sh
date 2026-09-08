#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../collection_env.sh
source "${SCRIPT_DIR}/../collection_env.sh"

if [[ "${ENABLE_DROOP}" != "YES" ]]; then
    echo "DROOP collection is disabled. Set ENABLE_DROOP=YES after reviewing the safety warning." >&2
    exit 1
fi
if [[ -z "${DROOP_ARGS_DDR4}" ]]; then
    echo "Set DROOP_ARGS_DDR4 to the verified arguments from the original DDR4 experiment." >&2
    exit 1
fi
if [[ ! -x "${DROOP_BIN}" ]]; then
    echo "DROOP_BIN is not executable: ${DROOP_BIN}" >&2
    exit 1
fi

read -r -a droop_arguments <<< "${DROOP_ARGS_DDR4}"
run_privileged "${DROOP_BIN}" "${droop_arguments[@]}"
