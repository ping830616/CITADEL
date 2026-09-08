#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COLLECTION_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=../collection_common.sh
source "${COLLECTION_ROOT}/collection_common.sh"
load_collection_config
CITADEL_RUN_ID="${CITADEL_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
export CITADEL_RUN_ID

echo "DFT"
date +"%T.%3N"
"${SCRIPT_DIR}/DDR5_RIG_PCM_COLLECT_DFT.sh"
date +"%T.%3N"

sleep "${MASTER_GAP_SECONDS}"
echo "DJ"
date +"%T.%3N"
"${SCRIPT_DIR}/DDR5_RIG_PCM_COLLECT_DJ.sh"
date +"%T.%3N"

sleep "${MASTER_GAP_SECONDS}"

echo "DP"
date +"%T.%3N"
"${SCRIPT_DIR}/DDR5_RIG_PCM_COLLECT_DP.sh"
date +"%T.%3N"

sleep "${MASTER_GAP_SECONDS}"

echo "GL"
date +"%T.%3N"
"${SCRIPT_DIR}/DDR5_RIG_PCM_COLLECT_GL.sh"
date +"%T.%3N"

sleep "${MASTER_GAP_SECONDS}"

echo "GS"
date +"%T.%3N"
"${SCRIPT_DIR}/DDR5_RIG_PCM_COLLECT_GS.sh"
date +"%T.%3N"

sleep "${MASTER_GAP_SECONDS}"

echo "HA"
date +"%T.%3N"
"${SCRIPT_DIR}/DDR5_RIG_PCM_COLLECT_HA.sh"
date +"%T.%3N"

sleep "${MASTER_GAP_SECONDS}"

echo "JA"
date +"%T.%3N"
"${SCRIPT_DIR}/DDR5_RIG_PCM_COLLECT_JA.sh"
date +"%T.%3N"

sleep "${MASTER_GAP_SECONDS}"

echo "MM"
date +"%T.%3N"
"${SCRIPT_DIR}/DDR5_RIG_PCM_COLLECT_MM.sh"
date +"%T.%3N"

sleep "${MASTER_GAP_SECONDS}"

echo "NI"
date +"%T.%3N"
"${SCRIPT_DIR}/DDR5_RIG_PCM_COLLECT_NI.sh"
date +"%T.%3N"

sleep "${MASTER_GAP_SECONDS}"

echo "OE"
date +"%T.%3N"
"${SCRIPT_DIR}/DDR5_RIG_PCM_COLLECT_OE.sh"
date +"%T.%3N"

sleep "${MASTER_GAP_SECONDS}"

echo "PI"
date +"%T.%3N"
"${SCRIPT_DIR}/DDR5_RIG_PCM_COLLECT_PI.sh"
date +"%T.%3N"

sleep "${MASTER_GAP_SECONDS}"

echo "SH"
date +"%T.%3N"
"${SCRIPT_DIR}/DDR5_RIG_PCM_COLLECT_SH.sh"
date +"%T.%3N"

sleep "${MASTER_GAP_SECONDS}"

echo "TR"
date +"%T.%3N"
"${SCRIPT_DIR}/DDR5_RIG_PCM_COLLECT_TR.sh"
date +"%T.%3N"

sleep "${MASTER_GAP_SECONDS}"
