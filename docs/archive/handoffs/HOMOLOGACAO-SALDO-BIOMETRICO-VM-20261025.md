# FaceKids — Saldo vinculado à biometria do serviço (laboratório, 25/10/2026)

**Escopo:** PR #4, branch `fix/facekids-ipc-security-hardening-20261024`. Não executar merge ou instalador. Esta etapa **não altera** o banco familiar, o Credential Provider registrado ou o agente instalado.

## Problema corrigido nesta etapa

Os três filhos compartilham o mesmo `TOKEN_USER` do Windows. Por isso **SID → ID fixo** no servidor não identifica a criança real. O serviço de laboratório de leitura original `FaceKidsQuotaLabOnly` permanece para ensaios anteriores, mas não é apropriado para saldos individuais de três rostos no mesmo login.

O novo endpoint `FaceKidsQuotaWriterBoundVmOnly` publica **somente um saldo da identidade facial ainda ativa no serviço**, nunca um ID escolhido pelo agente.

## Fluxo de autorização — SOMENTE VM

1. O SCM fornece o evento WTS de desbloqueio (não vem do agente).
2. O serviço LocalSystem observa a sessão física e compara `TOKEN_USER` com o SID infantil configurado em HKLM protegido.
3. `FaceAuthenticator` do serviço reconhece um dos perfis existentes no banco fictício, sem consumir `last_unlock.json` infantil.
4. `ServiceOwnedQuotaRuntime` vincula o `child_id` à sessão e ao epoch SCM sob lock compartilhado. Win+L, logoff, desconexão e troca de sessão revogam esse vínculo.
5. O serviço escreve débito/recibo no SQLite no seu **próprio thread de tick**, através de `charge_capped_once`. A thread de leitura do pipe **não acessa SQLite**.
6. `ServiceOwnedScmHost` permite uma resposta apenas quando existe um tick recente (até 3 intervalos de amostragem, mínimo de 3s), a criança do tick coincide com a **identidade facial verificada agora**, e SID/WTS/SCM não mudaram.
7. A thread SCM de leitura `serve_one_bound_vm_request` consulta o **SID real do chamador** por `ImpersonateNamedPipeClient`. A DACL do pipe autoriza apenas SYSTEM/Administrators e o SID infantil esperado. O corpo JSON tem apenas `version` e `action`. Só `GET_BOUND_BALANCE` é permitido; campos extras, `child_id`, `seconds`, `CHARGE` e `UNLOCK` são recusados.
8. `query_current_bound_vm_balance` (diagnóstico de VM) só aceita o PID da **instância do serviço SCM LocalSystem específica** `FaceKidsQuotaWriterVmOnly`. Retorna saldo e criança do vínculo atual, ou `None` quando não há vínculo válido. **Não controla LogonUI, quotas domésticas nem `LockWorkStation`.**

### Arquivos principais

| Arquivo | Responsabilidade |
| --- | --- |
| `facekids/quota_broker_policy.py` | Consultar identidade da lease já verificada, sem mutação |
| `facekids/quota_broker_wts.py` | Verificar conexão WTS, SID e estado Win+L |
| `facekids/quota_broker_runtime.py` | Verificar SID do cliente identificado pelo OS e perfil vinculado |
| `facekids/quota_broker_scm_host.py` | Snapshot efêmero de quota publicado somente depois do tick do serviço |
| `facekids/quota_broker_bound_protocol.py` | Contrato estrito e parser de resposta |
| `facekids/quota_broker_bound_transport_win.py` | Named Pipe do serviço LocalSystem com ACL e impersonação |
| `facekids/quota_broker_bound_client_win.py` | Diagnóstico read-only, com verificação do PID no SCM |
| `tests/test_quota_broker_bound.py` | Três perfis, Win+L, mudança SID, expiração e payloads forjados |
| `scripts/ci_scm_writer_vm_smoke.py` | Serviço Windows SCM real, conta infantil fictícia, DENY sem rosto e zero débito |

## Evidência de testes

No workflow *Unit tests*, o Windows executa **310 testes unitários** mais integração isolada no SCM e NTFS. O Ubuntu executa **310 testes unitários**. A compilação e smoke tests do Credential Provider continuam separados.

O teste real no runner Windows registrou o serviço de escrita sintético sob SYSTEM, criou três perfis fictícios, testou a consulta pelo token infantil e pelo token administrativo **sem reconhecimento**. Ambos obtiveram negação, sem inventar identidade; nenhum débito foi registrado, e serviço, conta, registro e arquivos temporários foram removidos. **Não há demonstração de webcam funcional na Sessão 0** nem de resposta positiva do SCM com rosto real: o caso positivo foi coberto somente pelo runtime de serviço com captura facial simulada e SQLite fictício.

Para a lógica (não instala serviço):

```powershell
python -m unittest discover -s tests -p "test_quota_broker_bound.py" -v
python -m unittest discover -s tests -p "test_quota_broker_scm_host.py" -v
```

A integração SCM/ACL automatizada é restrita ao **GitHub-hosted Windows runner**, `scripts/ci_scm_writer_vm_smoke.py`, e exige precondições para apagar integralmente recursos de laboratório. **Não execute esse script em máquina doméstica.**

## Portões que ainda impedem o corte produtivo

- **Facial positivo no Windows real:** verificar webcam física sob SYSTEM/Sessão 0 ou arquitetura alternativa de captura, liveness, falhas de câmera e troca de rostos.
- **Agente infantil protegido:** `filhos_agent.py` instalado ainda cobra diretamente pelo SQLite do modo legado. Esta etapa não desativou esse escritor. Precisa migração sem janela de dupla cobrança.
- **Saldo de produção:** o novo pipe está vinculado exclusivamente ao serviço **VM-only** e ao banco sintético marcado. O cliente não autoriza bloqueio automático: o agente só deverá controlar saldo/lock depois de um contrato de autoridade explicitamente homologado.
- **SQLite e rollback:** aplicar ACLs reais somente após backup consistente/WAL e restauração validada, sem depender do usuário infantil para abrir a base.
- **Winlogon e recuperação:** ensaio de login administrativo normal, Win+L, fast-user-switch, sleep, restart, snapshot externo e recuperação comprovada em VM interativa.
- **PR versus main:** reconciliar mudanças novas da `main` antes de qualquer merge. Manter PR #4 em rascunho até fechar portões.

**Conclusão:** integração do vínculo face→saldo→IPC em laboratório implementada, com regras de fail-closed. **Não está liberada para uso doméstico.**
