#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash scripts/Criar-Tela-Infantil-RegataOS.sh [usuario]" >&2
  exit 1
fi
ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CHILD_USER=${1:-filhos}
if [[ ! ${CHILD_USER} =~ ^[a-z_][a-z0-9_.-]*$ ]]; then
  echo "Conta infantil inválida: ${CHILD_USER}" >&2
  exit 1
fi
ACCOUNT=$(getent passwd "${CHILD_USER}" || true)
if [[ -z ${ACCOUNT} ]]; then
  echo "Conta infantil inexistente: ${CHILD_USER}" >&2
  exit 1
fi
CHILD_HOME=$(cut -d: -f6 <<<"${ACCOUNT}")
CHILD_GROUP=$(id -gn "${CHILD_USER}")
LAUNCHER="/usr/local/bin/facekids-child-gui"
if [[ ! -x ${LAUNCHER} ]]; then
  LAUNCHER="${ROOT_DIR}/scripts/Abrir-Tela-Infantil-RegataOS.sh"
fi
if [[ ! -x ${LAUNCHER} ]]; then
  echo "Lançador infantil ausente ou sem permissão de execução (${LAUNCHER})." >&2
  exit 1
fi
ICON="facekids"
if [[ ! -f /usr/share/icons/hicolor/scalable/apps/facekids.svg && ! -f /usr/share/pixmaps/facekids.png ]]; then
  ICON="${ROOT_DIR}/assets/facekids.svg"
fi
APPLICATIONS="${CHILD_HOME}/.local/share/applications"
AUTOSTART="${CHILD_HOME}/.config/autostart"
install -d -m 0755 -o "${CHILD_USER}" -g "${CHILD_GROUP}" "${APPLICATIONS}" "${AUTOSTART}"
for destination in "${APPLICATIONS}/facekids-child.desktop" "${AUTOSTART}/facekids-child.desktop"; do
  cat > "${destination}" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=FaceKids — Meu tempo
Comment=Mostra a criança reconhecida e o tempo disponível
Exec=${LAUNCHER}
Icon=${ICON}
Terminal=false
Categories=Utility;
StartupNotify=true
StartupWMClass=FaceKids
X-KDE-autostart-after=panel
DESKTOP
  chown "${CHILD_USER}:${CHILD_GROUP}" "${destination}"
  chmod 0644 "${destination}"
done
echo "Tela infantil instalada para ${CHILD_USER}; ela abrirá ao iniciar a sessão."
