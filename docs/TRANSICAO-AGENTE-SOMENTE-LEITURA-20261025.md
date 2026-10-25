# FaceKids — transição do agente Filhos: fronteira de escrita e leitura (25/10/2026)

## Escopo desta rodada

O agente legado recebeu um adaptador explícito, `LegacyLedgerQuota`, que é o único ponto do **loop de cobrança** onde `Storage.charge` continua acessível. O comportamento doméstico permanece como antes. A troca para serviço ainda não está ativada: a instalação familiar **não** foi modificada.

Também foi acrescentado um adaptador `BrokerLabReadOnlyQuota` de **observação não autoritativa**, com o objetivo de testar as consultas ao serviço SCM sem abrir SQLite na conta infantil e sem permitir cobrança/bloqueio por dados recebidos na rede/Named Pipe.

| Função | Agente legado atual | Adaptador de leitura de laboratório |
| --- | --- | --- |
| Consultar saldo | SQLite local | `GET_BALANCE` ao SCM de laboratório |
| Descontar tempo | `LegacyLedgerQuota.active_tick` → `Storage.charge` | **Nenhum método de débito** |
| Trocar identidade infantil | Metadados legados + verificações locais | **Nenhuma operação de troca** |
| Bloquear Windows por saldo | Como antes no agente legado | **Proibido:** `may_enforce_lock=False` |
| Persistir dados no agente | Sim, no modo antigo | Não |
| Ativar por variável de ambiente do filho | Não | **Não há chave para substituir o modo doméstico** |
| Qualificar para corte produtivo | Não | **Não, ainda é leitura de laboratório** |

## Fortalecimento do Named Pipe de leitura

- O cliente busca o **PID real da outra ponta** com `GetNamedPipeServerProcessId` e confere esse PID contra o serviço **exato** `FaceKidsQuotaLabOnly` em execução, consultando a identidade `LocalSystem` registrada no SCM com `QueryServiceStatusEx` e `QueryServiceConfigW` **antes de escrever a requisição**. A consulta direta de token SYSTEM pode falhar para usuário padrão e não é utilizada no cliente principal.
- Um pipe servido por um processo comum no runner é recusado; o pipe real SCM iniciado sob SYSTEM precisa corresponder ao PID e à conta do serviço cadastrado.
- Repostas fora do contrato, campos extras (`child_id`, `elapsed_seconds`), tempos NaN/infinito/negativos, contraditórios (saldo zero + permitido) e falhas de transporte não autorizam ações.
- Essa validação é **apenas defesa adicional**. PID/nome/conta SCM isoladamente **não bastam** para confiar nos valores, porque falta vincular o endpoint a um serviço SCM específico com configuração protegida e um identificador facial atual. O cliente de laboratório não deve controlar `LockWorkStation` ou login Windows.

## Comprovação automatizada

`tests/test_quota_agent_accounting.py`:
- três crianças fictícias e um débito legado isolado;
- o adaptador de observação não possui `active_tick` ou `charge`;
- erro de pipe, negação e payload forjado não podem cobrar, bloquear nem escolher uma criança;
- consulta feita por `ReadOnlyQuotaView` sem alterar os saldos;
- auditoria de que o loop legado usa `LegacyLedgerQuota` em vez de `store.charge` inline.

`tests/test_quota_broker_transport_win.py`: processo comum recusado pela inspeção do token do Named Pipe; transporte unitário do pipe testado com bypass de **teste apenas** para a verificação por SCM. O teste de SCM real exige PID e conta registrados.

`scripts/ci_scm_lab_smoke.py`: conta Windows sintética usa a consulta do adaptador no Named Pipe **real** do serviço `FaceKidsQuotaLabOnly` sob SYSTEM. O administrador é recusado pela ACL/mapeamento e nenhuma cobrança ocorre.

## Pendências bloqueadoras — não chamar de corte concluído

1. **Saldo por criança:** o serviço de escrita de VM usa WTS + reconhecimento facial para escolher o filho, mas ainda não oferece um endpoint de consulta que devolva o saldo da **identidade vinculada atualmente**. O serviço de consulta de laboratório é separado e usa mapeamento fixo de SID → ID, inadequado para três filhos na mesma conta Windows.
2. **Servidor imutável/atestado:** além de TOKEN_USER = SYSTEM, validar identidade específica do serviço SCM, o protocolo e o ciclo de vida; hoje o saldo de laboratório ainda não pode decidir bloqueios.
3. **Agente sem SQLite:** integrar o novo leitor no loop da conta Filhos *somente depois* de o serviço SCM publicar um contrato protegido e testado; remover de fato `Storage` do agente para banco protegido. Nunca usar `last_unlock.json` ou mensagens infantis como prova de identidade.
4. **Parar escrita duplicada:** não executar `Storage.charge` no agente e no SCM no mesmo banco/perfil. Fazer migração com banco/WAL/SHM protegidos, backup restaurável e teste real de token `Filhos`.
5. **VM interativa:** teste Win+L, troca das três crianças, sessão 0/câmera, login administrativo normal, snapshot e restauração realmente realizados.

O novo código está isolado no PR #4, não na `main`. Nenhum instalador, serviço doméstico, banco familiar, tarefa ou Credential Provider de produção foi alterado.
