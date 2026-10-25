# FaceKids — próximo estágio: serviço SCM e isolamento em laboratório

**Estado:** código preparado para um serviço Windows de laboratório com supervisão;
não existe instalação ou registro de serviço nesta entrega. O controle parental
existente no PC da família continua independente.

## Componentes entregues

- `facekids/quota_broker_transport_win.py`: comunicação Named Pipe
  exclusiva de laboratório com `FILE_FLAG_FIRST_PIPE_INSTANCE`,
  `PIPE_REJECT_REMOTE_CLIENTS`, ACL explícita, impersonação e SID
  do **cliente**. Conexão, leitura e escrita usam I/O *overlapped* com
  prazo máximo, cancelamento por sinal de parada e finalização do
  `OVERLAPPED` antes de liberar memória/evento/handle.
- `facekids/quota_broker_supervisor.py`: executa ciclos de requisições
  read-only, permite parada, aceita timeout ocioso e encerra após falhas
  consecutivas. Não contém autorização de alteração de quotas.
- `facekids/quota_broker_scm_win.py`: classe opcional
  `FaceKidsQuotaLabService` compatível com `pywin32 ServiceFramework`,
  com callbacks `SvcDoRun` e `SvcStop`. **Não instala** no SCM e
  não oferece comando automático de registro.
- `requirements-windows-service-lab.txt`: dependência pywin32 para VM,
  separada dos requisitos da instalação familiar.
- `scripts/Testar-ACL-Rollback-Broker-Lab.ps1`: cria um arquivo
  temporário *sintético*, aplica ACEs de leitura para BUILTIN Users,
  restaura o descritor de segurança original, verifica hash e exclui
  os dados do ensaio. Não recebe caminhos de produção, não modifica
  tarefas, registro, logon ou banco real.
- Testes novos: supervisão, cancelamento do pipe com/sem cliente,
  configuração SCM com `LabOnly=1`, rejeição de caminhos
  `ProgramData\FaceKids`, e simulação de ACL/rollback no Windows CI.

## Proteção de configuração

Um administrador, **somente em VM descartável e após confirmar backup/
recuperação**, deverá estabelecer configuração em HKLM sob:

`SOFTWARE\FaceControlKidsPC\QuotaBrokerLabService`

Campos obrigatórios (nenhum valor padrão permissivo):

| Valor | Tipo / requisito |
| --- | --- |
| LabOnly | DWORD = 1, obrigatório |
| Database | Caminho existente em `facekids-quota-lab`, nunca sob o ProgramData familiar |
| ClientSid | SID conhecido e confiável da conta de teste |
| ChildId | ID positivo do cadastro de teste |
| PipeSuffix | 32 caracteres hexadecimais minúsculos |

O SCM deve rodar com principal aprovado e executáveis instalados em
diretório protegido, depois de verificar ACL de cada diretório ancestral.
Esta branch NÃO configura isso e NÃO registra a classe no SCM.

## Testes e limitações

- Windows CI cobre pipe real e sintético, parada e timeout, SID certo/
  errado, e classe SCM carregável com pywin32 opcional (quando o job
  correspondente passar).
- Linux/Windows testam a política portátil de supervisão e portas
  fechadas antes de a configuração ser validada.
- Ensaio de ACL em arquivo temporário **não é** teste de acesso efetivo
  da conta Filhos e não é rollback de DLL/COM/Winlogon.
- `facekids/quota_broker_read_store.py` usa SQLite em modo read-only.
  O banco em produção ainda é gravável pelo agente Filhos e o broker
  de laboratório NÃO possui processo que debite quotas.
- A sessão real de cada criança NÃO pode ser derivada apenas do SID:
  as três crianças compartilham a conta Filhos. A identidade infantil
  ainda precisa vir de reconhecimento autenticado e vinculado ao WTS.
- Um processo que consiga falsificar o servidor do pipe de laboratório
  pode forjar respostas ao cliente shadow; essas respostas **nunca**
  podem alterar logon, quota ou bloqueio.
- Para migração real ainda faltam integração do worker privilegiado,
  idempotência persistente por instância, eventos WTS validados, monitor
  de saúde, binários protegidos, rollout/rollback transacional e testes
  físicos de Win+L/LogonUI.

## Próximo portão

Executar laboratório em **VM restaurável**, inclusive início/parada
real no SCM e teste de permissões com token Filhos de teste. Somente
depois preparar migração controlada de binários e SQLite.

PR #4 permanece draft sobre handoff; main, CP registrado, senhas,
fotos, webcam e máquina familiar não foram alterados.
