#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root." >&2
  exit 1
fi

HELPER=/usr/local/libexec/facekids-pam-helper
BACKUP_DIR=/var/lib/facekids/pam-backup
PAM_LINE='auth     [success=done default=ignore] pam_exec.so quiet /usr/local/libexec/facekids-pam-helper'

if [[ ! -x ${HELPER} ]]; then
  echo "Instale e teste o FaceKids antes de habilitar PAM." >&2
  exit 1
fi
if ! systemctl is-active --quiet facekids-linux.service; then
  echo "O serviço facekids-linux precisa estar ativo." >&2
  exit 1
fi
if ! find /lib64/security /usr/lib64/security -name pam_exec.so -print -quit 2>/dev/null | grep -q .; then
  echo "pam_exec.so não foi encontrado." >&2
  exit 1
fi

install -d -m 0700 -o root -g root "${BACKUP_DIR}"
for name in kde sddm; do
  target="/usr/lib/pam.d/${name}"
  backup="${BACKUP_DIR}/${name}.original"
  if [[ ! -f ${target} ]]; then
    echo "Arquivo PAM ausente: ${target}" >&2
    exit 1
  fi
  if grep -Fq '/usr/local/libexec/facekids-pam-helper' "${target}"; then
    continue
  fi
  if [[ ! -f ${backup} ]]; then
    install -m 0600 -o root -g root "${target}" "${backup}"
  fi
  temporary=$(mktemp "${target}.facekids.XXXXXX")
  awk -v line="${PAM_LINE}" '
    !inserted && $1 == "auth" && $0 ~ /common-auth/ { print line; inserted=1 }
    { print }
    END { if (!inserted) exit 42 }
  ' "${target}" > "${temporary}" || {
    rm -f "${temporary}"
    echo "Não foi possível localizar common-auth em ${target}." >&2
    exit 1
  }
  chown root:root "${temporary}"
  chmod 0644 "${temporary}"
  mv "${temporary}" "${target}"
done

echo "FaceKids foi adicionado a KDE e SDDM com fallback para senha."
echo "Mantenha a conta administrativa disponível e teste primeiro o bloqueio KDE."
