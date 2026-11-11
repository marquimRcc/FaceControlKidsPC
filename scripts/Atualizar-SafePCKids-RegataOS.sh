#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash scripts/Atualizar-SafePCKids-RegataOS.sh" >&2
  exit 1
fi
SOURCE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CHILD_USER=${1:-filhos}
ADMIN_GROUP=${2:-}
if [[ -z "${ADMIN_GROUP}" ]]; then
  if getent group wheel >/dev/null; then
    ADMIN_GROUP="wheel"
  elif getent group sudo >/dev/null; then
    ADMIN_GROUP="sudo"
  else
    ADMIN_GROUP="wheel"
  fi
fi
if [[ ! ${CHILD_USER} =~ ^[a-z_][a-z0-9_.-]*$ ]] || ! getent passwd "${CHILD_USER}" >/dev/null; then
  echo "Conta infantil inválida ou inexistente: ${CHILD_USER}" >&2
  exit 1
fi
if [[ ! ${ADMIN_GROUP} =~ ^[a-z_][a-z0-9_-]*$ ]] || ! getent group "${ADMIN_GROUP}" >/dev/null; then
  echo "Grupo administrador inválido ou inexistente: ${ADMIN_GROUP}" >&2
  exit 1
fi
CHILD_GROUP=$(id -gn "${CHILD_USER}")
if [[ ! -x /opt/safepckids/venv/bin/python || ! -f /var/lib/safepckids/criancas.sqlite3 ]]; then
  echo "Instalação existente não encontrada; use Instalar-SafePCKids-RegataOS.sh." >&2
  exit 1
fi
systemctl stop safepckids-linux.service
rm -rf /usr/lib/safepckids/safepckids
cp -a "${SOURCE_DIR}/safepckids" /usr/lib/safepckids/
chown -R root:root /usr/lib/safepckids/safepckids

# Atualiza interface desktop se distribuída
if [[ -d "${SOURCE_DIR}/apps/desktop/dist" && -d "${SOURCE_DIR}/apps/desktop/dist-electron" ]]; then
  install -d -m 0755 /opt/safepckids/desktop /opt/safepckids/desktop/electron /usr/share/icons/hicolor/scalable/apps /usr/share/pixmaps
  rm -rf /opt/safepckids/desktop/dist /opt/safepckids/desktop/dist-electron
  cp -a "${SOURCE_DIR}/apps/desktop/dist" /opt/safepckids/desktop/
  cp -a "${SOURCE_DIR}/apps/desktop/dist-electron" /opt/safepckids/desktop/
  install -m 0644 "${SOURCE_DIR}/apps/desktop/package.json" /opt/safepckids/desktop/package.json
  if [[ -d "${SOURCE_DIR}/apps/desktop/node_modules/electron/dist" ]]; then
    cp -a "${SOURCE_DIR}/apps/desktop/node_modules/electron/dist/." /opt/safepckids/desktop/electron/
    chmod 0755 /opt/safepckids/desktop/electron/electron /opt/safepckids/desktop/electron/chrome_crashpad_handler || true
  fi
  install -d -m 0755 /opt/safepckids/desktop/assets
  cp -a "${SOURCE_DIR}/assets/." /opt/safepckids/desktop/assets/
  install -m 0644 "${SOURCE_DIR}/assets/safepckids.svg" /usr/share/icons/hicolor/scalable/apps/safepckids.svg
  install -m 0644 "${SOURCE_DIR}/assets/safepckids-256.png" /usr/share/pixmaps/safepckids.png
  install -m 0755 "${SOURCE_DIR}/packaging/safepckids-admin-gui" /usr/local/bin/safepckids-admin-gui
  install -m 0755 "${SOURCE_DIR}/packaging/safepckids-child-gui" /usr/local/bin/safepckids-child-gui
  chown -R root:root /opt/safepckids/desktop
fi
# Atualiza configuração de runtime do tmpfiles (dispensa CAP_CHOWN)
install -d -m 0755 /usr/lib/tmpfiles.d /etc/tmpfiles.d
cat > /etc/tmpfiles.d/safepckids.conf <<TMPFILES
d /run/safepckids 0750 root ${ADMIN_GROUP} -
d /run/safepckids-child 2750 root ${CHILD_GROUP} -
TMPFILES
systemd-tmpfiles --create /etc/tmpfiles.d/safepckids.conf 2>/dev/null || true

install -m 0644 "${SOURCE_DIR}/packaging/safepckids-linux.service" /etc/systemd/system/safepckids-linux.service
sed -i "s/--user filhos/--user ${CHILD_USER}/" /etc/systemd/system/safepckids-linux.service
sed -i "s/--admin-group wheel/--admin-group ${ADMIN_GROUP}/" /etc/systemd/system/safepckids-linux.service
sed -i "s/^Group=wheel/Group=${ADMIN_GROUP}/" /etc/systemd/system/safepckids-linux.service
systemctl daemon-reload
systemctl restart safepckids-linux.service
systemctl --no-pager --full status safepckids-linux.service
echo "SafePCKids atualizado; banco biométrico e quotas preservados."
