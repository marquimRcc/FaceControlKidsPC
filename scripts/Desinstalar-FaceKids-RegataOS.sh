#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash scripts/Desinstalar-FaceKids-RegataOS.sh" >&2
  exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -x /usr/local/sbin/facekids-disable-pam ]]; then
  /usr/local/sbin/facekids-disable-pam
elif [[ -x ${SCRIPT_DIR}/Desativar-PAM-FaceKids-RegataOS.sh ]]; then
  "${SCRIPT_DIR}/Desativar-PAM-FaceKids-RegataOS.sh"
fi

systemctl disable --now facekids-linux.service 2>/dev/null || true
rm -f /etc/systemd/system/facekids-linux.service
rm -f /usr/local/sbin/facekids-admin
rm -f /usr/local/bin/facekids-linux-probe
rm -f /usr/local/libexec/facekids-pam-helper
rm -f /usr/local/sbin/facekids-enable-pam /usr/local/sbin/facekids-disable-pam
systemctl daemon-reload
rm -rf /usr/lib/facekids /opt/facekids

echo "Programa removido. Os dados biométricos e quotas foram preservados em /var/lib/facekids."
echo "Para apagá-los deliberadamente: sudo rm -rf /var/lib/facekids"
