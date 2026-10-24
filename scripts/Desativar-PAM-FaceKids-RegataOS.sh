#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root." >&2
  exit 1
fi

BACKUP_DIR=/var/lib/facekids/pam-backup
for name in kde sddm; do
  target="/usr/lib/pam.d/${name}"
  backup="${BACKUP_DIR}/${name}.original"
  if [[ -f ${backup} ]]; then
    install -m 0644 -o root -g root "${backup}" "${target}"
  elif [[ -f ${target} ]]; then
    temporary=$(mktemp "${target}.facekids.XXXXXX")
    awk '!/\/usr\/local\/libexec\/facekids-pam-helper/' "${target}" > "${temporary}"
    chown root:root "${temporary}"
    chmod 0644 "${temporary}"
    mv "${temporary}" "${target}"
  fi
done

echo "Integração PAM do FaceKids removida. A autenticação por senha permanece."
