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


## Próximo ciclo — política de conta SCM e ensaio de migração

**Nova exigência para qualquer execução posterior do serviço na VM:**
`HKLM\\SOFTWARE\\FaceControlKidsPC\\QuotaBrokerLabService\\ServiceSid`,
do tipo `REG_SZ`, deve conter o SID da **conta real do processo do serviço**.
O broker consulta seu próprio token com Win32/pywin32 e recusa iniciar se
o SID for diferente, inexistente ou malformado. A configuração existente
também exige os tipos exatos `REG_DWORD` (`LabOnly`, `ChildId`) e
`REG_SZ` (`Database`, `ClientSid`, `PipeSuffix`).

`tests/test_quota_broker_scm_lifecycle.py` exercita
`SvcDoRun`/`SvcStop` com mocks no Windows **sem instalação SCM real**.
O CI executa esses testes depois de instalar pywin32 somente no runner.

`facekids/quota_broker_cutover_lab.py` agora ensaia um *cutover* offline
de SQLite **somente** na pasta literal `facekids-quota-lab`:
1. exige um banco SQLite de teste fechado, sem arquivos `-wal`/`-shm`;
2. cria backup consistente usando a API oficial SQLite;
3. faz uma substituição temporária por cópia verificada;
4. reverte para os **bytes originais**, mesmo após falha simulada;
5. recusa caminhos sob `ProgramData\\FaceKids`, caminhos externos e
   raízes do laboratório que sejam links simbólicos.

Este ensaio **não é migração segura do banco doméstico**: não lida com
writers concorrentes, WTS, a instalação COM, Winlogon ou permissões de
acesso efetivo da conta Filhos. Nenhum desses componentes foi modificado.

**Critério de saída:** os quatro jobs Windows/Ubuntu/C++ do commit exato
da última implementação devem passar antes de dar o código por validado.


## Evidência adicional — SCM real e identidade infantil em runner descartável

**Integração real em Windows hospedado pelo GitHub (CI efêmero):**
`scripts/ci_scm_lab_smoke.py` só aceita `GITHUB_ACTIONS=true`,
`RUNNER_ENVIRONMENT=github-hosted`, `RUNNER_OS=Windows` e
`GITHUB_REPOSITORY=marquimRcc/FaceControlKidsPC`, além de privilégios
administrativos. Fora disso, **recusa executar**.

O ensaio instala temporariamente o `FaceKidsQuotaLabOnly` no SCM,
inicia como `SYSTEM`, abre um banco SQLite **fictício**, verifica a
leitura de quotas por Named Pipe, encerra e remove o serviço. A política
HKLM e o diretório do banco de ensaio são removidos no `finally`.
Não instala nem modifica o Credential Provider familiar.

O ensaio agora também cria uma conta Windows local infantil **fictícia**
(temporária e apagada na limpeza), exige que o serviço recuse a consulta
da conta administrativa do runner e aceite apenas a consulta da conta
infantil mapeada por SID. O programa comprova que nem essa conta pode
gravar dados de quota através do protocolo. A nova checagem final exige
que o token infantil não possua acesso de escrita à chave HKLM que
controla o serviço.

`scripts/ci_acl_child_token_smoke.py` realiza outro ensaio independente:
o token infantil real **consegue ler** DLL/ledger fictícios protegidos,
**não consegue escrevê-los** e pode **gravar somente na pasta separada
de cache**. Os testes atuam apenas em `FaceKidsAclCi<uuid>` sob
ProgramData, sem acessar `ProgramData\\FaceKids`.

CI comprovado em commits prévios:
- `40148637510`: instalação/start/consulta/stop/remoção SCM reais — SUCCESS;
- `40148877387`: teste de ACL com token infantil não administrativo — SUCCESS;
- `40149075585`: serviço SCM com aceitação por SID infantil e recusa do
  SID administrativo — Windows/Ubuntu SUCCESS;
- o HEAD que adiciona negação de escrita HKLM deve ter seu status
  consultado separadamente.

**Portão de hardware ainda fechado:** os testes são em uma VM descartável
do GitHub, não no PC doméstico nem em uma VM equivalente ao Windows
doméstico com webcam e LogonUI. A associação rosto/criança, eventos WTS,
banco de produção, migração efetiva das ACLs e recuperação real
continuam pendentes.
