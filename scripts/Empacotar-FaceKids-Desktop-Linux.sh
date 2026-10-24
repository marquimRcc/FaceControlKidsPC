#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
OUTPUT=${1:-"${ROOT_DIR}/artifacts/facekids-desktop-linux-x64.tar.gz"}
ARCH=$(uname -m)
if [[ ${ARCH} != x86_64 && ${ARCH} != amd64 ]]; then
  echo "Arquitetura ainda não suportada pelo bundle Electron: ${ARCH}" >&2
  exit 1
fi

PNPM=$(command -v pnpm || true)
if [[ -z ${PNPM} ]]; then
  echo "pnpm não encontrado; instale as dependências antes de empacotar." >&2
  exit 1
fi
ELECTRON_DIR="${ROOT_DIR}/apps/desktop/node_modules/electron/dist"
if [[ ! -x ${ELECTRON_DIR}/electron ]]; then
  echo "Runtime Electron ausente. Execute 'pnpm install' no repositório." >&2
  exit 1
fi

"${PNPM}" --dir "${ROOT_DIR}" build

STAGING=$(mktemp -d)
trap 'rm -rf "${STAGING}"' EXIT
BUNDLE="${STAGING}/facekids-desktop-linux-x64"
install -d -m 0755 "${BUNDLE}/app" "${BUNDLE}/electron" "${BUNDLE}/assets"
cp -a "${ROOT_DIR}/apps/desktop/dist" "${BUNDLE}/app/"
cp -a "${ROOT_DIR}/apps/desktop/dist-electron" "${BUNDLE}/app/"
install -m 0644 "${ROOT_DIR}/apps/desktop/package.json" "${BUNDLE}/app/package.json"
cp -a "${ELECTRON_DIR}/." "${BUNDLE}/electron/"
cp -a "${ROOT_DIR}/assets/." "${BUNDLE}/assets/"
install -m 0755 "${ROOT_DIR}/packaging/install-facekids-desktop-bundle" \
  "${BUNDLE}/install.sh"
install -m 0755 "${ROOT_DIR}/packaging/facekids-admin-gui" \
  "${BUNDLE}/facekids-admin-gui"
install -m 0755 "${ROOT_DIR}/packaging/facekids-child-gui" \
  "${BUNDLE}/facekids-child-gui"
git -C "${ROOT_DIR}" describe --always --dirty > "${BUNDLE}/VERSION"

(
  cd "${BUNDLE}"
  find . \( -type f -o -type l \) ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)
mkdir -p "$(dirname -- "${OUTPUT}")"
tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
  -C "${STAGING}" -czf "${OUTPUT}" facekids-desktop-linux-x64
sha256sum "${OUTPUT}" > "${OUTPUT}.sha256"
echo "Bundle criado: ${OUTPUT}"
echo "Checksum: ${OUTPUT}.sha256"
