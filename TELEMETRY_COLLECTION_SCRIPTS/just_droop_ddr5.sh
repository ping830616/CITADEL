#!/usr/bin/env bash
set -euo pipefail

COLLECTION_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COLLECTION_CALLER="${BASH_SOURCE[0]}"
# shellcheck source=collection_common.sh
source "${COLLECTION_ROOT}/collection_common.sh"
load_collection_config

[[ "${CITADEL_ENABLE_DROOP:-0}" == "1" ]] \
    || collection_error "DROOP is disabled. Set CITADEL_ENABLE_DROOP=1 only after hardware-specific review."
: "${DROOP_DDR5_START_MV:?Set DROOP_DDR5_START_MV in collection_config.sh.}"
: "${DROOP_DDR5_END_MV:?Set DROOP_DDR5_END_MV in collection_config.sh.}"
: "${DROOP_DDR5_STEP_MV:?Set DROOP_DDR5_STEP_MV in collection_config.sh.}"
if (( DROOP_DDR5_START_MV >= 0 || DROOP_DDR5_END_MV >= DROOP_DDR5_START_MV || DROOP_DDR5_STEP_MV <= 0 )); then
    collection_error "DDR5 offsets require a negative start, a more negative end, and a positive step magnitude."
fi

DROOP_OPERATION_BIN="${DROOP_OPERATION_BIN:-${COLLECTION_ROOT}/just_droop/operation}"
[[ -x "${DROOP_OPERATION_BIN}" ]] \
    || collection_error "Build the DROOP helper first: make -C ${COLLECTION_ROOT}/just_droop clean all"

printf 'WARNING: writing DDR5 voltage offsets through MSR 0x150.\n' >&2
run_privileged "${DROOP_OPERATION_BIN}" \
    -s "${DROOP_DDR5_START_MV}" \
    -e "${DROOP_DDR5_END_MV}" \
    -v "${DROOP_DDR5_STEP_MV}"
