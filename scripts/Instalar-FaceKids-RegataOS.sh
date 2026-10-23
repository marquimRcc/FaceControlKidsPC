#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash scripts/Instalar-FaceKids-RegataOS.sh" >&2
  exit 1
fi

SOURCE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CHILD_USER=${1:-filhos}
CHILD_COUNT=${2:-1}
ADMIN_GROUP=${3:-wheel}
if [[ ! ${CHILD_USER} =~ ^[a-z_][a-z0-9_.-]*$ ]]; then
  echo "Nome de usuário inválido: ${CHILD_USER}" >&2
  exit 1
fi
if [[ ! ${CHILD_COUNT} =~ ^[1-9][0-9]*$ ]] || (( CHILD_COUNT > 20 )); then
  echo "Quantidade de crianças deve estar entre 1 e 20" >&2
  exit 1
fi
if [[ ! ${ADMIN_GROUP} =~ ^[a-z_][a-z0-9_-]*$ ]] || ! getent group "${ADMIN_GROUP}" >/dev/null; then
  echo "Grupo administrador inválido ou inexistente: ${ADMIN_GROUP}" >&2
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
install -m 0755 "${SOURCE_DIR}/packaging/facekids-admin" /usr/local/bin/facekids-admin
install -m 0755 "${SOURCE_DIR}/packaging/facekids-linux-probe" /usr/local/bin/facekids-linux-probe
install -d -m 0755 /usr/local/libexec
install -m 0755 "${SOURCE_DIR}/packaging/facekids-pam-helper" /usr/local/libexec/facekids-pam-helper
install -m 0755 "${SOURCE_DIR}/scripts/Ativar-PAM-FaceKids-RegataOS.sh" /usr/local/sbin/facekids-enable-pam
install -m 0755 "${SOURCE_DIR}/scripts/Ativar-PAM-FaceKids-RegataOS.sh" /usr/local/bin/facekids-enable-pam
install -m 0755 "${SOURCE_DIR}/scripts/Desativar-PAM-FaceKids-RegataOS.sh" /usr/local/sbin/facekids-disable-pam
install -m 0755 "${SOURCE_DIR}/scripts/Desativar-PAM-FaceKids-RegataOS.sh" /usr/local/bin/facekids-disable-pam

# Interface Desktop Unificada (Electron + React)
install -d -m 0755 /opt/facekids/desktop /opt/facekids/desktop/electron /usr/share/icons/hicolor/scalable/apps /usr/share/pixmaps
if [[ -d "${SOURCE_DIR}/apps/desktop/dist" && -d "${SOURCE_DIR}/apps/desktop/dist-electron" ]]; then
  cp -a "${SOURCE_DIR}/apps/desktop/dist" /opt/facekids/desktop/
  cp -a "${SOURCE_DIR}/apps/desktop/dist-electron" /opt/facekids/desktop/
  install -m 0644 "${SOURCE_DIR}/apps/desktop/package.json" /opt/facekids/desktop/package.json
fi
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

python3 -m venv /opt/facekids/venv
/opt/facekids/venv/bin/python -m pip install --disable-pip-version-check -r /usr/lib/facekids/requirements.txt
PYTHONPATH=/usr/lib/facekids /opt/facekids/venv/bin/python -m facekids.cli \
  --models /usr/lib/facekids/models download-models
PYTHONPATH=/usr/lib/facekids /opt/facekids/venv/bin/python -m facekids.linux_admin \
  --database /var/lib/facekids/criancas.sqlite3 setup --children "${CHILD_COUNT}"

install -m 0644 "${SOURCE_DIR}/packaging/facekids-linux.service" /etc/systemd/system/facekids-linux.service
sed -i "s/--user filhos/--user ${CHILD_USER}/" /etc/systemd/system/facekids-linux.service
sed -i "s/--admin-group wheel/--admin-group ${ADMIN_GROUP}/" /etc/systemd/system/facekids-linux.service
sed -i "s/^Group=wheel/Group=${ADMIN_GROUP}/" /etc/systemd/system/facekids-linux.service
sed -i "s/FACEKIDS_CHILD_USER=filhos/FACEKIDS_CHILD_USER=${CHILD_USER}/" /usr/local/libexec/facekids-pam-helper
chown -R root:root /usr/lib/facekids /opt/facekids /var/lib/facekids
chmod 0644 /usr/lib/facekids/models/*.onnx
chmod 0700 /var/lib/facekids
chmod 0600 /var/lib/facekids/criancas.sqlite3
systemctl daemon-reload
if systemctl is-active --quiet facekids-linux.service; then
  systemctl restart facekids-linux.service
fi

echo "Instalação preparada para ${CHILD_COUNT} criança(s). Cadastre todos os rostos antes de iniciar o serviço:"
echo "Primeiro valide a webcam: facekids-linux-probe --camera 0 --seconds 5"
echo "sudo -E facekids-admin enroll 1"
echo "Repita para cada número configurado; depois: sudo systemctl enable --now facekids-linux"
echo "A integração PAM opcional não foi ativada. Teste o serviço antes de habilitá-la."
echo "Após os testes, habilite com: sudo facekids-enable-pam"
echo "Na conta do responsável, crie o aplicativo com: scripts/Criar-Atalho-Painel-RegataOS.sh"
echo "Para instalar a tela infantil: sudo bash scripts/Criar-Tela-Infantil-RegataOS.sh ${CHILD_USER}"
