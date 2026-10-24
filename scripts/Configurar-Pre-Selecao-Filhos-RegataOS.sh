#!/usr/bin/env bash
# ==============================================================================
# FaceKids Linux - Configurar Pré-Seleção da Conta Filhos no SDDM (Regata OS)
# ==============================================================================
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Este script precisa ser executado como root (use sudo)." >&2
  exit 1
fi

CHILD_USER="${1:-filhos}"
if ! id -u "${CHILD_USER}" >/dev/null 2>&1; then
  echo "Usuário '${CHILD_USER}' não encontrado no sistema. Crie-o primeiro com Criar-Conta-Filhos-RegataOS.sh." >&2
  exit 1
fi

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ICON_SRC="${ROOT_DIR}/assets/facekids-256.png"

echo "Configurando conta '${CHILD_USER}' como padrão na tela de login (SDDM)..."

# 1. Configurar ícone de avatar para a conta filhos
if [[ -f "${ICON_SRC}" ]]; then
  install -d -m 0755 /usr/share/sddm/faces
  install -m 0644 "${ICON_SRC}" "/usr/share/sddm/faces/${CHILD_USER}.face.icon"

  CHILD_HOME=$(getent passwd "${CHILD_USER}" | cut -d: -f6)
  if [[ -d "${CHILD_HOME}" ]]; then
    CHILD_GID=$(id -g "${CHILD_USER}")
    install -m 0644 -o "${CHILD_USER}" -g "${CHILD_GID}" "${ICON_SRC}" "${CHILD_HOME}/.face.icon"
  fi
  echo "[OK] Ícone do FaceKids configurado como avatar da conta '${CHILD_USER}'."
fi

# 2. Configurar diretiva de usuários no SDDM
install -d -m 0755 /etc/sddm.conf.d
cat <<'EOF' > /etc/sddm.conf.d/10-facekids-user.conf
[Users]
RememberLastUser=true
RememberLastSession=true
EOF
chmod 0644 /etc/sddm.conf.d/10-facekids-user.conf
echo "[OK] Diretiva RememberLastUser configurada em /etc/sddm.conf.d/10-facekids-user.conf."

# 3. Pré-definir 'filhos' no estado do SDDM (state.conf)
STATE_DIR="/var/lib/sddm"
STATE_FILE="${STATE_DIR}/state.conf"

install -d -m 0750 "${STATE_DIR}"
if id -u sddm >/dev/null 2>&1; then
  chown sddm:sddm "${STATE_DIR}"
fi

cat <<EOF > "${STATE_FILE}"
[Last]
Session=plasma6.desktop
User=${CHILD_USER}
EOF

chmod 0640 "${STATE_FILE}"
if id -u sddm >/dev/null 2>&1; then
  chown sddm:sddm "${STATE_FILE}"
fi
echo "[OK] Estado inicial do SDDM definido com sucesso para o usuário '${CHILD_USER}'."

echo ""
echo "Concluído com sucesso! Ao ligar o computador, a conta '${CHILD_USER}' já aparecerá em foco pronta para entrar."
