#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash scripts/Instalar-FaceKids-RegataOS.sh" >&2
  exit 1
fi

SOURCE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CHILD_USER=${1:-filhos}
if [[ ! ${CHILD_USER} =~ ^[a-z_][a-z0-9_.-]*$ ]]; then
  echo "Nome de usuário inválido: ${CHILD_USER}" >&2
  exit 1
fi
if ! getent passwd "${CHILD_USER}" >/dev/null; then
  echo "A conta compartilhada '${CHILD_USER}' ainda não existe." >&2
  exit 1
fi

zypper --non-interactive install python313 v4l-utils

install -d -m 0755 /usr/lib/facekids /usr/lib/facekids/models /opt/facekids
install -d -m 0700 -o root -g root /var/lib/facekids
cp -a "${SOURCE_DIR}/facekids" /usr/lib/facekids/
install -m 0644 "${SOURCE_DIR}/requirements.txt" /usr/lib/facekids/requirements.txt
install -m 0755 "${SOURCE_DIR}/packaging/facekids-admin" /usr/local/sbin/facekids-admin
install -m 0755 "${SOURCE_DIR}/packaging/facekids-linux-probe" /usr/local/bin/facekids-linux-probe
install -d -m 0755 /usr/local/libexec
install -m 0755 "${SOURCE_DIR}/packaging/facekids-pam-helper" /usr/local/libexec/facekids-pam-helper

python3 -m venv /opt/facekids/venv
/opt/facekids/venv/bin/python -m pip install --disable-pip-version-check -r /usr/lib/facekids/requirements.txt
PYTHONPATH=/usr/lib/facekids /opt/facekids/venv/bin/python -m facekids.cli \
  --models /usr/lib/facekids/models download-models
PYTHONPATH=/usr/lib/facekids /opt/facekids/venv/bin/python -m facekids.linux_admin \
  --database /var/lib/facekids/criancas.sqlite3 setup

install -m 0644 "${SOURCE_DIR}/packaging/facekids-linux.service" /etc/systemd/system/facekids-linux.service
sed -i "s/--user filhos/--user ${CHILD_USER}/" /etc/systemd/system/facekids-linux.service
sed -i "s/FACEKIDS_CHILD_USER=filhos/FACEKIDS_CHILD_USER=${CHILD_USER}/" /usr/local/libexec/facekids-pam-helper
chown -R root:root /usr/lib/facekids /opt/facekids /var/lib/facekids
chmod 0700 /var/lib/facekids
chmod 0600 /var/lib/facekids/criancas.sqlite3
systemctl daemon-reload
systemctl enable facekids-linux.service

echo "Instalação preparada. Cadastre os três rostos antes de iniciar o serviço:"
echo "Primeiro valide a webcam: facekids-linux-probe --camera 0 --seconds 5"
echo "sudo -E facekids-admin enroll 1"
echo "Repita para 2 e 3; depois: sudo systemctl start facekids-linux"
echo "A integração PAM opcional não foi ativada. Teste o serviço antes de habilitá-la."
