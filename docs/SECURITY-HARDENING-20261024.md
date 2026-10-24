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
