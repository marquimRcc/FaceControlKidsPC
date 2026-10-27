# FaceKids — broker de quotas: laboratorio Windows (sem instalacao)

**Status:** prototipo de laboratorio, nao e um Windows Service registrado e
NAO substitui o controle de quotas atualmente em uso pela conta Filhos.

## Entrega tecnica desta rodada

1. `quota_broker_protocol.py` — `FACEKIDS_QUOTA_V1`, apenas `PING` e
   `GET_BALANCE`. Campos de identidade, data, debito, bonus e perfil
   enviados por clientes sao recusados. A identidade entra exclusivamente
   pelo adaptador Windows que conhece o token da conexao.
2. `quota_broker_transport_win.py` — laboratorio com pipe de instancia
   unica, `PIPE_REJECT_REMOTE_CLIENTS`, ACL explicita e SID de cliente
   extraido sob `ImpersonateNamedPipeClient`/`OpenThreadToken`.
   `RevertToSelf` sempre executado. Nao registra tarefa ou servico.
3. `quota_broker_read_store.py` — acesso `mode=ro` e
   `PRAGMA query_only=ON`. O agente nao escolhe o ID do banco e nao
   recebe nenhuma operacao que grave no ledger.
4. `quota_broker_client_win.py` — cliente somente consulta para o pipe
   lab, com validacao de estrutura de resposta. **Nao autentica o
   servidor remoto e suas respostas nao podem controlar Winlogon, quotas
   ou LockWorkStation.**
5. `quota_broker_lab.py` — comando `--vm-lab-only`, exige caminho
   especifico `facekids-quota-lab`, SID e ID de cadastro de testes.
6. `quota_broker_migration.py` — backup WAL-consistente via
   `sqlite3.Connection.backup`, checagem de integridade e publicacao
   em arquivo NOVO dentro do diretorio de laboratorio, sem sobrescrever.
7. Testes `test_quota_broker_*.py` — identidade permitida e negada,
   trafego Named Pipe sintetico em Windows, rejeicao de comandos
   manipulados, DB somente leitura, backup, retorno a snapshot anterior,
   protecao contra overwrite e fixture corrompido.

## Procedimento manual FUTURO, exclusivamente VM descartavel

Em uma VM Windows com clone do repositorio, usando somente perfis ficticios:

- Criar uma pasta dedicada `facekids-quota-lab` em um diretorio temporario.
- Criar nela um banco SQLite **sintetico** usando o CLI de cadastros de teste;
  nunca copiar fotos, embeddings ou bases reais sem consentimento especifico.
- Verificar o SID da conta de teste com `whoami /user`.
- Iniciar o host SOMENTE de diagnostico com:
  `python -m facekids.quota_broker_lab --vm-lab-only --database "<fixture>" --client-sid "<SID-de-teste>" --child-id 1 --pipe-suffix 0123456789abcdef0123456789abcdef`
- Em outro terminal da MESMA VM, efetuar UMA consulta somente leitura
  usando `facekids.quota_broker_client_win.query_lab_balance` no pipe
  `\\.\pipe\FaceKidsQuotaBrokerLab-0123456789abcdef0123456789abcdef`.
- Repetir com SID nao autorizado e verificar `DENY`.
- Testar snapshot/rollback apenas copiando dados no proprio laboratorio;
  nao executar `icacls`, `regsvr32` nem scripts de instalacao.

Nao ativar politica SID no Credential Provider real nem alterar as tarefas
existentes ate uma VM/snapshot validar login convencional e reversao.

## BLOQUEIOS restantes antes de uso real

- **Servico Windows SCM nao implementado/instalado:** falta hospedar o
  broker em processo com identidade protegida, ciclo de vida, supervisao,
  recuperacao, eventos WTS e monitoramento; a versao lab processa um
  pedido e encerra.
- **Identidade de servidor para o agente:** o cliente lab nao valida PID/SID
  do processo servidor, logo suas respostas sao apenas diagnosticas.
- **ACLs NTFS reais:** binarios e ledger ainda compartilham diretorio
  historicamente gravavel pela conta Filhos; nunca instalar o prototipo
  sobre esses caminhos.
- **Integracao ao FilhosAgent:** modo opt-in de diagnostico **shadow-only**
  implementado; o agente ainda debita o SQLite legado diretamente e
  ignora a resposta do broker para bloqueio e autorizacao.
- **Rollback automatico de instalacao:** ha backup/ensaio de restauracao
  somente de fixture; nao ha rollback COM/registro/tarefa comprovado.
- **Timeout no host lab:** IO e bloqueante por simplicidade; nao executar
  como servico permanente. Exige IO cancelavel e shutdown seguro antes
  de integrar.
- **Biometria/Win+L:** nenhum teste real de Winlogon, cameras ou anti-spoof
  foi feito nesta rodada.

O PR #4 permanece em rascunho sobre a branch handoff. Main, instalacao
familiar, credenciais e rostos nao foram alterados.

## Shadow mode — laboratorio, NUNCA como fonte de autorizacao

A conta Filhos pode, exclusivamente em VM com broker lab, iniciar o agente
com as variaveis de ambiente de teste:
- `FACEKIDS_QUOTA_BROKER_SHADOW=1`
- `FACEKIDS_QUOTA_LAB_SUFFIX=0123456789abcdef0123456789abcdef`

O sampler roda numa thread daemon e compara periodicamente apenas os
saldos, registrando `matched`, `diverged` ou `broker-unavailable`.
Nao altera `QuotaTracker`, `Storage.charge` ou `lock_current_session`.
O cliente lab NAO valida SID do servidor, portanto sua resposta jamais
pode conceder acesso, cobrar, alterar perfis ou solicitar bloqueio.

Teste unitario `tests/test_quota_broker_shadow.py` verifica esse contrato.
