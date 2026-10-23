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
  useradd --create-home --shell /bin/bash "${CHILD_USER}"
  echo "Defina agora a senha de recuperação da conta compartilhada."
  passwd "${CHILD_USER}"
fi

# A conta pode já existir e carregar privilégios indiretos (docker, libvirt,
# wheel, video etc.). O desktop recebe dispositivos pela sessão do logind e
# não precisa de grupos suplementares permanentes.
usermod --groups "" "${CHILD_USER}"
if [[ $(id -G "${CHILD_USER}" | wc -w) -ne 1 ]]; then
  echo "Não foi possível remover todos os grupos suplementares de ${CHILD_USER}." >&2
  exit 1
fi
echo "Conta ${CHILD_USER} preparada sem grupos suplementares ou acesso direto à webcam."
