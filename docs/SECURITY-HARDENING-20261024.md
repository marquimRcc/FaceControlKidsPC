# FaceKids — Segurança incremental (24/10/2026)

## Escopo e origem
- Base: handoff/facekids-auto-unlock-stabilization-20261021.
- Branch exclusiva: fix/facekids-ipc-security-hardening-20261024.
- Main e branch de origem nao alteradas.
- Preservar fluxo de desbloqueio facial informado pelo proprietario como funcional; nao instalar/testar Credential Provider no PC familiar.

## Entregas deste ciclo
1. cb02de5212b3bb0cc0ffcfeecaa4affdcf691999 — FaceKidsPipeClient.h: rejeicao de lixo apos numeros de child_id/timestamp e protecao da conversao de saldo fora da faixa int.
2. b1af4e064b0fdc58e6a132a78d944b870ea9c622 — TestPipeClient.cpp: casos negativos adicionais para IDs adulterados, timestamp com sufixo e saldo excessivo.

## Verificacao
- Inspecao de conteudo remoto dos arquivos: realizada.
- Compilacao/execucao Windows: NAO verificada neste ciclo.
- GitHub Actions desta branch: NAO confirmado; aguardar jobs e corrigir falhas antes de aprovar qualquer integracao.
- Nenhum teste deste ciclo comprova liveness, camera segura ou Winlogon.

## Rodada adicional — 24/10/2026
- 60dfdda688b575e6c808f0278ea1ce1e20387dc1: ALLOW exige quota positiva e representavel; child_id em decimal canonico.
- ee8718b3e59b4c3e0a9dd624d42fee72a92af94b: casos negativos para quota nula, negativa, malformada, overflow e ID com zero inicial.
- Testes C++ foram adicionados, mas ainda nao ha evidencia verificada de compilacao/execucao desta branch.
- Nao houve alteracao no SDDL, instalador, senha, Provider COM nem registro de componentes.

## Fila e riscos remanescentes
1. Conferir GitHub Actions do HEAD, sobretudo build-real-credential-provider e TestPipeClient.exe. Corrigir qualquer falha.
2. Reforcar validacao de JSON duplicado/malformado com parser correto, em alteracoes pequenas e testadas.
3. Restringir SDDL do pipe sem interromper cliente LogonUI; testar tokens e comportamento em VM descartavel.
4. Revisar o instalador: permissao Modify em ProgramData, senha em argumentos e preservacao da instalacao funcional.
5. Verificar continuidade do processo na troca de sessao/reboot antes de alterar a inicializacao.
6. Testes fisicos de webcam, anti-spoof e desbloqueio real exigem intervencao voluntaria do proprietario. Nao instalar componente nativo no PC familiar nesta branch.


## Rodada de estabilizacao — 24/10/2026 (continuidade)

- `40936539064fd4c3f3d48e6de739f8e8c0409ba1`: evita falso positivo de testes negativos por falta de quota; adiciona caso positivo com quota realista.
- `e55ce6dff76c0e35a6dcc7b062331cf6948858ea` e `bc454f2943f89532c99c56dc5c9109d035f30ed6`: o servico facial nao inclui senha na resposta; assertiva Python de privacidade. O Credential Provider segue com sua logica de credenciais, sem alteracao funcional.
- `0027cbf370347552014f056d5c167460b64da315`: validador isolado de sintaxe JSON, chaves duplicadas, profundidade e limite 2047 bytes.
- `9a2ab01df4224e9f25ce40eb535555c00ad1513d`: resposta negada quando envelope nao for JSON valido e nao ambiguo.
- `e732f8261398324cc2606031d8f6e04eed26e669`: regressao contra duplicatas, lixo, truncamento e caso valido aninhado.
- `2138276509ab354e48870db997cd225a06e80241`: impede confusao entre campo textual e numerico nos campos de autorizacao do envelope.
- `73c765402f007a80bef3ed218891cf6320023b7f`: casos negativos de tipos incorretos no parser C++.

### Evidencia efetivamente executada
- Validador C++ puro, em harness isolado Linux `g++ -std=c++17 -Wall -Wextra -Werror -pedantic`: **3 casos validos e 14 casos invalidos aprovados**. Esse teste executou apenas o validador independente, NAO compilou/rodou a DLL Windows e NAO executou o TestPipeClient completo.
- Codigo/testes Python e C++ publicados na branch. Nao houve execucao local da suite completa nem de webcam real.
- Consulta GitHub Actions para o commit `73c7654`: a integracao retorna lista vazia de workflows (a consulta desse conector e limitada a runs de pull request) e nenhum status combinado. **CI Windows/Python nao confirmado**; nao tratar lista vazia como sucesso ou como evidencia de ausencia de workflows.
- O codigo nao alterou `main`, instaladores, tarefas, registro COM ou dispositivos.

### Pendencias imediatas
1. Inspecionar o workflow `Credential Provider compile and host checks` e o `Unit tests` por commit/branch no GitHub; executar e corrigir ate ficarem verdes.
2. Validar o fluxo autorizado e o fluxo de negacao do IPC no Windows virtualizado antes de integrar qualquer mudanca na instalacao funcional do PC familiar.
3. Auditoria e ensaios em VM para ACL do Named Pipe e NTFS ProgramData: nao endurecer cegamente antes de medir a identidade do cliente LogonUI e os acessos necessarios do agente.
4. Liveness, camera no Secure Desktop e resistencia anti-spoof nao sao comprovadas por estes testes sinteticos.


## Ciclo de continuação imediato — 24/10/2026

- `1ac3a414d4cdfbf86024ac61bb0efdde75497b3f`: valida chaves JSON simples e registra as posições exatas de campos de primeiro nível; nomes escapados deixam de poder representar aliases de autorização.
- `a82ac94d3153cd91a092e3994f8234fddb344910`: elimina busca por substring no parser C++ para valores de autorização, usando apenas os campos estruturais retornados pelo guard.
- `e270da3bc327202be88185838d831976c09a6848`: cria testes isolados portáteis para JSON válido, duplicatas, alias Unicode e campos aninhados.
- `b09cacb02a4f608a6093fcb887cddc6782c7c82e`: adiciona ao `tests.yml` a compilação e execução dos testes portáteis em Ubuntu.
- `4b792701e9119fe9579eadf9e02cb58c653ba744`: amplia testes nativos do pipe contra campos falsos em mensagens e valores aninhados.
- `0b6477c99ab7aed5036452899b0c7da6af40a00e`: adiciona diagnóstico PowerShell SOMENTE LEITURA de permissões ACL de arquivos e diretórios sensíveis.
- `faee6b139702c1727c687cdec82f1e90c1a8c514`: inclui parser e smoke test da auditoria de ACLs no runner Windows, sem instalação.

### Evidências desta rodada

- Execução local `g++ -std=c++17 -Wall -Wextra -Werror -pedantic` de harness isolado contra o guard C++ atual: **13/13 casos aprovados** (sem Windows, sem webcam).
- No PR em rascunho #4 para a branch handoff (NAO main), `Unit tests` run **40141186830**: Windows e Ubuntu concluídos com sucesso; `Credential Provider compile and host checks` run **40141186686**: ambos os jobs concluídos com sucesso. **Estes runs verificaram o HEAD anterior `b09cacb`**, nao garantem os commits seguintes.
- Verificação dos commits posteriores, sobretudo parser TestPipeClient e PowerShell ACL: **pendente** ate confirmar execuções atualizadas. Não afirmar CI verde para `faee6b1` antecipadamente.
- Arquitetura de login do PC doméstico preservada: nao foram executados instaladores, registro COM, Winlogon, alteração de permissões ou acesso a fotos.
- Handoff e main não foram modificadas; somente esta branch foi escrita. O PR está em rascunho e não foi mesclado.

### Próxima fila segura

1. Conferir jobs CI do HEAD atual; consertar qualquer falha no script de ACL ou nos testes C++.
2. Auditar permissões reais apenas por inspeção voluntária ou VM, sem aplicar icacls automaticamente.
3. Considerar autenticação de identidade do servidor Named Pipe e endurecimento das ACLs somente depois de validar Win+L e a conta Filhos numa VM/snapshot.
4. Corrigir bugs demonstrados nos limites de sessão/quota sem interferir nas credenciais reais da família.


## Ciclo de implementacao e CI — 24/10/2026 (quatro jobs confirmados)

### Sessao / quota
- `2d8d8856`, `007318e1`, `43150abf`: validacao de evento local
  `last_unlock.json` com tempo finito, data de hoje, limite de idade,
  rejeicao de futuro e ID de crianca invalido; recusa de perfil inexistente.
- `b235a6c5`, `398b9762`: quota SQLite ignora nao: **rejeita**
  tempo negativo, NaN, Inf, tipos invalidos e datas invalidas ANTES do write.
- `0a23cb8f`, `ecf48ba4`, `72994764`: ALLOW do pipe in-session
  exige usuario Filhos, protocolo, timestamp e saldo; reavalia
  quota/curfew; DENY nao bloqueia sem respaldo no banco.
  **O marcador de protocolo e publico e nao autentica o servidor.**

### Instalador, recuperacao e auditorias
- `730fd727`, `6f187b87`: agente Filhos agendado com token
  interativo, sem passar senha por `schtasks /rp`; contrato com testes.
  **Funcionamento da nova tarefa no PC domestico depende de VM/aceite.**
- `84bab31d`, `16538663`: `-PreflightOnly` do instalador retorna
  relatorio e sai ANTES de qualquer copia, registro ou tarefa.
- `4ba2333d`, `813692e6`: ACL read-only inclui SQLite, WAL/SHM,
  fotos, DLL, scripts, logs e SID independente do idioma; erro de
  sintaxe detectado em CI e corrigido.
- `1fde299a`, `49ba36ac`: `-AuditOnly` do desinstalador informa
  presencia de DLL, COM, tarefas e DB sem modificar nada.
- `06ce789b`, `8fcc3c8e`: auditoria passiva da tarefa e PID/sessao
  do auth-service; **nao prova identidade de servidor Named Pipe**.
- `c30b4140`, `9f82ccd5`, `f314954d`: CI Windows cobre os
  tres diagnosticos somente leitura, corrigindo a suposicao de que
  ProgramData/FaceKids estaria ausente no runner (testes Python criam logs).

### CI verificado
No commit de codigo `f314954d41b6064031f1870d70f449d972c5b57d`:
- **Unit tests** run `40142616581` — Windows e Ubuntu: SUCCESS.
- **Credential Provider compile and host checks** run `40142616599` —
  build-real-credential-provider e compile-and-host: SUCCESS.
- Os novos documentos e este checkpoint tem commits posteriores:
  verificar o CI do HEAD final separadamente, nao extrapolar status.

### Aceite bloqueado (nao apresentar como pronto)
- `docs/ACEITE-SEGURANCA-WINDOWS.md` e roteiro, nao teste fisico.
- Nao houve instalacao/registro do CP nem desinstalacao no PC familiar.
- ACL legada `Filhos:(OI)(CI)(M)` para ProgramData nao foi removida
  cegamente; requer migracao de codigo privilegiado e SQLite gravavel.
- Identidade efetiva e token do servidor pipe na visao do CP precisam
  de implementacao/validacao em VM antes de alterar o fluxo de login.
- Rollback de CP e logon sem admin, webcam real, spoofing/liveness e
  Win+L na versao nova NAO foram comprovados.
- PR #4 permanece draft, destinado a handoff e NAO a main.


## Novo ciclo — identidade de servidor, comandos IPC e segregacao de diretorios (24/10/2026)

### Implementacao publicada
- `d8df0156`, `90d04dca`, `67c00d67`, `1b52148d`, `622656a7`:
  novo `FaceKidsPipePeerIdentity.h` e `TestPipePeerIdentity.cpp` usam
  `GetNamedPipeServerProcessId`, token de processo e SID em pipe **sintetico**
  do runner. O helper e **apenas diagnostico** e NAO e invocado pelo
  `FaceKidsPipeClient::RequestAuthentication` em producao. Um SID igual
  tambem nao comprova a integridade do executavel do servidor.
- `08027907`, `636390e0`, `4f5115a8`: o agente usa decodificacao local
  JSON limitada a 2047 bytes que rejeita chaves duplicadas, NaN,
  Infinity, UTF-8 invalido e dados malformados.
- `d8f3177f`, `93b17c44`: plano de **migracao somente leitura** em
  `scripts/Planejar-Isolamento-FaceKids.ps1`, com teste Windows sintetico.
  Nenhuma ACL, tarefa, DLL, SQLite ou pasta do Windows real foi alterada.
- `dfac74a7`, `dea6a8ea`, `b12260d3`: servidor usa os bytes efetivos
  recebidos de `ReadFile`, aceita apenas comandos ASCII esperados com
  CRLF/LF opcional, nega NUL, codificacao invalida e comandos maiores
  que 512 bytes. Nao autentica a identidade do cliente.
- `1996ab1b`, `95627a81`: teste do serviço reutiliza a implementacao
  efetiva de decodificacao, sem logica fake no teste.

### Verificacoes
- Commit `b12260d32af5ef85187f710a32e453e78df9b4e0`:
  `Unit tests` run **40143404435**: Windows e Ubuntu SUCCESS;
  `Credential Provider compile and host checks` run **40143404372**:
  ambos jobs SUCCESS, incluindo verificacao de SID em pipe sintetico.
- Os ajustes de teste posteriores (`1996ab1b`, `95627a81`) exigem
  verificacao do CI do HEAD mais recente; NAO herdam automaticamente status.
- O PR #4 permanece em rascunho, baseado em handoff e sem merge.

### Bloqueios e criterio de migracao
1. `C:\ProgramData\FaceKids` permanece legado com riscos: scripts/
   DLL e banco no mesmo diretorio historicamente gravavel por Filhos.
   Mudar isso exige separacao do codigo para pasta com ACL privilegiada
   e servico/broker que grave o ledger em vez de Filhos. O novo
   planejador so lista caminhos e impedimentos.
2. Nao ativar o helper SID no Credential Provider ate que a identidade
   esperada esteja gravada de modo protegido, uma VM/snapshot demonstre
   login e o pipe nao possa ser substituido por impostor.
3. Nem JSON rigoroso nem SID do servidor solucionam a ausencia de
   anti-spoof/liveness real, a serializacao de credenciais legada no CP
   ou a integridade do banco SQLite gravado por Filhos.
4. O teste Win+L real e a recuperacao de login permanecem bloqueados
   por aceitacao supervisionada. Nao registrar o CP no PC familiar.


## Continuacao de seguranca: politica SID opt-in (24/10/2026)

- `5c89b908`, `848752e4`, `03425fa2`, `038a25ec`:
  `FaceKidsPipeClient` consulta `FaceKidsPipePeerIdentity::AuthorizeIfConfigured`
  apos abrir o Named Pipe, ANTES de transmitir `AUTH_QUERY`.
  A politica opcional e lida de `HKLM\\SOFTWARE\\FaceControlKidsPC\\CredentialProvider`:
  `EnforceAuthServiceSid` (DWORD=1) exige `AuthServiceSid` (REG_SZ).
  Valores malformados ou SID divergente falham fechados quando a politica
  estiver ativada. Sem valor de enforcement, mantem a baseline legada.
- `7de90613`: auditoria de identidade somente leitura informa se
  enforcement esta ativado e se o SID esperado esta configurado.
- Nenhum valor novo foi gravado no registro Windows do usuario, nem
  registrado Credential Provider em maquina real. Nenhum instalador foi
  executado.
- A verificacao compara o SID de usuario de um processo do pipe, nao
  prova assinatura de binario nem imune um processo comprometido
  executando sob o mesmo SID. **Nao declarar servidor autentico** so
  com comparacao de SID sem outros controles.
- A politica permanece desligada no uso domestico ate confirmar
  SID correto do auth-service na sessao interativa, conta Filhos e
  usuario administrador com testes de impostor em VM restauravel.
- O banco de quota `criancas.sqlite3` permanece gravavel pelo agente:
  arquitetura de ledger com broker privilegiado e migracao de ACLs sao
  BLOQUEIOS, nao entregas concluidas.
- Na consulta mais recente a `Unit tests` run `40143659975` tinha Ubuntu
  aprovado e Windows em progresso; `Credential Provider` run
  `40143659977` tinha compile-and-host aprovado e build-real em progresso.
  Consultar as execucoes finais antes de declarar esta rodada aprovada.


## 24/10/2026 — continuidade de identidade, eventos e limite de rede

Commits adicionais (branch somente, PR #4 permanece draft):
- `31c8723f` / `e1c7ea82`: relatorio SOMENTE LEITURA de SID do principal da tarefa e de SID do proprietario do processo de autenticacao; usa conversao explicita NTAccount para SID. Correspondencia de SID entre processos visiveis e tarefa **nao identifica necessariamente o servidor do pipe conectado**.
- `c416b4d8`: CI Windows exige campos diagnosticos SID sem afirmar que o pipe e confiavel.
- `e65ffff3`, `22cb651f`, `fe1d5e93`: o nome exibido da crianca vem do cadastro SQLite, nao do JSON `last_unlock.json`. IDs de cadastro inexistentes sao negados; arquivo continua **NAO AUTENTICADO** (um ID existente ainda pode ser falsificado se a conta Filhos tiver escrita).
- `002c70e3`, `c8e7485f`: `CreateNamedPipeW` passa a usar `PIPE_REJECT_REMOTE_CLIENTS=0x00000008` e ha teste cobrindo flags de mensagem e acesso local. Isso reduz a superficie de rede, **nao prova quem e o cliente ou o servidor local**.

### CI da ultima alteracao funcional/teste
- Commit `c8e7485f2c1bf2ce7e3cafc69378c68de2feed5e`:
  - Unit tests Windows/Ubuntu: `https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40143973936` — 2 jobs SUCCESS.
  - Credential Provider compile and host checks: `https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40143973929` — 2 jobs SUCCESS.
- O checkpoint em si cria novo commit, portanto o status do HEAD novo deve ser consultado separadamente.
- Nao houve instalacao, alteracao de ACLs ou teste fisico no computador familiar.

### Portoes ainda bloqueados
1. Cliente CP verificar o SID/token do **servidor conectado** via `GetNamedPipeServerProcessId` com SID esperado protegido por administrador; validar em VM antes de ativar, para nao bloquear LogonUI.
2. Separar codigo/DLL/script de arquivos que Filhos pode editar; implementar broker privilegiado para gravação de quota antes de restringir acesso ao SQLite.
3. Deixar de considerar `last_unlock.json` fonte autorizativa de ID sem corroboracao independente do pipe/servico confiavel.
4. Testes em VM/snapshot de reboot, Win+L, troca de usuario, rollback e ausencia de camera.
5. Liveness anti-foto/anti-video e confiabilidade do reconhecimento: so hardware fisico supervisionado.


## 24/10/2026 — reforco de nomes e prototipo de relogio do broker

- `1f3fdc18`: a identificacao `ALLOW` no agente tambem resolve o nome exibido
  da crianca pelo SQLite, nao pela resposta do pipe. Isso nao prova a
  autenticidade do servidor do pipe nem impede um ID de perfil valido falsificado.
- `3c3be6ef` e `64705cc4`: modulo **isolado e nao integrado**
  `facekids/quota_broker_clock.py`, com contrato de tempo monotônico medido
  pelo servidor, vinculado ao ID de crianca e sessao WTS, e testes negativos de
  clock NaN/Inf, saltos de tempo, troca de sessao e independencia de perfis.
  O argumento `observed_wts_active` DEVE vir de WTS consultado por processo
  privilegiado, nunca de payloads enviados pela conta Filhos. Ainda nao ha
  transporte seguro, validacao SID do cliente nem gravacao de quota por broker.

### Seguranca efetiva ainda pendente
- O agente atual continua escrevendo no banco SQLite compartilhado.
- `last_unlock.json` ainda pode selecionar ID de perfil existente se
  adulterado; novos controles apenas tornam nome e formatos consistentes.
- A identidade do servidor ligado ao pipe ainda nao e imposta no CP real.
- Nao instalar esta branch no PC familiar ate VM/snapshot e aceite fisico.


## 24/10/2026 — broker transacional e idempotencia (prototipo)

- `98c7a3ad`: novo `ServiceOwnedQuotaBroker` (somente Python isolado),
  baseado em `ServerObservedQuotaClock` e estado WTS que deve ser obtido
  independentemente por um futuro servico confiavel. Nao possui listener IPC.
- `3a269a41`: testes de duas criancas, Win+L/pausa, troca de sessao,
  monotonicidade, quota esgotada e curfew, sem acionar o Windows.
- `da347c7f`, `d5237d1b`, `4fae4014`: `Storage.charge_up_to_available`
  usa `BEGIN IMMEDIATE` para limitar debito ao saldo disponivel;
  o motor de prototipo usa essa operacao. Testes verificam duas conexoes
  SQLite cooperativas e invalidacao de dados.
- `f589eded`, `9bb588fe`: `charge_capped_once` registra recibo duravel
  por ID de evento emitido pelo futuro servico, na MESMA transacao do
  debito. Reenvios identicos debitam zero, reutilizacao do ID com outros
  dados e rejeitada. Essa API nao esta ligada ao agente existente.
- Plano: `docs/QUOTA-BROKER-ISOLATION-PLAN.md` descreve requisitos de
  WTS, binarios protegidos, ACLs do ledger, idempotencia, backup SQLite/WAL,
  rollout sombra, snapshot em VM e rollback. Nao modifica instalacao.

### Resultados e limites de confianca

- `Unit tests` no commit `4fae4014`:
  `https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40144458857`
  — Windows e Ubuntu SUCCESS.
- Para a API de recibos de replay (`9bb588fe`), consultar o novo CI antes
  de considerar a implementacao validada.
- **Nao existe servico Windows privilegiado ativo nesta branch.** O
  `filhos_agent.py` ainda debita o banco legado gravavel pela conta Filhos.
  O broker novo NAO e uma fronteira de seguranca enquanto WTS/identidade
  confiaveis, autorizacao de IPC, exclusao mutua de servico e ACLs nao
  estiverem implementados e testados em VM.
- Recibos em SQLite impedem replay com o mesmo ID, mas dois processos
  maliciosos que inventem IDs novos ainda podem tentar debitos. Nao
  confiar em IDs fornecidos pelo agente Filhos.
- Nenhuma operacao de instalacao/registro COM, migracao de SQLite,
  icacls, Win+L ou webcam foi executada no computador familiar.
- PR #4 permanece draft e nao mesclado.


## Ciclo — broker Windows de laboratorio e diagnostico shadow (24/10/2026)

**Etapas solicitadas 1 a 7 e 11: progresso executado sem modificar Windows domestico**

| Etapa | Codigo / status |
| --- | --- |
| 1. Windows Service | Host Windows experimental de UMA requisicao criado, mas NAO registrado no SCM nem instalado; servico privilegiado permanente fica bloqueado ate VM |
| 2. IPC | Contrato `FACEKIDS_QUOTA_V1` estritamente read-only; host de pipe local com SDDL explicita, sem clientes remotos e primeira instancia protegida |
| 3. Tokens/SID | Servidor de lab extrai SID por `ImpersonateNamedPipeClient` e compara com mapeamento de teste; negacao de SID estranho coberta em CI Windows |
| 4. SQLite | `ReadOnlyQuotaView` em `mode=ro`; snapshot WAL-consistente, preserva bonus e perfis, so permite arquivos NOVOS no laboratorio |
| 5. ACLs | Planejador e auditoria read-only ja existentes; migracao NTFS efetiva AINDA NAO executada; falta service-owned ledger/VM |
| 6. FilhosAgent | Opt-in `FACEKIDS_QUOTA_BROKER_SHADOW=1` e `FACEKIDS_QUOTA_LAB_SUFFIX` (apenas telemetry); debito/lock seguem legacy |
| 7. Recuperacao | Restauracao de snapshot sintetico e verificacao de saldos anteriores; rollback COM/tarefas/Winlogon AINDA NAO validado |
| 11. CI | Python Windows/Ubuntu, pipe Windows sintetico, build nativo CP/host e C++ completo executados sem alterar login |

### Commits de implementacao

- `e080eec8`, `ee5324e8`: protocolo read-only e testes anti-cliente malicioso.
- `e9588868`, `2f939643`, `c734e845`: backup SQLite WAL-consistente e ensaio de restauracao em arquivo novo.
- `d76cf88c`, `11038518`, `aba9238f`: host Windows de pipe de laboratorio com token SID e abertura read-only do ledger.
- `14ddf52d`, `fd8ef240`: leitura sem escrita e roundtrip real de pipe sintetico sob Windows.
- `8e7065d0`, `5707a162`: fechamentos explicitos SQLite no Windows; corrigidos dois erros de cleanup CI.
- `4fe450b3`, `8cdc66a4`: cliente lab read-only reutilizavel e exercitado no runner Windows.
- `f481f926`, `f2fd2048`: CLI de uma requisicao com gate `--vm-lab-only` e testes de caminho/SID.
- `14f73189`, `9969fe2b`, `d42aaa4c`: shadow diagnostics no agente com comparacao de saldo, sem autoridade sobre logon, tempo ou bloqueio.

### Evidencia GitHub Actions

Para o ultimo commit funcional `d42aaa4cb61a802c7593a7618321303cd7b0403e`:
- **Unit tests** `40146304213`: Windows SUCCESS e Ubuntu SUCCESS.
- **Credential Provider compile and host checks** `40146304210`: build real SUCCESS e compile-and-host SUCCESS.
- Os commits posteriores alteram somente a documentacao; verificar HEAD exato antes de qualquer revisao/merge.

### Limites honestos / nao instalar no PC

- Host `quota_broker_transport_win` so atende laboratorio: 1 pedido, IO sincronico, nao ha SCM, WTS privilegiado, servico ativo ou isolamento real da familia.
- O cliente lab nao verifica SID do servidor, logo NUNCA deve autorizar bloqueio, quota nem logon. O modo shadow e somente logs.
- SQLite legado ainda pode ser modificado pela conta Filhos; o agente ainda o escreve diretamente. A protecao de dados executaveis/ACLs precisa ser ensaiada em VM restauravel.
- Scripts de instalacao existentes NAO foram executados nesta rodada. Sem mudanca em tarefa agendada, regsvr32, registro, ACL, cameras ou fotos.
- Passagem para servico real requer testes de impersonacao e autenticidade do servidor em VM, timeouts/cancelamento robustos, serializacao exclusiva do ledger, backup/restauracao de COM e Winlogon, anti-spoof e validacao Win+L supervisionada.
- PR #4 segue **draft**, com base handoff e sem merge em main.


## Ciclo seguinte — Windows SCM supervisao + ACL rollback em fixture (24/10/2026)

- `c089da65`: servidor Named Pipe de laboratorio adota `FILE_FLAG_OVERLAPPED`,
  deadline total, `CancelIoEx` e espera para liberar `OVERLAPPED` com
  seguranca em timeout/parada, mantendo primeira instancia e clientes locais.
- `96f88853`, `09027edd`: supervisor com signal stop, tentativas limitadas,
  reinicio apos falha transitória e encerramento fail-closed apos erro repetido.
- `6aea77d8`: testes Windows de encerramento sem cliente conectado e deadline.
- `550d4f06`, `aa64924f`, `e997677b`: classe de serviço opcional baseada
  em pywin32 e configuracao estrita de HKLM `LabOnly=1`, sem comandos para
  instalar no SCM nem acesso ao banco familiar. Dependencia opcional
  isolada de `requirements.txt`.
- `fe5924fa`, `5f37c1e0`, `4211d308`, `4a7bd539`: script e teste
  Windows de ACL e rollback SOMENTE para arquivo temporario sintetico,
  com restauracao semantica de owner/heranca/ACE. O primeiro teste encontrou
  diferenca de SDDL textual; a restauracao foi corrigida e o Windows CI passou.
- `d986a70d`: CI Windows instala pywin32 apenas no runner descartavel e
  valida que o wrapper SCM herda `ServiceFramework`, SEM registro.
- `docs/BROKER-SCM-LAB-20261024.md`: roteiro, restricoes e bloqueios.

### CI verificado
- Commit de codigo/workflow `d986a70d314e251726565daeef1d990b50476eb3`:
  - Unit tests `https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40147534359`
    — Windows SUCCESS e Ubuntu SUCCESS.
  - Credential Provider `https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40147534306`
    — compilacao real SUCCESS e suite diagnostica SUCCESS.
- Commits de documentacao posteriores geram novas execucoes; consultar
  HEAD exato se necessario.

### Ainda bloqueado para hardware domestico
- Nenhum SCM instalado/iniciado de fato, nenhuma configuracao HKLM aplicada.
- Ensaio de ACL foi em arquivo TEMPORARIO do runner; acesso efetivo com token
  Filhos, migracao de SQLite da familia e rollback de COM ainda nao testados.
- Nao existe worker confiavel que debite tempo com eventos Windows WTS reais.
  Shadow responde apenas a diagnosticos, nao muda cobranca ou bloqueio.
- Nao tocar `main`, logon do PC, camera, fotos, tarefas nem provedor instalado.


## 24/10/2026 — progresso no SCM e rollback offline, sem intervenção doméstica

Commits funcionais desta rodada:
- `05e2911a`, `5c64c6f6`: testes do ciclo de vida
  `SvcDoRun/SvcStop` com pywin32 no runner Windows, **sem registrar SCM**;
  verificam parada antes da inicialização, carregamento da política
  e recusa de iniciar quando o registro é inválido.
- `8312f9bc`, `4522923c`: tipos exatos de valores da política HKLM
  para laboratório, sem acesso ou alteração a configuração real.
- `41e0b620`, `6ca5fbc3`, `de5b9cbe`: SID obrigatório da conta do
  **próprio processo SCM** antes da abertura do pipe ou do banco de teste;
  mismatch faz a inicialização falhar fechada.
- `2b430e37`, `780a65fe`, `b3e399cd`: cutover transacional de
  ensaio em SQLite sintetico com backup, substituição temporária e
  restauração exata dos bytes originais; testes de falha simulada,
  origem fora do laboratório, WAL ainda aberto e raiz symlink.
- `docs/BROKER-SCM-LAB-20261024.md`: detalhes e limites.

Evidência de CI:
- commit `de5b9cbe40dfca5af43c652452f9affcddc5d463` —
  Unit tests run `40148204656` Windows/Ubuntu SUCCESS;
  Credential Provider run `40148204585` dois jobs SUCCESS.
- CI do cutover offline e documentação mais recente ainda deve ser
  consultado separadamente; resultados anteriores não provam esse HEAD.

Status não resolvido:
- SCM NÃO registrado/iniciado em uma VM restaurável; testes SCM atuais
  são de classe/contrato com mocks e temporários.
- Isolamento NTFS com token infantil efetivo e serviço de quota com
  eventos WTS reais NÃO implementados.
- Nenhum backup nem migração dos dados infantis reais realizado.
- Não houve ação sobre `main`, credenciais, fotos, tarefas,
  LogonUI, registro COM, webcam ou PC da família.
- PR #4 segue draft até que uma VM e testes Win+L supervisionados
  comprovem recuperação e operação.
