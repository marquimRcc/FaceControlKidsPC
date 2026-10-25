# FaceControlKidsPC — Checkpoint de desenvolvimento autonomo

> Documento de retomada da branch `feature/windows-native-unlock-poc`.
> Atualizar apos cada ciclo. Nao confundir testes sinteticos com login facial real.
> A `main` nao deve ser alterada nem mesclada sem ordem explicita.

## Ciclo P0-1 a P0-5 — hardening da branch de segurança (25/10/2026)

**Branch:** `fix/facekids-ipc-security-hardening-20261024` — [PR #4](https://github.com/marquimRcc/FaceControlKidsPC/pull/4) em draft;
`main` intocada. A implementação anterior de P0-1 a P0-5 de VM
foi conferida no HEAD `3f17b02c`, com workflows Windows/Ubuntu
e Credential Provider aprovados antes desta rodada.

- **P0-1:** contrato `FACEKIDS_BOUND_QUOTA_V1` agora rejeita strings SID
  malformadas antes de chamar o leitor do saldo associado à lease facial
  do serviço SCM. Identificação do cliente continua sendo do token Windows,
  nunca dos campos JSON.
- **P0-2:** o observador read-only infantil devolve `unavailable` para
  `TypeError` do cliente, sem expor cobrança, troca de rosto, bloqueio
  ou acesso direto a SQLite. Não houve ativação do modo na instalação familiar.
- **P0-3:** teste simultâneo de quatro conexões SQLite reais no mesmo
  recibo de 32 dígitos: um débito e três replays sem cobrança. Reinício
  simulado mantém a deduplicação e recusa o escritor legado após a promoção.
- **P0-4:** a promoção compara schema e conteúdo de TODAS as tabelas
  SQLite, incluindo valores, configurações, embeddings e recibos, após
  o backup WAL-aware e dentro de `BEGIN IMMEDIATE`. Antes, contava
  apenas quatro tabelas e perdia `UPDATE` sem alteração na contagem.
  Rollback requer owner `vm-service-only` e rejeita symlink no caminho
  solicitado e estágio de restauração pendente sem criar novo undo.
- **P0-5:** teste negativo de desconexão WTS, tempo avançado e
  reinicialização do host: sem lease facial antiga, débito zero até um
  novo evento de desbloqueio do SCM e nova identificação simulada.

**Correções rastreáveis:**
- [b17d3520](https://github.com/marquimRcc/FaceControlKidsPC/commit/b17d3520023d404f6cab4074cfbb85ea496380a5) e [40d5931e](https://github.com/marquimRcc/FaceControlKidsPC/commit/40d5931e0b113f04e587c2f4292fc29e66cde53e): comparação integral e gates de rollback;
- [45d5b107](https://github.com/marquimRcc/FaceControlKidsPC/commit/45d5b1075ac46242872e5e2cd73ff59c10505f43) e [ee03ed63](https://github.com/marquimRcc/FaceControlKidsPC/commit/ee03ed63aeeed49fc7fdb815cabc3202dd9562e6): testes negativos e correção do teste de corrida;
- [320029cc](https://github.com/marquimRcc/FaceControlKidsPC/commit/320029cc19f994f1add7231f12284e1fc9bf7011), [a3659902](https://github.com/marquimRcc/FaceControlKidsPC/commit/a3659902150bd21fc2018a0ea387307aea59c44d): validações de IPC/agente;
- [392c50b2](https://github.com/marquimRcc/FaceControlKidsPC/commit/392c50b2d801d8327d2944a1ae9f7e22af28b13e) e [300db35b](https://github.com/marquimRcc/FaceControlKidsPC/commit/300db35b6a49cab7a6e09dce5d15906f3a310b28): concorrência e reinício.

**Evidências:** 6 testes isolados do comparador SQLite passaram localmente;
o GitHub Actions do `300db35b` passou nos 2 jobs Windows/Ubuntu
([Unit tests](https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40208065120))
e nos 2 jobs C++/Credential Provider
([Native](https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40208065101)).
O workflow Windows inclui smoke de SCM SYSTEM, ACL e cutover sintético.
Um teste novo inicialmente falhou: o mutador de teste fechava uma conexão
sem commit; corrigido em `ee03ed63`; só os resultados do HEAD final
são usados como aceite automatizado.

**Não homologado:** webcam e liveness reais, SYSTEM/Sessão 0/Winlogon,
snapshot externo e recuperação administrativa em VM interativa, instalação
familiar, migração do banco produtivo, bloqueio por IPC e compatibilidade
com alterações recentes da `main`. O PR permanece draft, sem merge.
Não instalar no computador da família.

---

## Fases 1 e 2 — progresso pós-P0-42 (20/10/2026)

Pedido: concluir a Fase 1 e, sem solicitar nova autorização,
iniciar automaticamente a Fase 2. NÃO declarar a Fase 1 validada
fisicamente sem webcam, liveness real e prova de LogonUI em VM.

### Fase 1: P0-43 a P0-47

- **P0-43 PARCIAL:** protected_camera_worker.h inspeciona somente
  dispositivos de video dentro do processo LocalSystem e recusa
  falso worker vindo de uma conta sem privilégios. Ainda nao
  captura frames confiaveis na sessao LogonUI.
- **P0-44 HARDWARE PENDENTE:** scripts/Testar-Camera-WinL.ps1 existe,
  mas a camera do computador familiar precisa de ensaio Win+L real.
- **P0-45 SOFTWARE IMPLEMENTADO:** face_matcher.h lê embeddings
  protegidos do SQLite e faz comparação 1:N com limites internos;
  rostos desconhecidos não podem gerar autorização de login.
- **P0-46 SOFTWARE IMPLEMENTADO:** face_consensus.h exige três
  confirmações do mesmo candidato em 3s, com uma só face e mesma sessão.
- **P0-47 DIAGNÓSTICO, NÃO LIVENESS:** liveness_challenge.py exercita
  pedido aleatório de movimento lateral e retorno, rejeitando
  imagem estática. Não resiste comprovadamente a foto móvel,
  vídeo, replay ou deepfake. Testes Python run 39464342930 OK.

### Fase 2: P0-48 a P0-51, iniciada em paralelo ao aceite físico

- **P0-48 SOFTWARE IMPLEMENTADO:** face_quota_bridge.h junta
  candidato protegido + WTS/SID da sessão + quota. A resposta
  positiva significa apenas NEEDS_TRUSTED_CAMERA_AND_LIVENESS;
  não fornece ticket ou desbloqueio.
- **P0-49 SOFTWARE IMPLEMENTADO, TESTE SINTÉTICO:** one_use_preflight.h
  encadeia o candidato protegido à pré-verificação única de sessão;
  ticket interno expira em 8s, revalida SID/WTS/quota e rejeita replay.
  O construtor de simulação é privado aos autotestes; uso normal
  sempre nega. facial_policy.h permanece como guarda independente.
  Nenhum ticket de login, senha ou credencial do Windows é emitido.
- **P0-50 SIMULADO:** usage_meter.h contabiliza tempo monotônico
  e quotas no banco; ativo apenas nos autotestes.
- **P0-51 DRY-RUN:** lock_decision.h verifica sessão alvo, SID e
  esgotamento de quota, mas em runtime sempre recusa bloquear.
  Construtor que habilita simulação é privado aos autotestes;
  não existe chamada Win32 para bloquear usuários.


Obs.: Fase 1 só pode receber status FINALIZADA após validar
a câmera física, a proveniência da captura e o liveness real
contra foto/vídeo. O GitHub CI não tem o hardware alvo.

### Próxima execução

1. Confirmar resultados C++/SCM dos commits P0-43 a P0-51
   (alguns workflows entraram na fila de GitHub Actions).
2. Corrigir quaisquer falhas e trabalhar nas próximas peças
   de integração, mantendo todos os caminhos de login fechados.
3. Recolher resultado do script Win+L no PC físico voluntariamente;
   provar captura protegida, cadastro consentido e liveness
   real contra foto/video antes de dar Fase 1 como concluída.
4. Nunca instalar Credential Provider no computador real; usar VM
   com snapshot restaurável e preservar a branch main.

---

## Ciclo de armazenamento biometrico e medicao — P0-36 a P0-42 (20/10/2026)

- **P0-36:** esquema protegido no WinSQLite para ate cinco embeddings
  SFace por crianca (128 floats finitos), sem imagens. Testes sinteticos
  verificam persistencia, recusas por tamanho/conteudo e separacao de perfis.
  CI SCM 39458291387 aprovado.
- **P0-37:** teste com token Windows restrito comprova negacao de leitura
  e gravacao no banco biometricos+quotas. CI SCM 39458659678 aprovado.
- **P0-38:** API IPC binaria de exclusao de embeddings, somente para
  administrador elevado realmente autenticado pelo token Windows;
  nao altera quota nem gera credencial. CI SCM 39459008858 aprovado.
- **P0-39:** verificacao nativa exige dono SYSTEM/Administrators, DACL
  protegida, dois ACEs com acesso completo e sem outros grupos;
  teste negativo de DACL so-leitura. CI SCM 39459378448 e
  39459662068 aprovados.
- **P0-40:** script scripts/Testar-Camera-WinL.ps1 prepara ambiente Python
  e inicia diagnostico opt-in com um so comando, SEM salvar frames
  ou alterar login. Teste em hardware fisico continua PENDENTE.
- **P0-41:** exclusao de templates e respectiva auditoria anonima
  sao feitas em uma unica transacao SQLite; registro persiste ao reabrir,
  sem armazenar imagens/modelos em auditoria. CI SCM
  39460501543 aprovado.
- **P0-42:** simulador C++ de consumo monotônico por perfil e quota,
  com bloqueio por WTS alterado, dia trocado, tempo regressivo,
  saldo esgotado e separacao de criancas. A classe normal nega
  ativacao por falta de identificacao facial confiavel; so autoteste
  injeta perfis e relogio. CI Windows broker 39460971880
  aprovado; conferir CI SCM 39460971872 para conclusao.

**NAO esta concluido:** captura real de imagem com origem verificavel
no Secure Desktop, liveness resistente a foto/video, binding facial
a crianca, credencial Windows e desbloqueio de LogonUI. O bootstrap
de webcam precisa ser executado voluntariamente no PC fisico.
Nenhum codigo deste ciclo foi instalado no PC familiar ou na main.

### Proximos trabalhos viaveis sem hardware

1. Revisar retencao/backup e acesso administrativo aos embeddings
   nativos e o fluxo transacional de auditoria.
2. Implementar a camada de binding seguro entre worker protegido
   de camera e medidor de tempo; manter runtime fechado por padrao.
3. Fortalecer teste em runner VM de recuperacao do banco SQLite;
   nao instalar o Credential Provider real ate haver snapshot testado.
4. Obter resultado do diagnostico Win+L fisico antes de assumir
   viabilidade da webcam para LogonUI.

---

## Ciclo de seguranca adicional — P0-35 (20/10/2026)

P0-35: ampliados os testes sinteticos do quota_gate nativo.
Novos casos negativos incluem:
- WTS INACTIVE e UNKNOWN
- SID de token diferente da conta Filhos
- session_id trocado entre captura e consulta
- dia de quota invalido
- nova verificacao positiva apenas apos restaurar todas as precondicoes

Codigo no commit bd127034; conferir workflows Windows broker
39456205834 e SCM 39456205889 antes de declarar ambos aprovados.
Esses testes usam snapshots simulados, nao a tela segura real.

Proxima prioridade concreta: proteger a origem da captura facial
com worker sob controle do servico Windows, sem aceitar embeddings,
'camera_healthy' ou 'liveness_passed' da conta Filhos.
Testes de foto/video e LogonUI reais seguem dependentes de hardware
e ambiente VM recuperavel.

---

## Ciclo de recuperacao e endurecimento — P0-30 a P0-34 (20/10/2026)

**P0-30 — falha fechada + recuperacao do SQLite: TESTADO.**
No runner Windows descartavel, o SCM parou o broker, teve seu banco
intencionalmente corrompido, confirmou que o servico nao inicia com
o ledger invalido, restaurou os bytes originais com SHA-256 identico,
reiniciou o servico e verificou PING. CI 39454046681 aprovado.
Esse teste **nao e um snapshot de VM** nem substitui um rollback
do LogonUI. Nao realiza autenticacao ou registro de Provider.

**P0-31 — mensagem IPC excessiva: TESTADO.**
Broker passa a testar frame de 128 bytes no pipe que aceita apenas
32; nenhuma resposta positiva e aceita, mesmo se o servidor
desconectar. CI 39454325991 aprovado.

**P0-32 — API sintetica privada: TESTADO.**
Removida a fabrica publica de politica facial artificial. Somente a
funcao interna self_test e friend do construtor de diagnostico.
Um static_assert bloqueia construcao sintetica por outros chamadores.
A politica normal nega toda evidencia artificial.
CI 39454667563 (broker) e 39454667627 (SCM) aprovados.

**P0-33 — isolamento de conta sem privilegios: TESTADO.**
Um token Windows restrito, com SID Administradores desabilitado,
tenta abrir o pipe; o ACL nega. Admin legitimo ainda recebe PONG.
Nenhuma conta Windows foi criada. CI 39455111448 aprovado.
Nao e teste direto da conta Filhos no PC real.

**P0-34 — preflight de runner virtual antes de testes SCM: APROVADO.**
Adicionado scripts/Conferir-Ambiente-Isolado.ps1, apenas leitura.
O workflow exige contexto GitHub-hosted e indicios WMI de Windows
virtualizado antes de criar um servico de teste.
O primeiro workflow falhou devido a verificacao errada de
LASTEXITCODE de um script PowerShell; corrigido. Run 39455686332:
preflight, compilacao e ciclo completo do SCM APROVADOS.
Virtualizacao detectada nao e evidencia de snapshot utilizavel.

### Proxima fila tecnica

1. Confirmar status completo de 39455686332 e corrigir se necessario.
2. Preparar politica de recuperacao e preflight para VM Windows local
   com snapshot verificado externamente, sem instalar o CP real.
3. Testar limite de quota individual e reavaliacao de WTS em eventos
   de troca/desconexao, somente com dados sinteticos.
4. Captura facial REAL com worker protegido continua BLOQUEADA por
   falta de teste de hardware, liveness e identidade do processo.
5. Manter **main intacta**; nao instalar nada no Winlogon do PC real.

---

## Ciclo seguinte — P0-26 a P0-28 (20/10/2026)

- **P0-26 — diagnostico de frames em memoria:** o broker C++ adicionou
  camera_frame_probe.h e o CLI opt-in --frame-probe, que le um unico
  frame via Media Foundation, produz somente uma metrica de uniformidade
  e descarta os pixels. NAO e liveness nem reconhecimento. Nao funciona
  como autenticador ou operacao do pipe. Compilacao/auto-teste aprovados
  no Windows; CI sem camera fisica nao prova a captura real.
  Evidencias CI: 39451223659 (broker), 39451223705 (SCM),
  39451223655 (Credential Provider).
- **P0-27 — privacidade na demonstracao:** operacao parent-only
  remove_faces apaga os embeddings do perfil selecionado e cancela
  cadastro pendente sem eliminar quota nem outros perfis. PRAGMA
  secure_delete=ON reduz residuo, sem prometer exclusao fisica de SSD.
  Evidencia CI: 39451448015 (Python Windows/Linux), aprovado.
  A base da demonstracao continua editavel pelo proprio usuario:
  NAO usa-la para autenticacao protegida.
- **P0-28 — roteiro de teste real Win+L:** criado
  facekids/hardware_camera_probe.py com contadores somente em memoria,
  consulta WTS pela sessao de processo do Windows e saida que distingue
  falta de amostras, camera sem frames e frames preliminares durante
  bloqueio. Nao salva imagens, nao altera login.
  Evidencia de CI Python: 39451750368 (validacao sintetica),
  aprovado em Windows e Linux; capturas da webcam real PENDENTES
  em equipamento fisico.

### Prioridade na proxima execucao automatica

1. Conferir conclusao do run 39451750368 (especialmente Windows),
   corrigindo se necessario.
2. Prosseguir P0-29: separar testes de liveness demonstrativos de
   prova real anti-foto/video; impedir promocao de flag nao confiavel
   em qualquer fluxo de autorizacao nativa.
3. **P0-29 concluida no codigo e em CI:** InternalFacePolicy agora
   nega por padrao qualquer evidencia com booleanos simulados, mesmo
   que origin/liveness/camera venham como positivos. Factory de testes
   permite apenas verificacoes sinteticas, nao login. Provas CI Windows:
   39452149478 (broker) e 39452149379 (SCM).
   A resistencia real a fotos/videos e a origem segura continuam PENDENTES.
4. Inspecionar falhas do SCM/IPC e revisar limites/timeout/cancelamento
   de diagnosticos, priorizando operacoes que nao bloqueiem LogonUI.
5. P0-30: VM com snapshot, teste de recuperacao da conta administrativa
   e apenas depois estudo de serializacao Windows; nunca no PC real.
6. Revisar retencao/protecao dos embeddings e nao capturar dados de
   menores no GitHub Actions.

Leia primeiro este documento, compare HEAD e suites GitHub; faca
varias mudancas testadas na mesma execucao quando possivel.

---

## Ultima entrega — 20/10/2026

Etapas tecnicas realizadas nesta rodada:

| Etapa | Mudanca concreta | Prova automatizada |
|---|---|---|
| P0-21 | Validacao de data civil e limite acumulado de bonus no WinSQLite nativo | Tests de broker e SCM Windows |
| P0-22 | Teste real de mensagem binaria invalida no named pipe retorna DENIED | Workflow Windows broker IPC |
| P0-23 | PRAGMA quick_check verificado antes de inicializar o ledger; arquivo SQLite invalido recusado | Testes de host e SCM Windows |
| P0-24 | SFace rejeita vetores NaN, infinito, zerados e dimensoes invalidas | Testes de reconhecimento Python Windows/Linux |
| P0-25 | Storage Python igualou teto de bonus por crianca/dia (480 min) | Testes de Storage Windows/Linux |

Comprovacoes GitHub Actions:
- C++/SCM apos controle de integridade: runs 39447068762 e 39447068788
- Teste de input de protocolo: run 39446548826
- Testes de novos vetores faciais: run 39447476627
- Testes Python com regras de bonus: run 39447759390

Os workflows acima podem levar alguns instantes a terminar na ocasiao
do commit. Nao afirmar que um workflow em andamento passou por completo
antes de conferir sua conclusao.

## Baseline mantida

- Broker C++ protegido, executado como LocalSystem apenas no runner de teste
- Credenciais Windows nunca sao serializadas pelo Credential Provider de diagnostico
- Login real e registro da DLL COM continuam desativados
- Quotas SQLite persistentes por 3 perfis e WTS/SID isolados
- Webcam no broker: apenas inventario/estado; NAO prova reconhecimento ou liveness
- Testes de camera Win+L anteriores vieram de um processo interativo da conta Filhos,
  nao de uma captura comprovadamente confiavel em LogonUI

## Proximas etapas em ordem

1. **P0-26: fronteira de captura confiavel.** Projeto e testes de um worker
   de video isolado com origem verificavel. Nao promover flags recebidas da
   conta Filhos a verdades do broker. Nenhum ticket de login neste estagio.
2. **P0-27: auditoria de dados biometricos.** Cadastro/descarte local,
   diretorio seguro, minimizacao, consentimento parental e protecao da
   conta administrativa. Sem capturar imagem infantil em GitHub Actions.
3. **P0-28: teste em hardware.** Medir se um worker confiavel consegue
   abrir e ler a camera no contexto real do Windows bloqueado.
4. **P0-29: testes de ataques de apresentacao.** Rejeicao de foto, video e
   duas faces com liveness valido, comprovado em equipamento real.
5. **P0-30: VM com snapshot e rollback.** Credencial de Windows e
   serializacao COM apenas depois de ter recuperacao comprovada.

## Padrao para cada execucao autonoma

1. Ler este checkpoint e HEAD atual no GitHub; nao repetir trabalho entregue.
2. Escolher **varias subtarefas relacionadas**, nao um commit isolado.
3. Escrever codigo e testes negativos; rodar GitHub Actions e corrigir falhas.
4. Atualizar o checkpoint com commit, provas verificadas e pendencias.
5. Comunicar "etapa X concluida; avancando para Y" durante o ciclo.
6. Parar somente por limite de duracao ou bloqueio verdadeiro (por exemplo,
   hardware fisico sem acesso). Uma automacao horaria retoma no ciclo seguinte.
7. Nunca executar procedimentos de login experimentais no computador familiar.

## Fora do escopo de provas ate nova evidencia

Nenhum resultado de testes simulados confirma protecao contra falsificacao
de rosto, liveness efetivo, acesso ao Secure Desktop ou desbloqueio Windows.
