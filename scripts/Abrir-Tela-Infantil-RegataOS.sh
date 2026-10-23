#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ELECTRON="${ROOT_DIR}/apps/desktop/node_modules/.bin/electron"
if [[ ! -x ${ELECTRON} || ! -f ${ROOT_DIR}/apps/desktop/dist/index.html ]]; then
  echo "A interface FaceKids ainda não foi preparada em ${ROOT_DIR}." >&2
  exit 1
fi
cd "${ROOT_DIR}/apps/desktop"
exec "${ELECTRON}" . --role=child
