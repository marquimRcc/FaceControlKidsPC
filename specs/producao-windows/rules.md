# Rules — Regras de Negócio de Produção (FaceControlKidsPC)

**Versão:** 1.0  
**Data:** 2026-11-05  
**Escopo:** Produção Windows física — conta `Filhos`  
**Fonte:** `facekids/filhos_agent.py`, `quota_agent_accounting.py`, `agent_watchdog.py`, `storage.py`, `session_transition_policy.py`

> [!NOTE]
> Cada regra é identificada por código único `R-NN`. Referências a código incluem o módulo de origem. Regras de laboratório/VM são explicitamente excluídas desta lista.

---

## Bloco 1 — Identidade e Autenticação

**R-01 — Conta exclusiva gerenciada**  
O Credential Provider C++ intercepta o logon **exclusivamente** da conta `Filhos` (filtro por SID). Contas de administradores e demais usuários nunca passam pelo fluxo facial.  
*Fonte: `native/credential_provider_facekids/`*

**R-02 — SID Binding do Named Pipe**  
O Named Pipe `\\.\pipe\FaceKidsAuthPipe` possui DACL configurada para aceitar conexões apenas do SID da conta `Filhos`. O serviço SYSTEM pode criar o pipe; a conta Filhos pode conectar-se.  
*Fonte: `facekids/windows_pipe_api.py`, `facekids/auth_service.py`*

**R-03 — Fonte de identidade em sessão é o serviço, nunca o JSON**  
O arquivo `last_unlock.json` é **UI-only** — serve apenas para disparar a tela de boas-vindas e lembretes visuais. A identidade da criança (child_id que debita quota) só pode ser alterada por uma resposta validada do `auth_service` via Named Pipe. Um processo da conta `Filhos` pode editar o JSON, portanto nunca atribui autoridade de quota.  
*Fonte: `filhos_agent.py` comentário: "Notification file is UI-only. It must not change identity"*

**R-04 — Tolerância a webcam ocupada (ERROR_CAMERA)**  
Se o serviço facial retornar `ERROR_CAMERA` durante uma `SESSION_QUERY` (webcam em uso por outro app, ex.: videochamada ou navegador), o agente **mantém o perfil ativo atual** sem alterar saldo ou bloquear a sessão.  
*Fonte: `filhos_agent.py` linhas ~695–703*

**R-05 — Senha fixa de AutoLogon**  
A conta `Filhos` usa senha fixa `"1"` exclusivamente para o mecanismo `KerbInteractiveLogon` do Credential Provider. Esta senha não deve ser alterada sem atualizar a DLL.  
*Fonte: `docs/ARQUITETURA-PRODUCAO-WINDOWS.md`*

**R-06 — Validação de observação facial tipada**  
Respostas do pipe em sessão (`SESSION_QUERY`) são validadas via `validated_face_observation()`. Respostas inconsistentes (status inválido, timestamp antigo > 60s, perfil não cadastrado) são descartadas sem ação.  
*Fonte: `facekids/ipc_reply.py`, `filhos_agent.py`*

---

## Bloco 2 — Quota e Contabilidade de Tempo

**R-07 — Motor único de débito (LegacyLedgerQuota)**  
`LegacyLedgerQuota` é o **único** adaptador de débito de quotas autorizado em produção. Nenhum outro módulo (`BrokerLabReadOnlyQuota`, `quota_broker_*`, `quota_vm_*`) pode emitir débitos ou decisões de bloqueio na sessão física.  
*Fonte: `quota_agent_accounting.py` docstring; `filhos_agent.py` linha ~570*

**R-08 — Intervalo de tick válido: 0,5s a 15s**  
O método `active_tick()` rejeita qualquer `seconds` fora do intervalo `[0.5, 15.0]`. Isso previne picos de débito após hibernação ou suspensão.  
*Fonte: `quota_agent_accounting.py` linha ~42*

**R-09 — Quota diária reseta à meia-noite**  
Ao detectar mudança de data (`date.today().isoformat() != today`), o tracker reinicia os avisos. O saldo é calculado por dia no SQLite.  
*Fonte: `filhos_agent.py` linhas ~619–621*

**R-10 — Avisos de tempo: 10 min, 5 min, 1 min**  
O agente emite toasts progressivos:
- ≤ 600s restantes → aviso de 10 minutos (uma vez por período)
- ≤ 300s restantes → aviso de 5 minutos (uma vez por período)
- ≤ 60s restantes → aviso de 1 minuto (uma vez por período)

Avisos são reiniciados quando o pai concede bônus que eleva o saldo acima do limite anterior.  
*Fonte: `filhos_agent.py` `QuotaTracker.check_notifications_and_lock()`*

**R-11 — Bloqueio automático ao esgotar a quota**  
Quando `remaining ≤ 0`, o agente exibe toast "Tempo Esgotado" (4s), aguarda 1,2s e executa `LockWorkStation()`. O Credential Provider na tela de logon impede o retorno enquanto a quota estiver zerada.  
*Fonte: `filhos_agent.py` linha ~466–481*

**R-12 — Lembrete visual a cada 30 minutos**  
Durante uso ativo, a cada 1800s de uso contínuo com saldo > 60s, o agente reexibe a tela de boas-vindas como lembrete de tempo restante.  
*Fonte: `filhos_agent.py` linhas ~772–775*

---

## Bloco 3 — Inatividade Física e Reembolso

**R-13 — Reembolso por inatividade física**  
Se o usuário ficar ≥ `lock_seconds` (padrão 120s) sem mover mouse ou teclado, o agente:
1. Calcula o reembolso: `min(idle_seconds, lock_seconds)`.
2. Chama `store.refund(child_id, refund, today)` no SQLite.
3. Exibe atualização do saldo no tracker.
4. Executa `LockWorkStation()`.

O tempo de inatividade **não** é cobrado da quota.  
*Fonte: `filhos_agent.py` linhas ~732–746*

**R-14 — Aviso de inatividade**  
Quando idle ≥ `warn_seconds` (padrão 100s), um toast de aviso é exibido uma única vez. O flag `inactivity_warned` é resetado quando idle < `warn_seconds` novamente.  
*Fonte: `filhos_agent.py` linhas ~747–758*

**R-15 — Idle cap pela duração ativa da sessão**  
O idle real é calculado como `min(get_user_idle_seconds(), active_duration)`, onde `active_duration` é o tempo decorrido desde que a sessão ficou `ACTIVE`. Isso previne falso idle logo após o desbloqueio.  
*Fonte: `filhos_agent.py` linha ~655*

**R-16 — Configuração de inatividade sobrescritível**  
Os valores padrão de `lock_seconds` (120s) e `warn_seconds` (100s) podem ser sobrescritos em `C:\ProgramData\FaceKids\configuracoes.json` pelos campos `inactivity_lock_seconds` e `inactivity_warn_seconds`. Mínimos forçados: `lock ≥ 30s`, `warn ≥ 10s`.  
*Fonte: `filhos_agent.py` `get_inactivity_settings()`*

---

## Bloco 4 — Estado da Sessão e Horário Permitido (Curfew)

**R-17 — Pausa automática quando sessão bloqueada (Win+L)**  
Quando `current_session_state()` retorna `LOCKED`, o agente não faz débito de quota, não emite toasts de aviso e encerra a tela de boas-vindas se estiver aberta.  
*Fonte: `filhos_agent.py` linhas ~641–642*

**R-18 — Bloqueio por horário de dormir (Curfew)**  
Se `store.is_curfew_active()` retornar `True` durante a sessão ativa, o agente exibe toast "Horário de Dormir" (4,5s), aguarda 1,2s, executa `LockWorkStation()` e aguarda mais 5s antes de reiniciar o clock de sessão.  
*Fonte: `filhos_agent.py` linhas ~708–726*

**R-19 — Reinício do clock de sessão após desbloqueio**  
Ao detectar transição de `LOCKED → ACTIVE`, o agente reinicia `session_active_since_mono` e `last_active_time` para evitar débito retroativo de tempo bloqueado.  
*Fonte: `filhos_agent.py` linhas ~643–646*

---

## Bloco 5 — Troca de Perfil entre Irmãos

**R-20 — Transição de perfil validada pela política**  
A troca de criança ativa é decidida por `decide_child_transition()` em `session_transition_policy.py`. A transição só ocorre se a observação facial for `ALLOW` e a política aprovar `SWITCH_CHILD`.  
*Fonte: `filhos_agent.py` linhas ~669–683*

**R-21 — Bloqueio se criança diferente sem quota/horário**  
Se uma observação facial retornar `DENY_QUOTA` ou `DENY_CURFEW` para uma criança diferente da atual, e a política indicar `SWITCH_CHILD`, o agente bloqueia a sessão imediatamente.  
*Fonte: `filhos_agent.py` linhas ~684–692*

**R-22 — Reset de clock ao trocar de criança**  
Ao aprovar uma troca de perfil, `session_active_since_mono` e `last_welcome_reminder_mono` são reiniciados para o novo perfil.  
*Fonte: `filhos_agent.py` linhas ~678–679*

---

## Bloco 6 — Watchdog Anti-Burla

**R-23 — Instância única via Mutex**  
O `filhos_agent.py` cria o Mutex `Local\FaceKidsFilhosAgentMutex` ao iniciar. Se o erro `ERROR_ALREADY_EXISTS` (183) for retornado, a instância duplicada encerra imediatamente.  
*Fonte: `filhos_agent.py` linhas ~556–559*

**R-24 — Heartbeat a cada 10s**  
O agente grava `agent_heartbeat.json` atomicamente (via `.tmp` + rename) a cada 10s enquanto a sessão estiver `ACTIVE`. O JSON contém `timestamp`, `pid` e `version: "1.0"`.  
*Fonte: `agent_watchdog.py` `write_agent_heartbeat()`; `filhos_agent.py` linhas ~607–652*

**R-25 — Watchdog: recuperação na 1ª falha**  
Se o heartbeat estiver ausente ou com idade > 45s enquanto a sessão `Filhos` estiver `ACTIVE`, o watchdog dispara a tarefa agendada `FaceKidsFilhosAgent` (1ª falha consecutiva = `RECOVERY_TRIGGERED`).  
*Fonte: `agent_watchdog.py` linhas ~224–227*

**R-26 — Watchdog: bloqueio preventivo na 2ª+ falha**  
Na 2ª falha consecutiva sem heartbeat, o watchdog executa `LockWorkStation()` preventivamente e tenta relançar o agente.  
*Fonte: `agent_watchdog.py` linhas ~229–238*

**R-27 — Watchdog: período de carência no startup**  
O watchdog concede `startup_grace_period` (padrão 60s) após inicialização. Durante a carência, retorna `GRACE_PERIOD` sem checar heartbeat.  
*Fonte: `agent_watchdog.py` linhas ~207–208*

**R-28 — Watchdog monitora somente conta Filhos ativa**  
Se o usuário do console ativo não for `Filhos` (ex.: conta de administrador na frente do PC), o watchdog retorna `NO_ACTION` sem contador de falhas.  
*Fonte: `agent_watchdog.py` linhas ~195–199*

---

## Bloco 7 — Fallback e Conta Administrador

**R-29 — Fallback para conta Administrador**  
A conta administrativa (ex.: `MarcosMiniPC`) nunca é interceptada pelo Credential Provider. Se o serviço facial estiver inativo ou a câmera indisponível, os pais podem sempre fazer login pela senha convencional da conta Administrador.  
*Fonte: `docs/ARQUITETURA-PRODUCAO-WINDOWS.md`*

**R-30 — Agente só roda na conta Filhos**  
Na inicialização, `run_agent()` verifica `USERNAME == "filhos"`. Se diferente, encerra imediatamente sem inicializar o tracker ou o banco.  
*Fonte: `filhos_agent.py` linhas ~549–552*

---

## Bloco 8 — Segurança e Privacidade

**R-31 — Biometria exclusivamente local e offline**  
Vetores biométricos, fotos e o banco SQLite nunca são transmitidos para serviços externos. Todo processamento é local.  
*Fonte: `INSTRUCOES-IA-SDD.md` Proibição Absoluta #4*

**R-32 — Sem dados biométricos em commits**  
Fotos de rostos, vetores e o banco `kids.sqlite3` de produção estão no `.gitignore` e nunca devem ser incluídos em commits.  
*Fonte: `INSTRUCOES-IA-SDD.md` Checklist Pré-Commit*

**R-33 — ACLs não podem ser rebaixadas para Everyone**  
Nenhuma ACL restritiva de segurança (DACLs do pipe, permissões do banco, ACEs de serviço) pode ser rebaixada para `Everyone` / `Todos`.  
*Fonte: `INSTRUCOES-IA-SDD.md` Checklist Pré-Commit*

**R-34 — Protocolo do Pipe: ASCII, sem nulos, máximo 512 bytes**  
Comandos aceitos pelo pipe: `AUTH_QUERY`, `SESSION_QUERY`, `QUERY`, `PING`. Payloads com caracteres nulos, não-ASCII ou tamanho > 512 bytes resultam em `INVALID_REQUEST`.  
*Fonte: `facekids/pipe_protocol.py`*

**R-35 — Detecção Passiva de Liveness**  
A autenticação facial requer verificação de vivacidade baseada na variância temporal dos marcos faciais YuNet ao longo de frames consecutivos. Se a variância for nula ou inferior ao limiar mínimo de micro-movimento (foto estática ou tela fixa), o serviço emite `DENY_SPOOF` e bloqueia a concessão de acesso.  
*Fonte: `facekids/liveness.py`, `facekids/auth_service.py`*

**R-36 — Reembolso Idempotente com Recibo e Session Epoch**  
Cada transição para estado `ACTIVE` gera um `session_epoch` criptograficamente aleatório. O método `refund()` persiste um recibo único na tabela `quota_refund_receipts`. Chamadas repetidas com o mesmo `session_epoch` retornam o saldo atual sem duplicar o estorno de tempo, e estornos são limitados ao saldo efetivamente consumido.  
*Fonte: `facekids/storage.py`, `facekids/filhos_agent.py`*

**R-37 — Blindagem NTFS de ProgramData\FaceKids**  
A pasta `C:\ProgramData\FaceKids` e seus arquivos devem possuir herança desabilitada (`/inheritance:d`) e permissões amplas de escrita para `Everyone` e `BUILTIN\Users` revogadas. SYSTEM e Administradores possuem Controle Total; binários e scripts executáveis são restritos contra adulteração por contas não privilegiadas.  
*Fonte: `scripts/Blindar-Permissoes-FaceKids.ps1`, `scripts/Instalar-FaceKids-Nativo.ps1`*
