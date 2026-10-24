#!/usr/bin/env bash
# ==============================================================================
# FaceKids Linux - Diagnóstico de Saúde e Integridade do Sistema
# ==============================================================================
set -euo pipefail

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
BLUE="\033[34m"
RESET="\033[0m"

PASS="[${GREEN}OK${RESET}]"
WARN="[${YELLOW}AVISO${RESET}]"
FAIL="[${RED}FALHA${RESET}]"
INFO="[${BLUE}INFO${RESET}]"

ISSUES_COUNT=0
WARNINGS_COUNT=0

log_pass() { echo -e "  ${PASS} $1"; }
log_warn() { echo -e "  ${WARN} $1"; ((WARNINGS_COUNT++)) || true; }
log_fail() { echo -e "  ${FAIL} $1"; ((ISSUES_COUNT++)) || true; }
log_info() { echo -e "  ${INFO} $1"; }

echo -e "\n${BOLD}======================================================================${RESET}"
echo -e "${BOLD}       FaceKids Linux - Verificação de Integridade e Saúde             ${RESET}"
echo -e "${BOLD}======================================================================${RESET}\n"

# 1. Verificação de Usuário e Permissões Administrativas
echo -e "${BOLD}1. Permissões de Execução:${RESET}"
CURRENT_USER=$(id -un)
CURRENT_UID=$(id -u)
log_info "Executando como usuário: ${CURRENT_USER} (UID ${CURRENT_UID})"

ADMIN_GROUP=""
for candidate in wheel sudo; do
  if getent group "${candidate}" >/dev/null 2>&1; then
    ADMIN_GROUP="${candidate}"
    break
  fi
done

if [[ -n "${ADMIN_GROUP}" ]]; then
  log_pass "Grupo de administração detectado no sistema: ${ADMIN_GROUP}"
else
  log_warn "Nenhum grupo padrão (wheel/sudo) encontrado."
fi

# 2. Verificação do Serviço Systemd
echo -e "\n${BOLD}2. Serviço em Segundo Plano (Systemd):${RESET}"
if command -v systemctl >/dev/null 2>&1; then
  SERVICE_STATE=$(systemctl is-active facekids-linux.service 2>/dev/null || echo "inactive")
  SERVICE_ENABLED=$(systemctl is-enabled facekids-linux.service 2>/dev/null || echo "disabled")

  if [[ "${SERVICE_STATE}" == "active" ]]; then
    log_pass "Serviço facekids-linux.service está ATIVO (running)"
  else
    log_warn "Serviço facekids-linux.service está ${SERVICE_STATE}"
  fi

  if [[ "${SERVICE_ENABLED}" == "enabled" ]]; then
    log_pass "Serviço habilitado para inicialização no boot"
  else
    log_info "Serviço não habilitado automaticamente no boot (${SERVICE_ENABLED})"
  fi
else
  log_warn "systemctl não disponível neste ambiente."
fi

# 3. Modelos de Inteligência Artificial (YuNet + SFace)
echo -e "\n${BOLD}3. Modelos de Reconhecimento Facial:${RESET}"
YUNET=""
SFACE=""
for dir in /usr/lib/facekids/models /opt/facekids/models "$(pwd)/models"; do
  if [[ -f "${dir}/face_detection_yunet_2023mar.onnx" && -f "${dir}/face_recognition_sface_2021dec.onnx" ]]; then
    YUNET="${dir}/face_detection_yunet_2023mar.onnx"
    SFACE="${dir}/face_recognition_sface_2021dec.onnx"
    break
  fi
done

if [[ -n "${YUNET}" && -n "${SFACE}" ]]; then
  log_pass "Modelos ONNX localizados em: $(dirname "${YUNET}")"
else
  log_fail "Modelos faciais YuNet/SFace não encontrados em /usr/lib/facekids/models ou /opt/facekids/models"
fi

# 4. Banco de Dados e Permissões
echo -e "\n${BOLD}4. Banco de Dados e Armazenamento Protegido:${RESET}"
DB_PATH="/var/lib/facekids/criancas.sqlite3"
if [[ -f "${DB_PATH}" ]]; then
  DB_PERMS=$(stat -c "%a %U:%G" "${DB_PATH}" 2>/dev/null || echo "desconhecido")
  log_pass "Banco de dados existente: ${DB_PATH} (${DB_PERMS})"
  if [[ "${DB_PERMS}" =~ ^(600|660) ]]; then
    log_pass "Permissões restritas do banco de dados validadas"
  else
    log_warn "Permissões do banco recomendadas são 0600 ou 0660 (atual: ${DB_PERMS})"
  fi
else
  log_info "Banco de dados ainda não criado em ${DB_PATH} (será gerado no primeiro cadastro)"
fi

# 5. Sockets IPC e Diretórios em Execução
echo -e "\n${BOLD}5. Comunicação Inter-Processos (IPC Sockets):${RESET}"
ADMIN_SOCK="/run/facekids/admin.sock"
CHILD_SOCK="/run/facekids-child/status.sock"

if [[ -S "${ADMIN_SOCK}" ]]; then
  ADMIN_SOCK_PERMS=$(stat -c "%a %U:%G" "${ADMIN_SOCK}" 2>/dev/null || echo "desconhecido")
  log_pass "Socket de administração ativo: ${ADMIN_SOCK} (${ADMIN_SOCK_PERMS})"
else
  log_warn "Socket ${ADMIN_SOCK} não encontrado ou daemon inativo"
fi

if [[ -S "${CHILD_SOCK}" ]]; then
  CHILD_SOCK_PERMS=$(stat -c "%a %U:%G" "${CHILD_SOCK}" 2>/dev/null || echo "desconhecido")
  log_pass "Socket infantil ativo: ${CHILD_SOCK} (${CHILD_SOCK_PERMS})"
else
  log_warn "Socket ${CHILD_SOCK} não encontrado ou daemon inativo"
fi

# 6. Teste de Comunicação IPC ao Vivo (se os sockets existirem)
echo -e "\n${BOLD}6. Diagnóstico ao Vivo com o Daemon:${RESET}"
PYTHON_BIN=""
for candidate in /opt/facekids/venv/bin/python "$(pwd)/.venv/bin/python" python3; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    PYTHON_BIN="${candidate}"
    break
  fi
done

if [[ -S "${ADMIN_SOCK}" && -n "${PYTHON_BIN}" ]]; then
  IPC_STATUS=$("${PYTHON_BIN}" -c "
import socket, json
try:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(3.0)
        s.connect('${ADMIN_SOCK}')
        s.sendall(b'{\"op\": \"status\"}\n')
        buf = b''
        while b'\n' not in buf:
            chunk = s.recv(4096)
            if not chunk: break
            buf += chunk
        res = json.loads(buf.decode('utf-8').strip())
        snap = res.get('snapshot', {})
        print(f\"service={snap.get('service')} camera={snap.get('camera')} session={snap.get('session')} children={len(snap.get('children', []))}\")
except Exception as e:
    print(f\"ERRO: {e}\")
" 2>/dev/null || echo "ERRO")

  if [[ "${IPC_STATUS}" =~ service=online ]]; then
    log_pass "Daemon respondeu com sucesso: ${IPC_STATUS}"
  else
    log_fail "Falha ao consultar estado do daemon: ${IPC_STATUS}"
  fi

  IPC_PROBE=$("${PYTHON_BIN}" -c "
import socket, json
try:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(4.0)
        s.connect('${ADMIN_SOCK}')
        s.sendall(b'{\"op\": \"probe\", \"seconds\": 1.0}\n')
        buf = b''
        while b'\n' not in buf:
            chunk = s.recv(4096)
            if not chunk: break
            buf += chunk
        res = json.loads(buf.decode('utf-8').strip())
        if not res.get('ok'):
            print(f\"LEGACY: {res.get('error', 'desconhecido')}\")
        else:
            probe = res.get('probe', {})
            print(f\"opened={probe.get('opened')} frames={probe.get('frames')} usable={probe.get('usable_frames')} faces={probe.get('faces_seen')}\")
except Exception as e:
    print(f\"ERRO: {e}\")
" 2>/dev/null || echo "ERRO")

  if [[ "${IPC_PROBE}" =~ opened=True ]]; then
    log_pass "Telemetria da câmera via daemon: ${IPC_PROBE}"
  elif [[ "${IPC_PROBE}" =~ LEGACY ]]; then
    log_warn "Daemon em execução ainda é de versão anterior (reinicie o serviço para ativar telemetria)"
  else
    log_warn "Telemetria da câmera: ${IPC_PROBE}"
  fi
else
  log_info "Consulta ao vivo ignorada (socket ausente ou daemon parado)"
fi

# 7. Pacote da Interface Desktop (Electron)
echo -e "\n${BOLD}7. Interface Desktop (Electron):${RESET}"
BUNDLE_INDEX="/opt/facekids/desktop/dist/index.html"
ELECTRON_BIN="/opt/facekids/desktop/electron/electron"

if [[ -f "${BUNDLE_INDEX}" && -x "${ELECTRON_BIN}" ]]; then
  log_pass "Pacote desktop autossuficiente instalado em /opt/facekids/desktop"
else
  log_info "Pacote em /opt/facekids/desktop não localizado (usando fallback de desenvolvimento)"
fi

if [[ -x /usr/local/bin/facekids-admin-gui ]]; then
  log_pass "Atalho executável do painel presente em /usr/local/bin/facekids-admin-gui"
else
  log_info "Atalho global /usr/local/bin/facekids-admin-gui ausente"
fi

# 8. Verificação de Erros Recentes no Log do Serviço
echo -e "\n${BOLD}8. Registros Recentes do Journal:${RESET}"
if command -v journalctl >/dev/null 2>&1; then
  RECENT_ERRORS=$(journalctl -u facekids-linux.service --since "1 hour ago" -p err --no-pager -n 5 2>/dev/null || true)
  if [[ -n "${RECENT_ERRORS}" && "${RECENT_ERRORS}" != "-- No entries --" ]]; then
    log_warn "Erros encontrados no journal recente:"
    echo "${RECENT_ERRORS}" | sed 's/^/    /'
  else
    log_pass "Nenhum erro crítico registrado no journal na última hora"
  fi
else
  log_info "journalctl não disponível."
fi

# Resumo Final
echo -e "\n${BOLD}======================================================================${RESET}"
if [[ ${ISSUES_COUNT} -eq 0 && ${WARNINGS_COUNT} -eq 0 ]]; then
  echo -e "  ${GREEN}${BOLD}Status Geral: SAUDÁVEL (Todos os testes foram aprovados)${RESET}"
elif [[ ${ISSUES_COUNT} -eq 0 ]]; then
  echo -e "  ${YELLOW}${BOLD}Status Geral: ATENÇÃO (${WARNINGS_COUNT} aviso(s) encontrado(s))${RESET}"
else
  echo -e "  ${RED}${BOLD}Status Geral: CRÍTICO (${ISSUES_COUNT} falha(s), ${WARNINGS_COUNT} aviso(s))${RESET}"
fi
echo -e "${BOLD}======================================================================${RESET}\n"

if [[ ${ISSUES_COUNT} -gt 0 ]]; then
  exit 1
fi
exit 0
