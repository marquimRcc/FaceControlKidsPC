# FaceControlKidsPC — Arquitetura de Produção Windows (10/11)

**Data de Homologação:** Outubro / 2026  
**Ambiente Alvo:** Windows 10 e Windows 11 (Desktop Doméstico Físico)  
**Conta Compartilhada:** `Filhos` (senha fixa `"1"` para AutoLogon pelo Credential Provider)  
**Conta Administradora:** Intacta, nunca interceptada pelo Credential Provider

---

## 1. Visão Geral da Arquitetura

O FaceControlKidsPC é um sistema de controle parental biométrico e controle de tempo de tela para Windows 10/11. Ele opera em três camadas coordenadas:

1. **Camada de Logon / LogonUI (C++ Nativo):**
   - DLL: `native/credential_provider_facekids/FaceKidsCredentialProvider.dll` (instalada em `C:\ProgramData\FaceKids\`).
   - Visível **exclusivamente** na conta `Filhos` (filtragem por SID).
   - Consulta o serviço Python via Named Pipe `\\.\pipe\FaceKidsAuthPipe`.
   - Ao receber `ALLOW`, executa AutoLogon transparente via `KerbInteractiveLogon` com senha `"1"`.

2. **Camada de Serviço Central (Python SYSTEM / Administrador):**
   - Serviço: `facekids/auth_service.py` (executado via Agendador de Tarefas no Boot como `SYSTEM` ou no logon).
   - Biometria: OpenCV DNN com modelos **YuNet** (detecção facial) e **SFace** (extração e comparação vetorial).
   - Fonte de Dados: SQLite local em `C:\ProgramData\FaceKids\kids.sqlite3`.
   - Proteção Anti-Burla: `facekids/agent_watchdog.py` monitora o processo `filhos_agent.py` na sessão ativa e previne uso indevido caso o processo seja finalizado.

3. **Camada de Sessão do Usuário (Python na conta Filhos):**
   - Agente: `facekids/filhos_agent.py` (iniciado na sessão interativa do usuário `Filhos`).
   - Tela de Boas-Vindas: `facekids/welcome_screen.py` (auto-fecha em 4s e reabre a cada 30min para lembrar o tempo restante).
   - Contabilidade de Quota: `facekids/quota_agent_accounting.py` (`LegacyLedgerQuota`), descontando tempo apenas da criança identificada.
   - Reembolso de Inatividade: Se a criança se afasta por 120s sem mexer no mouse/teclado, o sistema bloqueia e **reembolsa** o saldo de inatividade.

---

## 2. Mapa dos Arquivos de Produção Windows vs. Laboratório/Linux

> [!IMPORTANT]
> A contabilidade de tempo em produção no Windows utiliza exclusivamente o **`LegacyLedgerQuota`** (`quota_agent_accounting.py`) integrado ao `Storage` (`storage.py`). Os módulos com prefixo `quota_broker_*` e `quota_vm_*` são protótipos de laboratório preservados para testes de regressão da CI e **não devem** ser chamados no fluxo principal de produção.

### A. Módulos de Produção Windows (Runtime Oficial)
| Arquivo | Função no Sistema de Produção |
|---|---|
| `facekids/admin_dashboard.py` | Painel dos Pais (Tkinter): gestão de crianças, quotas, bônus, horários e galeria de fotos |
| `facekids/admin_auth.py` | Autenticação administrativa dos pais para acesso ao painel |
| `facekids/auth_service.py` | Servidor Named Pipe IPC, identificação facial e coordenação de logon |
| `facekids/agent_watchdog.py` | Watchdog anti-burla do agente da conta Filhos com heartbeat e auto-recuperação |
| `facekids/boot_auth.py` | Inicialização do serviço em modo SYSTEM no boot do Windows |
| `facekids/children_pilot.py` | Captura de 12 fotos da webcam (sem retângulo verde sobreposto) e cálculo de embeddings |
| `facekids/child_quota_pilot.py` | Verificação monotônica de saldo de quotas e bônus |
| `facekids/filhos_agent.py` | Agente residente na sessão Filhos: toasts, quota, inatividade e bloqueio |
| `facekids/welcome_screen.py` | Tela de boas-vindas Tkinter com avatar e saldo de tempo restante |
| `facekids/storage.py` | Banco de dados SQLite (`kids.sqlite3`), perfis, fotos e horários permitidos |
| `facekids/quota_agent_accounting.py` | Motor oficial de débito de quotas (`LegacyLedgerQuota`) |
| `facekids/recognition.py` | Modelos YuNet e SFace para reconhecimento facial rápido e local |
| `facekids/session.py` | Consulta nativa Win32 WTS do estado da sessão (ACTIVE/LOCKED) |
| `facekids/session_transition_policy.py` | Política de alternância suave de perfis entre irmãos no mesmo computador |
| `facekids/locker.py` | Chamada segura de `LockWorkStation` no Windows |
| `facekids/pipe_protocol.py` | Protocolo e serialização de mensagens Named Pipe IPC |
| `facekids/ipc_reply.py` | Validação de observações faciais tipadas do pipe |
| `facekids/ipc_json.py` | Leitor defensivo de arquivos JSON locais |
| `facekids/avatar_utils.py` | Tratamento e persistência das fotos das crianças |
| `facekids/ui_theme.py` | Paleta Catppuccin Macchiato padronizada |
| `facekids/platform_paths.py` | Resolução do diretório oficial `C:\ProgramData\FaceKids` |
| `facekids/windows_pipe_api.py` | Configuração Win32 de handles e buffers para Named Pipes |

### B. Módulos de Laboratório e Testes Experimentais (NÃO USAR EM PRODUÇÃO)
- `facekids/quota_broker_*`: Protótipos de broker SCM para arquitetura de microserviços.
- `facekids/quota_vm_*`: Diagnósticos e testes em máquinas virtuais Hyper-V.

### C. Módulos Exclusivos Linux / Regata OS (NÃO USAR NO WINDOWS)
- `facekids/linux_admin.py`
- `facekids/linux_auth.py`
- `facekids/linux_pam_helper.py`
- `facekids/linux_probe.py`
- `facekids/linux_runtime.py`

---

## 3. Scripts Principais de Operação no Windows

- **`Instalar-FaceUnlock.bat`**: Instala a DLL nativa do Credential Provider, registra no COM e agenda o serviço e o agente.
- **`abrir-facekids.bat`**: Abre o Painel dos Pais para gerenciar filhos, quotas, bônus e galeria de fotos.
- **`Ativar-Desbloqueio-No-Boot.bat`**: Configura o serviço facial para iniciar como SYSTEM antes mesmo do primeiro login.
- **`Desinstalar-FaceUnlock.bat`**: Desfaz o registro COM e remove as tarefas agendadas, mantendo o banco e as fotos intactos.
