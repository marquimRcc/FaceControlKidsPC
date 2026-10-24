#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -eq 0 ]]; then
  echo "Execute este script na conta do responsável, sem sudo." >&2
  exit 1
fi
ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
LAUNCHER="/usr/local/bin/facekids-admin-gui"
if [[ ! -x ${LAUNCHER} ]]; then
  LAUNCHER="${ROOT_DIR}/scripts/Abrir-Painel-RegataOS.sh"
fi
ICON="facekids"
if [[ ! -f /usr/share/icons/hicolor/scalable/apps/facekids.svg && ! -f /usr/share/pixmaps/facekids.png ]]; then
  ICON="${ROOT_DIR}/assets/facekids.svg"
fi
APPLICATIONS_DIR=${XDG_DATA_HOME:-"${HOME}/.local/share"}/applications
mkdir -p "${APPLICATIONS_DIR}"
DESKTOP_FILE="${APPLICATIONS_DIR}/facekids-admin.desktop"
cat > "${DESKTOP_FILE}" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=FaceKids — Painel dos pais
Comment=Cadastre crianças e gerencie tempo e horários
Exec=${LAUNCHER}
Icon=${ICON}
Terminal=false
Categories=Settings;Utility;
StartupNotify=true
StartupWMClass=FaceKids
DESKTOP
chmod 0644 "${DESKTOP_FILE}"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${APPLICATIONS_DIR}" >/dev/null 2>&1 || true
fi
echo "Atalho criado: ${DESKTOP_FILE}"
