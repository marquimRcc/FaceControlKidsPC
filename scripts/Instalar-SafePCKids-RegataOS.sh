#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash scripts/Instalar-SafePCKids-RegataOS.sh" >&2
  exit 1
fi

SOURCE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CHILD_USER=${1:-filhos}
CHILD_COUNT=${2:-1}
ADMIN_GROUP=${3:-}
if [[ -z "${ADMIN_GROUP}" ]]; then
  if getent group wheel >/dev/null; then
    ADMIN_GROUP="wheel"
  elif getent group sudo >/dev/null; then
    ADMIN_GROUP="sudo"
  else
    ADMIN_GROUP="wheel"
  fi
fi
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
CHILD_GROUP=$(id -gn "${CHILD_USER}")

zypper --non-interactive install python313 v4l-utils

install -d -m 0755 /usr/lib/safepckids /usr/lib/safepckids/models /opt/safepckids
install -d -m 0700 -o root -g root /var/lib/safepckids
cp -a "${SOURCE_DIR}/safepckids" /usr/lib/safepckids/
install -m 0644 "${SOURCE_DIR}/requirements.txt" /usr/lib/safepckids/requirements.txt
install -m 0755 "${SOURCE_DIR}/packaging/safepckids-admin" /usr/local/sbin/safepckids-admin
install -m 0755 "${SOURCE_DIR}/packaging/safepckids-admin" /usr/local/bin/safepckids-admin
install -m 0755 "${SOURCE_DIR}/packaging/safepckids-linux-probe" /usr/local/bin/safepckids-linux-probe
install -d -m 0755 /usr/local/libexec
install -m 0755 "${SOURCE_DIR}/packaging/safepckids-pam-helper" /usr/local/libexec/safepckids-pam-helper
install -m 0755 "${SOURCE_DIR}/scripts/Ativar-PAM-SafePCKids-RegataOS.sh" /usr/local/sbin/safepckids-enable-pam
install -m 0755 "${SOURCE_DIR}/scripts/Ativar-PAM-SafePCKids-RegataOS.sh" /usr/local/bin/safepckids-enable-pam
install -m 0755 "${SOURCE_DIR}/scripts/Desativar-PAM-SafePCKids-RegataOS.sh" /usr/local/sbin/safepckids-disable-pam
install -m 0755 "${SOURCE_DIR}/scripts/Desativar-PAM-SafePCKids-RegataOS.sh" /usr/local/bin/safepckids-disable-pam

# Interface Desktop Unificada (Electron + React)
install -d -m 0755 /opt/safepckids/desktop /opt/safepckids/desktop/electron /usr/share/icons/hicolor/scalable/apps /usr/share/pixmaps
if [[ -d "${SOURCE_DIR}/apps/desktop/dist" && -d "${SOURCE_DIR}/apps/desktop/dist-electron" ]]; then
  cp -a "${SOURCE_DIR}/apps/desktop/dist" /opt/safepckids/desktop/
  cp -a "${SOURCE_DIR}/apps/desktop/dist-electron" /opt/safepckids/desktop/
  install -m 0644 "${SOURCE_DIR}/apps/desktop/package.json" /opt/safepckids/desktop/package.json
fi
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

python3 -m venv /opt/safepckids/venv
/opt/safepckids/venv/bin/python -m pip install --disable-pip-version-check -r /usr/lib/safepckids/requirements.txt
PYTHONPATH=/usr/lib/safepckids /opt/safepckids/venv/bin/python -m safepckids.cli \
  --models /usr/lib/safepckids/models download-models
PYTHONPATH=/usr/lib/safepckids /opt/safepckids/venv/bin/python -m safepckids.linux_admin \
  --database /var/lib/safepckids/criancas.sqlite3 setup --children "${CHILD_COUNT}"

# Configuração de runtime protegida via systemd-tmpfiles (elimina necessidade de CAP_CHOWN)
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
sed -i "s/SAFEPCKIDS_CHILD_USER=filhos/SAFEPCKIDS_CHILD_USER=${CHILD_USER}/" /usr/local/libexec/safepckids-pam-helper
chown -R root:root /usr/lib/safepckids /opt/safepckids /var/lib/safepckids
chmod 0644 /usr/lib/safepckids/models/*.onnx
chmod 0700 /var/lib/safepckids
chmod 0600 /var/lib/safepckids/criancas.sqlite3
systemctl daemon-reload
if systemctl is-active --quiet safepckids-linux.service; then
  systemctl restart safepckids-linux.service
fi

echo "Instalação preparada para ${CHILD_COUNT} criança(s). Cadastre todos os rostos antes de iniciar o serviço:"
echo "Primeiro valide a webcam: safepckids-linux-probe --camera 0 --seconds 5"
echo "sudo -E safepckids-admin enroll 1"
echo "Repita para cada número configurado; depois: sudo systemctl enable --now safepckids-linux"
echo "A integração PAM opcional não foi ativada. Teste o serviço antes de habilitá-la."
echo "Após os testes, habilite com: sudo safepckids-enable-pam"
echo "Na conta do responsável, crie o aplicativo com: scripts/Criar-Atalho-Painel-RegataOS.sh"
echo "Para instalar a tela infantil: sudo bash scripts/Criar-Tela-Infantil-RegataOS.sh ${CHILD_USER}"
