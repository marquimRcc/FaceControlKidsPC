# FaceKids — plano de isolamento do ledger de quotas

**Status: projeto de migração / prova de conceito, NÃO implantado.**

## O que existe nesta branch

- `facekids/quota_broker_clock.py`: relógio de débito por criança e sessão WTS, com limite de amostragem e pausa quando a sessão não está ativa.
- `facekids/quota_broker_policy.py`: motor de decisão e cobrança, sem listener IPC nem registro de serviço Windows.
- `Storage.charge_up_to_available`: transação SQLite `BEGIN IMMEDIATE` que impede cobrar além do saldo mesmo com dois escritores cooperativos.
- Testes em `tests/test_quota_broker_clock.py`, `tests/test_quota_broker_policy.py` e `tests/test_storage.py`.

**Isso NÃO protege o banco enquanto Filhos puder alterá-lo diretamente.**
Um processo da conta Filhos ainda pode escrever no SQLite, e o agente atual continua usando `Storage.charge`. Nenhum serviço privilegiado foi iniciado, nenhuma ACL foi modificada e nenhuma credencial foi alterada.

## Fronteira de confiança prevista

1. Processo confiável hospedado em uma conta dedicada (ou SYSTEM com permissões minimizadas), binários e scripts instalados em diretório sem permissão de escrita para Filhos.
2. O serviço identifica a sessão interativa por **token real do Windows/WTS**. Mensagens de usuário NÃO podem escolher `child_id`, `session_id`, `seconds`, `day` ou estado de desbloqueio.
3. Associação `child_id ↔ session_id` nasce de um evento de reconhecimento cuja origem foi autenticada; `last_unlock.json` e o protocolo `FACEKIDS_IPC_V1` **não** são provas de origem.
4. O serviço lê `time.monotonic()` e a data local no próprio processo. Somente ele chama `ServiceOwnedQuotaBroker.start_verified_session()` e `observe()`.
5. IPC infantil para exibir saldo/alerta deve ser de **somente leitura**. Qualquer API de mutação aceita apenas comandos de administrador autenticados ou eventos do serviço validados.
6. O SQLite, seu WAL/SHM, imagens de referência e diretórios ancestrais devem ter ACLs restritas e verificadas por acesso efetivo com o token Filhos. Logs e cache não devem permitir substituir scripts executáveis.
7. Instâncias concorrentes do broker requerem exclusão mútua ou leases/identificadores idempotentes persistidos. `BEGIN IMMEDIATE` serializa gravações, mas sozinho não impede dois processos diferentes de cobrar o mesmo intervalo duas vezes.

## Etapas de migração segura

1. **VM com snapshot externo testado:** criar usuários equivalentes, webcam simulada, uma conta administrativa com login convencional disponível.
2. **Observabilidade:** medir SIDs de task/processos, proprietário do pipe conectado e ACLs NTFS em `ProgramData`, `Program Files` e pasta do repositório.
3. **Instalação paralela, sem substituir o provedor:** implantar serviço isolado e banco sintético em diretório protegido. Manter a baseline antiga funcionando sem encaminhar pedidos à nova instância.
4. **Shadow mode:** comparar decisões, quotas e pausas entre o agente legado e o motor isolado, sem bloquear nem alterar cobrança real.
5. **Corte transacional:** parar escritores antigos, fazer backup verificado do SQLite (API de backup, respeitando WAL), fixar ACLs e mover ledger sob posse do serviço. Verificar leituras e escrita com tokens reais.
6. **Canário em VM:** testar troca rápida de usuário, Win+L, sessão desconectada, hibernação, reinício, horário de dormir, quota esgotada e 3 crianças.
7. **Rollback:** desativar novo agente e broker, restaurar ACLs e tarefas anteriores, reverter DB/registro conforme ponto de restauração, mantendo o login convencional. Simular rollback no snapshot antes de usar no PC familiar.

## Critérios de bloqueio

**NÃO migrar / NÃO habilitar no PC familiar** se qualquer requisito faltar:
- Compilação/testes Windows e Ubuntu concluídos no HEAD exato;
- Identidade real do servidor/clientes Named Pipe e ACLs medidas em VM;
- Worker de quota privilegiado com autenticação/autorizações e armazenamento protegido;
- Prevenção de replay/idempotência contra reinicializações e processos duplicados;
- Regressão física do Winlogon e método de recuperação verificados com o responsável;
- Liveness/anti-spoof explicitamente testado se for requisito de segurança.

A branch e o PR #4 permanecem independentes da `main` e não devem ser mesclados automaticamente.
