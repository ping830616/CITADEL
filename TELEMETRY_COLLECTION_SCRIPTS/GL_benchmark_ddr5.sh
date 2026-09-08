#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=collection_env.sh
source "${SCRIPT_DIR}/collection_env.sh"

if [[ -z "${GL_COMMAND_DDR5}" ]]; then
    echo "Set GL_COMMAND_DDR5 to the verified DDR5 Game of Life command." >&2
    exit 1
fi

exec bash -lc "${GL_COMMAND_DDR5}"
