# Spec — Produção Windows (SafePCKids)

**Versão:** 1.0  
**Data:** 2026-11-05  
**Ambiente alvo:** Windows 10 / Windows 11 — Desktop Doméstico Físico  
**Status:** ACTIVE (em produção homologada desde out/2026)  
**Fonte de verdade:** Código-fonte do branch `main` + 339 testes CI verdes no SHA `96a9630b`

> [!IMPORTANT]
> Este documento descreve o **comportamento observável em produção física**. Não descreve laboratório de VM nem experimentos de broker. Qualquer alteração nesta spec requer aprovação formal antes de qualquer mudança no código.

---

## 1. Escopo do Sistema

O SafePCKids é um **sistema de controle parental biométrico** para Windows 10/11. Ele:

- **Intercepta a tela de logon** (`LogonUI`) exclusivamente para a conta compartilhada `Filhos`.
- **Autentica crianças por reconhecimento facial** usando webcam USB local (XWF-1080P ou compatível).
- **Gerencia quotas de tempo de tela** por perfil de criança, com contabilidade local offline.
- **Bloqueia o Windows automaticamente** ao esgotar a quota ou detectar inatividade.
- **Não intercepta a conta Administrador** — seu acesso permanece via fluxo nativo do Windows.

### 1.1 Fora do Escopo (Atual)

- Filtragem de conteúdo / Firewall parental.
- Sincronização de dados em nuvem.
- Suporte a múltiplas contas Windows de crianças (apenas a conta `Filhos` é gerenciada).
- Autologon automático (habilitado apenas após aprovação do M5).

---

## 2. Componentes de Produção

### 2.1 Camada C++ — Credential Provider (LogonUI)

| Atributo | Valor |
|---|---|
| Arquivo | `native/credential_provider_safepckids/SafePCKidsCredentialProvider.dll` |
| Instalação | `C:\ProgramData\SafePCKids\` (registrada via COM) |
| Visibilidade | Exclusivamente na tela de logon da conta `Filhos` (filtro por SID) |
| Protocolo IPC | Conecta via Named Pipe `\\.\pipe\SafePCKidsAuthPipe` |
| Autologon | `KerbInteractiveLogon` com senha fixa `"1"` ao receber status `ALLOW` |
| Conta Admin | Transparente — o Credential Provider não interfere na conta Administrador |

### 2.2 Camada Python — Serviço Central (Auth Service)

| Atributo | Valor |
|---|---|
| Módulo principal | `safepckids/auth_service.py` |
| Conta de execução | `SYSTEM` ou `Administrador` via Agendador de Tarefas no boot |
| Modelos biométricos | YuNet (detecção facial) + SFace (embedding 1:N) via OpenCV DNN |
| Banco de dados | SQLite local — `C:\ProgramData\SafePCKids\kids.sqlite3` |
| Named Pipe server | `\\.\pipe\SafePCKidsAuthPipe` |
| Segurança do Pipe | DACL com SID Binding exclusivo da conta `Filhos` |

### 2.3 Camada Python — Agente de Sessão (Filhos Agent)

| Atributo | Valor |
|---|---|
| Módulo | `safepckids/filhos_agent.py` |
| Conta de execução | Sessão interativa da conta `Filhos` |
| Scheduler | Agendador de Tarefas `SafePCKidsFilhosAgent` |
| Motor de quota | `LegacyLedgerQuota` em `quota_agent_accounting.py` — ÚNICO motor de débito |
| Fonte de identidade | `last_unlock.json` (UI-only) + verificação facial periódica via IPC |
| Aviso de inatividade | `warn_seconds` = `max(10, lock_seconds - 20)`, padrão 100s |
| Bloqueio por inatividade | `lock_seconds` = padrão 120s (configurável via `configuracoes.json`) |
| Verificação facial em sessão | `SESSION_QUERY` via Named Pipe, intervalo padrão 120s (configurável) |

### 2.4 Componentes de Suporte

| Módulo | Função |
|---|---|
| `safepckids/agent_watchdog.py` | Watchdog anti-burla: monitora heartbeat do `filhos_agent.py` a cada 15s |
| `safepckids/welcome_screen.py` | Tela de boas-vindas Tkinter (avatar + saldo). Auto-fecha em 4s. |
| `safepckids/storage.py` | Acesso ao SQLite (`kids.sqlite3`): perfis, fotos, horários, quotas |
| `safepckids/recognition.py` | Modelos YuNet/SFace para identificação facial rápida e local |
| `safepckids/children_pilot.py` | Cadastro biométrico: captura 12 fotos sem retângulo sobreposto |
| `safepckids/session.py` | WTS Win32: detecta estado `ACTIVE` / `LOCKED` da sessão |
| `safepckids/locker.py` | `LockWorkStation()` Win32 seguro |
| `safepckids/pipe_protocol.py` | Decodificador de comandos do Named Pipe (bounded, ASCII-only) |
| `safepckids/liveness.py` | Detecção de vivacidade facial passiva: variância temporal de marcos faciais YuNet para rejeição de fotos estáticas |

---

## 3. Módulos NÃO Usados em Produção

> [!WARNING]
> Os módulos abaixo existem no repositório mas **NÃO devem ser chamados no fluxo de produção**.

| Prefixo | Propósito | Uso Permitido |
|---|---|---|
| `quota_broker_*` | Protótipos de broker SCM para microserviços | Apenas testes de laboratório (CI) |
| `quota_vm_*` | Diagnósticos em Hyper-V / VM | Apenas testes de laboratório (CI) |
| `linux_*` | PAM, auth e admin do Regata OS Linux | Apenas CI Linux — nunca no Windows |
| `filhos_bound_vm_agent.py` | Agente bound a VM | Somente laboratório |
| `filhos_quota_vm_readonly.py` | Leitura somente de VM | Somente laboratório |

---

## 4. Arquivos Físicos e Caminhos de Produção

| Recurso | Caminho |
|---|---|
| Banco SQLite | `C:\ProgramData\SafePCKids\kids.sqlite3` |
| DLL Credential Provider | `C:\ProgramData\SafePCKids\SafePCKidsCredentialProvider.dll` |
| Log do Agente | `C:\ProgramData\SafePCKids\filhos_agent.log` |
| Heartbeat do Agente | `C:\ProgramData\SafePCKids\agent_heartbeat.json` |
| Último desbloqueio (UI) | `C:\ProgramData\SafePCKids\last_unlock.json` |
| Configurações | `C:\ProgramData\SafePCKids\configuracoes.json` |
| Modelos ML | `models/face_detection_yunet_*.onnx`, `models/face_recognition_sface_*.onnx` |

---

## 5. Scripts de Operação Windows

| Script | Função |
|---|---|
| `Instalar-FaceUnlock.bat` | Instala DLL, registra COM, agenda serviço e agente |
| `Desinstalar-FaceUnlock.bat` | Remove registro COM e tarefas agendadas (preserva banco e fotos) |
| `Ativar-Desbloqueio-No-Boot.bat` | Habilita o serviço facial como SYSTEM antes do primeiro login |
| `abrir-safepckids.bat` | Abre o Painel dos Pais (`admin_dashboard.py`) |
| `scripts/Iniciar-Teste-Adulto-Filhos.ps1` | Teste presencial voluntário com rosto adulto (M1 — sem autologon) |
| `scripts/Blindar-Permissoes-SafePCKids.ps1` | Endurecimento NTFS de permissões (SYSTEM/Admin Full, remoção de Everyone/Users write, proteção da DLL, configs e scripts .bat) |

---

## 6. Painel dos Pais (Admin Dashboard)

- Módulo: `safepckids/admin_dashboard.py` (Tkinter)
- Autenticação: `safepckids/admin_auth.py`
- Funcionalidades: cadastro de crianças, configuração de quotas diárias, bônus de tempo, horários permitidos (curfew), galeria de fotos, 3 temas visuais (Catppuccin Macchiato padrão)

---

## 7. Limitações Conhecidas e Impeditivos Estruturais

1. **Webcam USB na Sessão 0 (SYSTEM):** A captura de frames em contexto SYSTEM (isolado do desktop) ainda não foi validada fisicamente. Risco de falha silenciosa de abertura da câmera. *(Bloqueador do M2)*
2. **Autologon não ativado em produção:** O fluxo de `KerbInteractiveLogon` existe no C++, mas não está habilitado no PC familiar até M5 ser aprovado.
3. **Reembolsos de inatividade com recibo:** Implementada geração de `session_epoch` e persistência idempotente na tabela `quota_refund_receipts` (`safepckids/storage.py` e `safepckids/filhos_agent.py`), prevenindo duplicação de saldo após suspensão/hibernação.
4. **Liveness passivo ativo:** Implementada verificação de micro-movimento temporal sobre os marcos faciais do YuNet (`safepckids/liveness.py`), rejeitando automaticamente tentativas de spoofing por fotos estáticas.
5. **Generalização 1+ de perfis:** O piloto foi generalizado, mas scripts e instalador antigos podem conter suposições de exatamente 3 perfis. Auditoria necessária antes de M4.
6. **PR #4 é draft:** O branch de security hardening não foi mergeado à `main`. Integração exige análise e testes.
