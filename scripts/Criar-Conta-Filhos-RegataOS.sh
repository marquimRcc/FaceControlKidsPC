#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root." >&2
  exit 1
fi

CHILD_USER=${1:-filhos}
if [[ ! ${CHILD_USER} =~ ^[a-z_][a-z0-9_.-]*$ ]]; then
  echo "Nome de usuário inválido: ${CHILD_USER}" >&2
  exit 1
fi
if getent passwd "${CHILD_USER}" >/dev/null; then
  echo "A conta ${CHILD_USER} já existe. Nenhuma conta foi recriada."
else
  useradd --create-home --shell /bin/bash --groups video "${CHILD_USER}"
  echo "Defina agora a senha de recuperação da conta compartilhada."
  passwd "${CHILD_USER}"
fi

if id -nG "${CHILD_USER}" | tr ' ' '\n' | grep -qx wheel; then
  gpasswd --delete "${CHILD_USER}" wheel
fi
usermod --append --groups video "${CHILD_USER}"
echo "Conta ${CHILD_USER} preparada como usuário comum, sem grupo wheel."
