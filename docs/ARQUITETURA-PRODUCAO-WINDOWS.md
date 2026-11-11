# SafePCKids — Arquitetura de Produção Windows (10/11)

**Data de Homologação:** Outubro / 2026  
**Ambiente Alvo:** Windows 10 e Windows 11 (Desktop Doméstico Físico)  
**Conta Compartilhada:** `Filhos` (senha fixa `"1"` para AutoLogon pelo Credential Provider)  
**Conta Administradora:** Intacta, nunca interceptada pelo Credential Provider

---

## 1. Visão Geral da Arquitetura

O SafePCKids é um sistema de controle parental biométrico e controle de tempo de tela para Windows 10/11. Ele opera em três camadas coordenadas:

1. **Camada de Logon / LogonUI (C++ Nativo):**
   - DLL: `native/credential_provider_safepckids/SafePCKidsCredentialProvider.dll` (instalada em `C:\ProgramData\SafePCKids\`).
   - Visível **exclusivamente** na conta `Filhos` (filtragem por SID).
   - Consulta o serviço Python via Named Pipe `\\.\pipe\SafePCKidsAuthPipe`.
   - Ao receber `ALLOW`, executa AutoLogon transparente via `KerbInteractiveLogon` com senha `"1"`.

2. **Camada de Serviço Central (Python SYSTEM / Administrador):**
   - Serviço: `safepckids/auth_service.py` (executado via Agendador de Tarefas no Boot como `SYSTEM` ou no logon).
   - Biometria: OpenCV DNN com modelos **YuNet** (detecção facial) e **SFace** (extração e comparação vetorial).
   - Fonte de Dados: SQLite local em `C:\ProgramData\SafePCKids\kids.sqlite3`.
   - Proteção Anti-Burla: `safepckids/agent_watchdog.py` monitora o processo `filhos_agent.py` na sessão ativa e previne uso indevido caso o processo seja finalizado.

3. **Camada de Sessão do Usuário (Python na conta Filhos):**
   - Agente: `safepckids/filhos_agent.py` (iniciado na sessão interativa do usuário `Filhos`).
   - Tela de Boas-Vindas: `safepckids/welcome_screen.py` (auto-fecha em 4s e reabre a cada 30min para lembrar o tempo restante).
   - Contabilidade de Quota: `safepckids/quota_agent_accounting.py` (`LegacyLedgerQuota`), descontando tempo apenas da criança identificada.
   - Reembolso de Inatividade: Se a criança se afasta por 120s sem mexer no mouse/teclado, o sistema bloqueia e **reembolsa** o saldo de inatividade.

---

## 2. Mapa dos Arquivos de Produção Windows vs. Laboratório/Linux

> [!IMPORTANT]
> A contabilidade de tempo em produção no Windows utiliza exclusivamente o **`LegacyLedgerQuota`** (`quota_agent_accounting.py`) integrado ao `Storage` (`storage.py`). Os módulos com prefixo `quota_broker_*` e `quota_vm_*` são protótipos de laboratório preservados para testes de regressão da CI e **não devem** ser chamados no fluxo principal de produção.

### A. Módulos de Produção Windows (Runtime Oficial)
| Arquivo | Função no Sistema de Produção |
|---|---|
| `safepckids/admin_dashboard.py` | Painel dos Pais (Tkinter): gestão de crianças, quotas, bônus, horários e galeria de fotos |
| `safepckids/admin_auth.py` | Autenticação administrativa dos pais para acesso ao painel |
| `safepckids/auth_service.py` | Servidor Named Pipe IPC, identificação facial e coordenação de logon |
| `safepckids/agent_watchdog.py` | Watchdog anti-burla do agente da conta Filhos com heartbeat e auto-recuperação |
| `safepckids/boot_auth.py` | Inicialização do serviço em modo SYSTEM no boot do Windows |
| `safepckids/children_pilot.py` | Captura de 12 fotos da webcam (sem retângulo verde sobreposto) e cálculo de embeddings |
| `safepckids/child_quota_pilot.py` | Verificação monotônica de saldo de quotas e bônus |
| `safepckids/filhos_agent.py` | Agente residente na sessão Filhos: toasts, quota, inatividade e bloqueio |
| `safepckids/welcome_screen.py` | Tela de boas-vindas Tkinter com avatar e saldo de tempo restante |
| `safepckids/storage.py` | Banco de dados SQLite (`kids.sqlite3`), perfis, fotos e horários permitidos |
| `safepckids/quota_agent_accounting.py` | Motor oficial de débito de quotas (`LegacyLedgerQuota`) |
| `safepckids/recognition.py` | Modelos YuNet e SFace para reconhecimento facial rápido e local |
| `safepckids/session.py` | Consulta nativa Win32 WTS do estado da sessão (ACTIVE/LOCKED) |
| `safepckids/session_transition_policy.py` | Política de alternância suave de perfis entre irmãos no mesmo computador |
| `safepckids/locker.py` | Chamada segura de `LockWorkStation` no Windows |
| `safepckids/pipe_protocol.py` | Protocolo e serialização de mensagens Named Pipe IPC |
| `safepckids/ipc_reply.py` | Validação de observações faciais tipadas do pipe |
| `safepckids/ipc_json.py` | Leitor defensivo de arquivos JSON locais |
| `safepckids/avatar_utils.py` | Tratamento e persistência das fotos das crianças |
| `safepckids/ui_theme.py` | Paleta Catppuccin Macchiato padronizada |
| `safepckids/platform_paths.py` | Resolução do diretório oficial `C:\ProgramData\SafePCKids` |
| `safepckids/windows_pipe_api.py` | Configuração Win32 de handles e buffers para Named Pipes |

### B. Módulos de Laboratório e Testes Experimentais (NÃO USAR EM PRODUÇÃO)
- `safepckids/quota_broker_*`: Protótipos de broker SCM para arquitetura de microserviços.
- `safepckids/quota_vm_*`: Diagnósticos e testes em máquinas virtuais Hyper-V.

### C. Módulos Exclusivos Linux / Regata OS (NÃO USAR NO WINDOWS)
- `safepckids/linux_admin.py`
- `safepckids/linux_auth.py`
- `safepckids/linux_pam_helper.py`
- `safepckids/linux_probe.py`
- `safepckids/linux_runtime.py`

---

## 3. Scripts Principais de Operação no Windows

- **`Instalar-FaceUnlock.bat`**: Instala a DLL nativa do Credential Provider, registra no COM e agenda o serviço e o agente.
- **`abrir-safepckids.bat`**: Abre o Painel dos Pais para gerenciar filhos, quotas, bônus e galeria de fotos.
- **`Ativar-Desbloqueio-No-Boot.bat`**: Configura o serviço facial para iniciar como SYSTEM antes mesmo do primeiro login.
- **`Desinstalar-FaceUnlock.bat`**: Desfaz o registro COM e remove as tarefas agendadas, mantendo o banco e as fotos intactos.
