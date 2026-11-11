#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash scripts/Desinstalar-SafePCKids-RegataOS.sh" >&2
  exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CHILD_USER=${1:-filhos}
if [[ -x /usr/local/sbin/safepckids-disable-pam ]]; then
  /usr/local/sbin/safepckids-disable-pam
elif [[ -x ${SCRIPT_DIR}/Desativar-PAM-SafePCKids-RegataOS.sh ]]; then
  "${SCRIPT_DIR}/Desativar-PAM-SafePCKids-RegataOS.sh"
fi

systemctl disable --now safepckids-linux.service 2>/dev/null || true
rm -f /etc/systemd/system/safepckids-linux.service
rm -f /usr/local/sbin/safepckids-admin /usr/local/bin/safepckids-admin
rm -f /usr/local/bin/safepckids-linux-probe
rm -f /usr/local/libexec/safepckids-pam-helper
rm -f /usr/local/sbin/safepckids-enable-pam /usr/local/bin/safepckids-enable-pam
rm -f /usr/local/sbin/safepckids-disable-pam /usr/local/bin/safepckids-disable-pam
if getent passwd "${CHILD_USER}" >/dev/null 2>&1; then
  CHILD_HOME=$(getent passwd "${CHILD_USER}" | cut -d: -f6)
  rm -f "${CHILD_HOME}/.local/share/applications/safepckids-child.desktop"
  rm -f "${CHILD_HOME}/.config/autostart/safepckids-child.desktop"
fi
systemctl daemon-reload
rm -rf /usr/lib/safepckids /opt/safepckids

echo "Programa removido. Os dados biométricos e quotas foram preservados em /var/lib/safepckids."
echo "Para apagá-los deliberadamente: sudo rm -rf /var/lib/safepckids"
