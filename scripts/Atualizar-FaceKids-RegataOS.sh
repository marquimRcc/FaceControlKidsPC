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
install -m 0644 "${SOURCE_DIR}/packaging/facekids-linux.service" /etc/systemd/system/facekids-linux.service
sed -i "s/--user filhos/--user ${CHILD_USER}/" /etc/systemd/system/facekids-linux.service
sed -i "s/--admin-group wheel/--admin-group ${ADMIN_GROUP}/" /etc/systemd/system/facekids-linux.service
sed -i "s/^Group=wheel/Group=${ADMIN_GROUP}/" /etc/systemd/system/facekids-linux.service
systemctl daemon-reload
systemctl restart facekids-linux.service
systemctl --no-pager --full status facekids-linux.service
echo "FaceKids atualizado; banco biométrico e quotas preservados."
