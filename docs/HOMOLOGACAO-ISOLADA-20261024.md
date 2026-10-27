# FaceKids — homologação integrada isolada (24/10/2026)

**Resultado: APROVADO no escopo de laboratório; NÃO homologado para instalação doméstica.**

## Evidências GitHub Actions

Commit de código e workflow: `d0264f707c403f63309e806cd1d5b27f85914759`.

- Unit tests: https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40150516399 — **Windows SUCCESS** e **Ubuntu SUCCESS**.
- Credential Provider: https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40150516352 — **build real SUCCESS** e **COM/IPC diagnóstico SUCCESS**.

O script `scripts/ci_quota_isolated_acceptance.py` roda em ambos os sistemas no workflow de testes, produz somente evidência JSON sintética, não instala programa e não lê dados reais das crianças.

## Matriz de aceite executada

| Cenário | Resultado | Evidência |
| --- | --- | --- |
| Banco temporário e três crianças fictícias | APROVADO | `facekids-quota-accept-*` via `TemporaryDirectory` |
| Mesmo SID da conta Windows, perfis infantis diferentes | APROVADO | Débitos independentes 4 s, 3 s e 2 s |
| Sessão sem unlock SCM | NEGADO conforme esperado | 0 s cobrados |
| Identidade verificada e tempo monotônico | APROVADO | `VerifiedWtsQuotaWorker` + `ServiceOwnedQuotaBroker` |
| Lock/Win+L simulado seguido de unlock sem novo rosto | NEGADO conforme esperado | Lease revogado; 0 s até novo binding |
| Troca de sessão WTS | NEGADO conforme esperado | Lease invalidado |
| Tentativa infantil de enviar `CHARGE`, ID ou duração via IPC | NEGADO conforme esperado | `handle_broker_read` aceita apenas GET_BALANCE/PING |
| Idempotência e recibos persistidos | APROVADO | 3 recibos SQLite em transações com débito |
| Backup/restauração WAL-consistente e limpeza no Windows | APROVADO | `sqlite3.Connection.backup` e `contextlib.closing` |
| Gravação em SQLite aberto em `mode=ro` | NEGADO conforme esperado | `sqlite3.OperationalError` |
| Compilação do CP real e host C++ diagnóstico | APROVADO | CI C++ acima |
| SCM e ACL reais de conta infantil **sintética** | APROVADO no runner | Etapas Windows existentes no mesmo workflow; nenhuma conta real da família |

### Falha encontrada e corrigida durante o ensaio

O primeiro ensaio Windows apontou `WinError 32` ao remover `snapshot-only.sqlite3`: o context manager de `sqlite3.Connection` apenas controla commit/rollback, **não fecha o handle**. Commit `d0264f70` passou a usar `contextlib.closing` em todas as conexões de backup e restauração. A repetição do pipeline passou nos dois sistemas.

### Correção de segurança incorporada

- `facekids/quota_broker_wts.py`: lock, disconnect ou observação WTS inativa revoga o lease facial anterior, não só pausa a cobrança; o desbloqueio não restabelece a identidade da criança automaticamente.
- `tests/test_quota_broker_wts.py`: testes atualizados exigem novo vínculo facial confiável após lock ou restart.
- Esses módulos ainda são componentes de laboratório; não substituem o agente legado instalado.

## Escopo NÃO coberto / bloqueios de produção

1. O Credential Provider doméstico não foi registrado, atualizado ou exercitado no Winlogon físico. O SID esperado do servidor continua dependendo de configuração HKLM opt-in e validação de propriedade do serviço.
2. O serviço de laboratório continua principalmente read-only; o worker WTS que debita banco sintético ainda não está ligado a eventos faciais comprovadamente autenticados nem é o escritor exclusivo do SQLite familiar.
3. Não houve migração de ACL, banco, fotos, tarefas ou registry HKLM reais do PC da família. Os testes com usuário restrito foram executados somente em host Windows descartável.
4. Desbloqueio com webcam real, liveness anti-replay, recuperação do logon após falha de DLL, alternância entre 3 crianças reais e rollback do Winlogon precisam de VM restaurável com os componentes nativos e posterior aceite supervisionado.
5. A branch `fix/facekids-ipc-security-hardening-20261024` permanece isolada; PR #4 em rascunho, sem merge para `main` ou handoff.

**Decisão:** aceitar a homologação de regressão sintética, manter **BLOQUEADA** qualquer instalação automática no PC familiar.
