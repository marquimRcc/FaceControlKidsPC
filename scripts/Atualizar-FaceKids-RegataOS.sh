#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash scripts/Atualizar-FaceKids-RegataOS.sh" >&2
  exit 1
fi
SOURCE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CHILD_USER=${1:-filhos}
ADMIN_GROUP=${2:-wheel}
if [[ ! ${CHILD_USER} =~ ^[a-z_][a-z0-9_.-]*$ ]] || ! getent passwd "${CHILD_USER}" >/dev/null; then
  echo "Conta infantil inválida ou inexistente: ${CHILD_USER}" >&2
  exit 1
fi
if [[ ! ${ADMIN_GROUP} =~ ^[a-z_][a-z0-9_-]*$ ]] || ! getent group "${ADMIN_GROUP}" >/dev/null; then
  echo "Grupo administrador inválido ou inexistente: ${ADMIN_GROUP}" >&2
  exit 1
fi
if [[ ! -x /opt/facekids/venv/bin/python || ! -f /var/lib/facekids/criancas.sqlite3 ]]; then
  echo "Instalação existente não encontrada; use Instalar-FaceKids-RegataOS.sh." >&2
  exit 1
fi
systemctl stop facekids-linux.service
rm -rf /usr/lib/facekids/facekids
cp -a "${SOURCE_DIR}/facekids" /usr/lib/facekids/
chown -R root:root /usr/lib/facekids/facekids

# Atualiza interface desktop se distribuída
if [[ -d "${SOURCE_DIR}/apps/desktop/dist" && -d "${SOURCE_DIR}/apps/desktop/dist-electron" ]]; then
  install -d -m 0755 /opt/facekids/desktop /opt/facekids/desktop/electron /usr/share/icons/hicolor/scalable/apps /usr/share/pixmaps
  rm -rf /opt/facekids/desktop/dist /opt/facekids/desktop/dist-electron
  cp -a "${SOURCE_DIR}/apps/desktop/dist" /opt/facekids/desktop/
  cp -a "${SOURCE_DIR}/apps/desktop/dist-electron" /opt/facekids/desktop/
  install -m 0644 "${SOURCE_DIR}/apps/desktop/package.json" /opt/facekids/desktop/package.json
  if [[ -d "${SOURCE_DIR}/apps/desktop/node_modules/electron/dist" ]]; then
    cp -a "${SOURCE_DIR}/apps/desktop/node_modules/electron/dist/." /opt/facekids/desktop/electron/
    chmod 0755 /opt/facekids/desktop/electron/electron /opt/facekids/desktop/electron/chrome_crashpad_handler || true
  fi
  install -d -m 0755 /opt/facekids/desktop/assets
  cp -a "${SOURCE_DIR}/assets/." /opt/facekids/desktop/assets/
  install -m 0644 "${SOURCE_DIR}/assets/facekids.svg" /usr/share/icons/hicolor/scalable/apps/facekids.svg
  install -m 0644 "${SOURCE_DIR}/assets/facekids-256.png" /usr/share/pixmaps/facekids.png
  install -m 0755 "${SOURCE_DIR}/packaging/facekids-admin-gui" /usr/local/bin/facekids-admin-gui
  install -m 0755 "${SOURCE_DIR}/packaging/facekids-child-gui" /usr/local/bin/facekids-child-gui
  chown -R root:root /opt/facekids/desktop
fi
install -m 0644 "${SOURCE_DIR}/packaging/facekids-linux.service" /etc/systemd/system/facekids-linux.service
sed -i "s/--user filhos/--user ${CHILD_USER}/" /etc/systemd/system/facekids-linux.service
sed -i "s/--admin-group wheel/--admin-group ${ADMIN_GROUP}/" /etc/systemd/system/facekids-linux.service
sed -i "s/^Group=wheel/Group=${ADMIN_GROUP}/" /etc/systemd/system/facekids-linux.service
systemctl daemon-reload
systemctl restart facekids-linux.service
systemctl --no-pager --full status facekids-linux.service
echo "FaceKids atualizado; banco biométrico e quotas preservados."
