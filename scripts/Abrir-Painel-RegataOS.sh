#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ELECTRON="${ROOT_DIR}/apps/desktop/node_modules/.bin/electron"
if [[ ! -x ${ELECTRON} ]]; then
  echo "Dependências da interface ausentes. Execute 'pnpm install' em ${ROOT_DIR}." >&2
  exit 1
fi
if [[ ! -f ${ROOT_DIR}/apps/desktop/dist/index.html ]]; then
  PNPM=$(command -v pnpm || true)
  if [[ -z ${PNPM} ]]; then
    echo "Build da interface ausente e pnpm não foi encontrado." >&2
    exit 1
  fi
  "${PNPM}" --dir "${ROOT_DIR}" build
fi
cd "${ROOT_DIR}/apps/desktop"
exec "${ELECTRON}" . --role=admin
