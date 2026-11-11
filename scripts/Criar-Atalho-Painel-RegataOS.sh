#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -eq 0 ]]; then
  echo "Execute este script na conta do responsável, sem sudo." >&2
  exit 1
fi
ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
LAUNCHER="/usr/local/bin/safepckids-admin-gui"
if [[ ! -x ${LAUNCHER} ]]; then
  LAUNCHER="${ROOT_DIR}/scripts/Abrir-Painel-RegataOS.sh"
fi
ICON="safepckids"
if [[ ! -f /usr/share/icons/hicolor/scalable/apps/safepckids.svg && ! -f /usr/share/pixmaps/safepckids.png ]]; then
  ICON="${ROOT_DIR}/assets/safepckids.svg"
fi
APPLICATIONS_DIR=${XDG_DATA_HOME:-"${HOME}/.local/share"}/applications
mkdir -p "${APPLICATIONS_DIR}"
DESKTOP_FILE="${APPLICATIONS_DIR}/safepckids-admin.desktop"
cat > "${DESKTOP_FILE}" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=SafePCKids — Painel dos pais
Comment=Cadastre crianças e gerencie tempo e horários
Exec=${LAUNCHER}
Icon=${ICON}
Terminal=false
Categories=Settings;Utility;
StartupNotify=true
StartupWMClass=SafePCKids
DESKTOP
chmod 0644 "${DESKTOP_FILE}"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${APPLICATIONS_DIR}" >/dev/null 2>&1 || true
fi
echo "Atalho criado: ${DESKTOP_FILE}"
