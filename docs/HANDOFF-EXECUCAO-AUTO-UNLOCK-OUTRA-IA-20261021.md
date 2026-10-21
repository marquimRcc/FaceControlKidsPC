# FaceControlKidsPC — PLANO DE EXECUÇÃO TÉCNICA PARA OUTRA IA

**Data de referência:** 21/10/2026 (America/Sao_Paulo)  
**Natureza:** handoff executável, backlog, arquitetura, testes e critérios de aceite.  
**Repositório:** https://github.com/marquimRcc/FaceControlKidsPC  
**Branch reservada para a implementação:** handoff/facekids-auto-unlock-stabilization-20261021  
**Baseline de origem:** main em ef7eed1f324a9994528517ab4d3708ddc4248399  
**Responsabilidades:** a IA executora implementa e testa; o ChatGPT revisor analisa entregas e resultados, sem assumir desenvolvimento.  
**Estado deste documento:** diagnóstico estático e verificação de GitHub Actions. Nenhum teste de hardware, login/Winlogon ou instalação doméstica foi realizado pelo revisor nesta entrega.

> ORDEM DIRETA À IA EXECUTORA: trabalhe SOMENTE na branch acima, examine novamente seu HEAD antes de agir, avance em lotes de mudanças com commits e verificações, e entregue código funcional demonstrável. Não peça autorização a cada subetapa. Não modifique main, não faça merge, não altere a conta administrativa e não esconda ou desative provedores de credenciais padrão do Windows. Quando houver risco real de bloquear o acesso ao PC, pare somente a operação de instalação perigosa e prossiga com código, testes isolados e preparação de rollback. A senha local fixa de teste "1" para a conta Filhos é uma decisão expressa do proprietário: preserve-a nesta etapa; não substitua unilateralmente por cofre complexo ou rotação. Filtragem, firewall, internet e bloqueio de conteúdo estão em OUTRO PROJETO e NÃO fazem parte deste backlog.

---

## 0. A intenção do proprietário, sem reinterpretar requisitos

O PC é doméstico e de propriedade do responsável, usado pelos filhos. Uma única conta Windows local PADRÃO chamada **Filhos** é compartilhada por três crianças cadastradas facialmente. Há uma conta administrativa separada usada pelo responsável. A experiência pretendida é:

1. A criança senta diante da webcam (câmera USB, previamente reportada como XWF-1080P).
2. Quando a máquina está na tela de bloqueio da conta Filhos, o aplicativo detecta automaticamente um rosto, sem clicar em tile, abrir terminal, apertar botão ou digitar senha.
3. O rosto é reconhecido como uma das crianças cadastradas; o sistema consulta o saldo individual e o horário permitido.
4. Se permitido, o Windows DESBLOQUEIA A CONTA Filhos por seu mecanismo nativo de autenticação; o login administrativo não participa e não é afetado.
5. Aparece o acolhimento com nome, foto/avatar e tempo restante; um atalho opcional pode abrir Brave no YouTube Kids.
6. O uso efetivo em sessão ativa desconta minutos SOMENTE da criança corretamente identificada. Cada criança começa com 120 minutos/dia, configurável pelo responsável, com bônus.
7. Aos 10, 5 e 1 minutos restantes, aparecem avisos; ao zerar saldo ou atingir horário proibido, chama-se LockWorkStation na sessão Filhos.
8. Ao sair da cadeira, bloquear manualmente (Win+L), alternar a criança ou retornar depois, o estado é reavaliado. Enquanto o Windows estiver bloqueado, tempo não é cobrado.
9. O responsável ajusta fotos, cadastros, saldo, bônus, horários, histórico e programas no painel administrativo sem precisar entrar na conta Filhos.

**Decisões deliberadas e NÃO negociáveis nesta rodada:**
- Senha local Filhos = "1", fixa nesta fase. Usuário aceita esse risco em casa. A senha não será argumento para bloquear progresso ou redesenhar o projeto inteiro. Ainda assim, não imprimi-la em log, nunca transmiti-la pela rede nem armazená-la em eventos públicos; manter a credencial restrita ao componente que autentica o Windows.
- Login convencional por senha/PIN permanece disponível. O usuário NÃO exige nesta fase impedir um filho que conheça o PIN de fazer login. Portanto quota/horário NÃO são garantias invioláveis de acesso no cenário de senha conhecida.
- Não desenvolver firewall, DNS, filtragem web, bloqueio de aplicativos ou políticas de internet; existe outra frente responsável por isso.
- Prioridade máxima: EXPERIÊNCIA AUTOMÁTICA CONFIÁVEL da webcam à sessão Filhos. Não confundir “reconheceu rosto num aplicativo” com “o Windows destravou sem interação”.
- Não comprometer a conta administrativa, não configurar autologon geral do Windows por chave Winlogon e não criar uma tela falsa sobre o desktop fingindo ser login.
- Não obrigar implementação robusta de anti-spoofing ou IR/Windows Hello como condição de entrega doméstica. Pode registrar limitação explícita quanto a foto/vídeo e adicionar proteção leve que não destrua usabilidade.
- Privacidade: fotos, vetores, nomes e logs de crianças locais ao PC, nunca em commits, artifacts, telemetry, GitHub Actions ou chamadas de rede.
- Desenvolver de modo iterativo sem exigir novas autorizações para cada fase. Não alegar testes presenciais que não foram executados.

## 1. Estado verificado em 21/10/2026

Branches observadas no baseline: main, feature/face-access-gate, feature/filhos-face-quota-pilot, feature/parent-face-pilot, feature/windows-native-unlock-poc. PR #1 e PR #2 foram incorporados à main em 20/10.

Commits relevantes em main, do mais recente para o mais antigo:

| SHA curto | Entrega |
|---|---|
| ef7eed1f324a | Histórico 7 dias, horário permitido, PIN parental |
| bdb49a2fdfbd | Bônus personalizado no painel |
| de8037d9b1a6 | Brave abrindo YouTube Kids |
| 401394307786 | Cronômetro real, avisos, bloqueio automático |
| a4a63bd97032 | Painel administrativo de crianças, foto, perfil, quotas |
| d599028a9524 | Agente de sessão Filhos |
| 4131aca0acc6 | Tela de boas-vindas por criança |
| 052c6d90f2d1 | Ajuste do domínio local para LSA Negotiate |
| dc208d317cbd | Serialização real CredPack/CP e tentativa de auto-logon |
| 4025a006e8dd | DLL C++ de login + Named Pipe + instalador |

**GitHub Actions do baseline:** https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/39634262101

- Windows: 142 testes Python executados, 1 erro. Teste test_authenticator_nonexistent_db inicializa Recognizer ANTES de verificar ausência do banco e falha por ONNX indisponível na CI.
- Linux: os mesmos testes apresentam 2 erros: o problema do ONNX e tentativa de acessar ctypes.windll no teste de segurança Windows.
- O workflow C++ “Credential Provider compile and host checks” ficou verde, porém COMPILA o código DIAGNÓSTICO native/credential_provider_poc e não prova build/funcionamento de native/credential_provider_facekids (código de login real).
- Há binários compilados versionados em native/credential_provider_facekids, mas não considerar a existência deles como prova de build reprodutível.
- README e docs/ADR-003-WINDOWS-REAL-FACE-UNLOCK.md descrevem implementação anterior e podem contradizer os commits novos.
- Não há prova fornecida de login/desbloqueio automático real validado de ponta a ponta em Windows doméstico. Há evidências anteriores de leitura de webcam durante Win+L em processo interativo, que NÃO garantem captura no contexto do serviço/LogonUI.

**Regra da executora:** revalidar esses fatos ao abrir a branch: commits posteriores podem ter corrigido algo. Não aplicar mudanças desnecessárias que já existam.

## 2. Mapa de arquivos e funcionalidades presentes

### Login Windows / webcam
- native/credential_provider_facekids/FaceKidsProvider.cpp e .h: implementação COM ICredentialProvider e associação SID da conta Filhos.
- native/credential_provider_facekids/FaceKidsCredential.cpp e .h: autenticação assíncrona, GetSerialization, seleção automática de tile.
- native/credential_provider_facekids/FaceKidsPipeClient.h: cliente local do Named Pipe; lê resposta e decide ALLOW.
- native/credential_provider_facekids/FaceKidsSerialization.h: CredPackAuthenticationBufferW, pacote Negotiate, .\\Filhos.
- native/credential_provider_facekids/dllmain.cpp: registro do COM/CLSID {FAC0D042-3DD0-4A8C-9F18-440C44330C20}.
- native/credential_provider_facekids/build.ps1: build MinGW/w64devkit atualmente amarrado a caminho local.
- native/credential_provider_facekids/TestProviderHost.cpp e TestPipeClient.cpp: hosts/testes superficiais disponíveis.
- facekids/auth_service.py: webcam YuNet/SFace, verifica saldo/horário, responde AUTH_QUERY/ALLOW no pipe \\.\pipe\FaceKidsAuthPipe.
- facekids/recognition.py: carregamento dos ONNX, detecção/alinhamento/extração e comparação 1:N.
- facekids/children_pilot.py: cadastro e SQLite compartilhado/diretório por usuário, além do piloto legado.
- facekids/locked_face_probe.py, windows_lock_probe.py, hardware_camera_probe.py, webcam_observer.py: diagnósticos a reaproveitar.

### Sessão / quotas / UI
- facekids/filhos_agent.py: agente na sessão Filhos, relógio monotônico, avisos, auto LockWorkStation, last_unlock.json.
- facekids/storage.py: people, embeddings, daily_usage, daily_bonus, settings, PIN, histórico e curfew.
- facekids/welcome_screen.py: foto/nome/tempo e launch do Brave/YouTube Kids.
- facekids/avatar_utils.py: foto, avatar PNG, extração opcional de embedding a partir de arquivo.
- facekids/admin_dashboard.py: painel principal.
- facekids/admin_auth.py: PBKDF2 do PIN.
- facekids/session.py e locker.py: API WTS/estado de sessão e LockWorkStation.

### Instalação e QA
- scripts/Instalar-FaceKids-Nativo.ps1, scripts/Desinstalar-FaceKids-Nativo.ps1.
- Instalar-FaceUnlock.bat, Desinstalar-FaceUnlock.bat, abrir-facekids.bat e cadastrar-filho-*.bat.
- FaceKids-Teste-Webcam-WinL.bat: instalador de teste legado referenciando feature/windows-native-unlock-poc, NÃO confundir com instalação atual.
- .github/workflows/tests.yml, credential-provider-build.yml, windows-broker-build.yml, windows-broker-scm-vm.yml e demais.
- native/windows_broker_poc: experiências importantes P0-1..P0-42 com SID/WTS/ACL/SCM/IPC.
- docs/PROGRESSO-AUTONOMO.md e docs/POC-*.md: histórico antigo; confrontar com o que é utilizado hoje.

## 3. Fluxo alvo e limites reais da plataforma

Fluxo de desbloqueio na conta já conectada e bloqueada:

~~~text
USB webcam XWF-1080P
       |
Face Auth Worker (processo que comprovadamente acessa câmera mesmo sob Win+L)
       |  captura real, estabilidade facial, comparacao YuNet/SFace
       v
Servico/Broker ativo independentemente de login administrativo
       |  resolve childId, sessao WTS, SID da conta Filhos, quota, horario
       |  gera DECISAO de curta duração vinculada à sessão
       v
Named Pipe LOCAL com validação de origem, tamanho, timeout, dados tipados
       |
Credential Provider C++ V2 visível SOMENTE na conta Filhos
       |  CredentialsChanged / default tile + pbAutoLogonWithDefault
       |  GetSerialization com credencial local Filhos (senha "1")
       v
LogonUI/LSA/Windows valida logon ou unlock
       |
Evento confirmado de sessão Filhos ACTIVE (e não apenas ALLOW facial)
       v
Agente Filhos -> identifica criança -> boas-vindas -> quota/avisos/lock
~~~

**O Credential Provider não autentica por si só e não impede os provedores de senha/PIN.** Login/unlock acontece quando Windows aceita a serialização. Preservar sempre ao menos um método normal de login do Windows (inclusive do administrador). Documentação oficial:
- https://learn.microsoft.com/en-us/windows/win32/secauthn/credential-providers-in-windows
- https://learn.microsoft.com/en-us/windows/win32/api/credentialprovider/nf-credentialprovider-icredentialprovider-getcredentialcount
- https://learn.microsoft.com/en-us/windows/win32/api/credentialprovider/nf-credentialprovidercredential-getserialization
- https://learn.microsoft.com/en-us/windows/desktop/Services/interactive-services

Separar explicitamente estes estados:
1. Windows ligado na tela de login antes do PRIMEIRO logon da conta Filhos.
2. Sessão Filhos já iniciada, depois bloqueada com Win+L (primeira meta obrigatória).
3. Volta de suspensão/hibernação/monitor desligado com sessão Filhos bloqueada.
4. Conta administrativa ativa ou bloqueada — FaceKids NUNCA deve tentar autenticar no lugar dela.
5. Troca rápida de usuário para Filhos, com ou sem sessão preexistente.

Não prometer que um único processo Python interativo resolve todos esses estados. Serviço Windows executa na Sessão 0 e NÃO pode mostrar interface no desktop do usuário; webcam DirectShow/MSMF em Sessão 0 deve ser validada empiricamente. Se um worker em Sessão 0 não acessa o hardware sob Win+L, definir arquitetura alternativa e comprovar antes da instalação real. Um agente em Filhos já conectado pode resolver unlock, mas não necessariamente logon a frio. **Jamais esconder esse gap.**

## 4. Problemas encontrados: evidências concretas e solução esperada

### A. Critérios do pipe e credencial (alta prioridade)
- auth_service.py usa SDDL_PERMISSIVE com (A;;GA;;;IU): usuários interativos têm acesso amplo. FaceKidsPipeClient.h considera sucesso se a resposta contiver a substring "ALLOW". Um servidor ou conteúdo inadequado pode simular a decisão.
- ALTERAR para contrato explícito versão/operação/status/child_id/session_id/nonce/timestamp; limitar tamanho; rejeitar JSON inválido/status desconhecido/múltiplos campos; o processo cliente não decide por substring.
- Validar token/SID da contraparte, lado servidor e, quando aplicável, lado cliente. Usar ACL mínima para o cenário local real. Aproveitar princípios do Broker C++ protegido antigo; NÃO conectar cegamente o pipe experimental antigo como se já fornecesse biometria.
- Colocar timeout FINITO em conexão, leitura, processamento e cancelamento. Detectar travamento do worker/câmera e manter login convencional disponível.
- O usuário autorizou senha "1" fixa; mantê-la para .\\Filhos sem exigir solução de cofre nesta fase, mas nunca gravá-la no last_unlock.json ou mostrar em eventos/UI/logs. Não mandar credencial a clientes arbitrários da conta Filhos.
- Credential Provider: validar m_eligible ANTES de indicar auto-logon; revisar estado m_readyToAutoLogon, repetição de GetSerialization, ReportResult para senha inválida, cancelamento da thread, ciclo COM, uso de ponteiro m_pProvider durante thread, limpeza de credenciais em memória quando viável.
- Avaliar o contrato GetCredentialCount/pbAutoLogonWithDefault e NotifyAuthSuccess/CredentialsChanged em host de testes e no LogonUI verdadeiro.

### B. Ciclo de vida do worker
- Instalar-FaceKids-Nativo.ps1 atualmente adiciona script VBS no Startup do ADMINISTRADOR, em vez de serviço independente. Após logout/reboot sem login admin, o processo poderá não estar ativo. Isso contradiz o requisito sentar-e-desbloquear.
- Mesmo script usa taskkill /f /im pythonw.exe: pode matar Python alheio ao produto. SUBSTITUIR por controle específico via PID/serviço/tarefa identificados do FaceKids.
- Criar identidade estável do componente de autenticação iniciado no boot (SCM ou tarefa apropriada), com restart supervisionado e logging local rotativo. Confirmar câmera disponível sob contexto escolhido.
- Usar um único proprietário da câmera por vez; fechamento/liberação em finally; política para disputa com webcam em uso; fila, exclusão mútua, timeout e retentativas sem CPU 100%.

### C. Agente Filhos e agendamento
- Instalador cria schtasks /sc onlogon sem associar claramente o usuário/ambiente interativo de Filhos; pode executar em usuário errado ou não aparecer no desktop.
- Em filhos_agent.py, validação de identidade/conta precisa usar token Windows, não apenas variável USERNAME. Rodar exclusivamente na sessão Filhos interativa.
- Inicializar uma única instância por sessão usando mutex correto; não reabrir welcome em loop.
- Agente deve ser instalado/iniciado/reiniciado de modo reprodutível e removido no uninstall.
- O serviço de login/autorização não pode depender da vida do agente. Falha de agente não deve afetar administrador nem impedir login tradicional.

### D. Identidade incorreta após login por PIN
- filhos_agent.py lê C:\ProgramData\FaceKids\last_unlock.json. Na ausência desse evento usa o primeiro filho cadastrado. welcome_screen.py usa fallback no ID 2 e saldo 7200; isto gera foto, saldo e descontos de OUTRA criança.
- **PROIBIDO qualquer fallback arbitrário de child_id/nome/120 minutos.**
- Requisito: após login convencional, exibir estado "criança ainda não identificada", capturar/confirmar rosto no desktop se possível, ou orientar identificação. Enquanto não houver identificação confiável, não atribuir consumo a alguém aleatório.
- Não bloquear usuário por ter usado PIN nesta fase; o proprietário aceitou essa possibilidade.
- Evento facial tem session_id, child_id, created_at, expiração curta, identificador único e estado de confirmação da sessão Windows. Limpar eventos obsoletos.
- Troca de criança diante da webcam durante sessão já ativa deve solicitar reidentificação e atualizar o filho responsável pelo tempo, com período de tolerância claramente definido.
- Nenhum child_id derivado de foto ou nome de arquivo deve substituir a decisão do reconhecedor efetivo.

### E. Quota e persistência
- Storage local grava daily_usage e daily_bonus SQLite; filho agente hoje faz charge diretamente. Em um PC doméstico isso pode servir à experiência inicial, mas configurações precisam continuar coerentes entre painel admin, agente e serviço.
- Se a mesma base é escrita por múltiplos processos, impor transações atômicas, WAL/busy_timeout adequados, evitar múltiplos débito do mesmo intervalo, garantir fechamento/conexões por processo.
- relógio monotônico para duração; data civil local para reset diário; suspensões, hibernação, sessão bloqueada, troca de usuário, diferença de relógio, virada da meia-noite e reinício do agente não podem gerar consumo fantasma.
- Limite padrão 120 min por criança, sem pressupor IDs 1/2/3 se migração/edit de perfis mudar linhas. Bônus e horários gerenciáveis no painel; ausência de regra de curfew = permitido.
- Consolidar uma única fonte de verdade para quota/config. Se criar Broker protegido já nesta rodada, não introduzir segundo SQLite paralelo acidental; preservar e migrar dados sem apagá-los.
- Definir política “rosto desconhecido”: pausar atribuição e reidentificar, nunca gastar saldo do primeiro filho nem bloquear imediatamente conta do administrador.
- Não confundir “tempo do PC ligado” com “tempo da sessão Filhos ativa e criança identificada”.

### F. UI, avatar e dados sensíveis
- auth_service.py escreve last_unlock.json antes de saber se o Windows autenticou realmente e inicia welcome_screen logo após ALLOW via subprocess. Se estiver em sessão 0 ou desktop/admin errado, a janela pode não aparecer ou aparecer na conta inadequada.
- Exibir welcome SOMENTE após confirmação da sessão Filhos ACTIVE, dentro da sessão interativa Filhos, e somente uma vez por autenticação/retorno. Associar foto à identidade facial realmente confirmada.
- Remover fallback aleatório que mostra outra criança e contabiliza saldo fictício. Calcular barra de progresso usando limite + bônus real, não total fixo de 7200.
- Abertura de Brave/YouTube Kids é opcional e deve ocorrer exclusivamente na conta Filhos; não execute aplicações configuráveis via shell=True com parâmetros arbitrários provenientes de JSON gravável pela conta das crianças. Usar execução sem shell, argumento separado e lista administrada pelo responsável.
- As fotos JPEG/PNG e embeddings devem ficar fora do Git, fora dos logs e com exclusão por criança disponível; registrar retenção local. Não prometer que delete em SQLite é apagamento físico irrecuperável em SSD.
- Painel só aparece no contexto autorizado do responsável; is_admin_account não deve dar permissão a qualquer usuário diferente de "Filhos", especialmente via fallback de variável de ambiente. Verificar papel por token/SID ou admin Windows efetivo.
- PIN parental está com PBKDF2 no módulo admin_auth.py; conservar, mas não chamar de proteção de sistema se o banco é editável pela conta Filhos. Teste de PIN: se configurado, operações sensíveis pedem acesso; sem PIN inicial, deixar claro que painel depende do Windows administrativo.
- Não colocar nomes/fotos de crianças em prints, logs de CI ou artifacts.

### G. Instalação / desinstalação
- Instalar-FaceUnlock.bat e outros comandos têm caminho rígido C:\Users\MarcosMiniPC\Documents\git\FaceControlKidsPC; localizar raiz por caminho do próprio script e aceitar clone em local diferente.
- Compilador MinGW referenciado por caminho pessoal; detectar ferramenta disponível ou fornecer dependência explícita com erro informativo; CI compila a mesma fonte.
- Instalar apenas componente pretendido, pedir elevação UAC de modo explícito, checar arquitetura x64, existência da conta local Filhos/SID e o método de recuperação/admin antes de registro.
- Não instalar / registrar DLL automaticamente numa mera execução de testes ou import de módulo.
- Remoção atual não exclui necessariamente o Startup por usuário, tarefa agendada FaceKidsFilhosAgent e arquivos associados; tem ErrorActionPreference SilentlyContinue e imprime “estado original restaurado” sem provar. Corrigir com rastreamento real de recursos criados e validação pós-uninstall.
- Não fazer registro silencioso em máquina do usuário até haver backup/rollback e teste isolado documentados. Criar opção de dry-run / preflight; opção real somente consciente do risco da integração LogonUI.
- Preservar providers nativos de senha/PIN e acesso administrativo. Nunca filtrar globalmente ou esconder a conta/admin.
- Testar uninstall idempotente, reinício depois da remoção e ausência de recursos órfãos. Não deletar fotos/quotas no uninstall sem escolha explícita do responsável.

### H. Código obsoleto, testes verdes e documentação
- README, ADR-003, PROGRESSO-AUTONOMO e várias POC afirmam que CP real ainda não serializa; estão desatualizados frente a native/credential_provider_facekids.
- Há dois caminhos de CP/Broker: o antigo “somente diagnóstico” e o novo “faz logon”. Definir de forma explícita qual é o produto atual e o que permanece legado experimental; não apagar código antigo sem antes aproveitar guardrails seguros.
- O teste tests/test_windows_login_guardrails.py só inspeciona native/credential_provider_poc/provider.cpp; ampliar para cobrir a DLL real e separar premissas do código diagnóstico. Não remover guardrails antigos apenas para conseguir CI verde.
- A pipeline principal roda Linux e Windows; não adicionar teste que suponha hardware/ctypes.windll em Linux sem skip/mock. Testar estado sem banco ANTES de inicializar modelos ONNX.
- Não fazer commit de .venv, sqlite3, fotos, logs, credenciais ou ONNX. Acrescentar entradas pertinentes ao .gitignore se necessário.

---

## 5. Decisão arquitetural proposta: integrar, não refazer tudo

Manter Python para CV/GUI/quotas iniciais e C++ nativo para o Credential Provider. A IA deve avaliar dois caminhos e escolher com evidência:

**Caminho mínimo para primeiro aceite (preferível se funcionar em hardware):**
- FaceAuthWorker Python iniciado independentemente de login administrativo e capaz de acessar câmera durante Win+L.
- API local autenticada/restrita; valida childId, quotas e horário, responde veredito tipado de uso único.
- Credential Provider C++ real manda consulta sem bloquear LogonUI e serializa .\\Filhos com senha fixa "1" somente após veredito positivo; timeout => não tenta login.
- Agente Filhos identifica sessão ACTIVE, lê evento confirmado, mostra welcome e conta uso. Migração de SQLite sem perda.

**Caminho alternativo, se o worker autônomo não abrir webcam sob Win+L:**
- Serviço de autorização no boot + worker de webcam num contexto apropriado comprovadamente ativo enquanto Filhos está bloqueada; IPC com permissão compatível e sem depender da sessão admin.
- Validar ao menos Win+L com sessão Filhos já iniciada; para logon a frio construir spike separado. Se só o unlock funcionar, registrar cold boot como pendência e não mascarar o resultado.

**Elementos aproveitáveis do P0 antigo:** verificação WTS/SID, ACL de pipe, SCM, condições deny-by-default, SQLite protegido, medidor monotônico, one-use preflight. Reaproveitar apenas componentes que façam sentido e tenham cobertura. Evitar duas fontes de quotas ou duas decisões de acesso concorrentes.

**Padrão de resposta de autenticação sugerido (conceitual; a IA define codec):**
~~~json
{
  "version": 1,
  "request_id": "<identificador não repetível>",
  "status": "ALLOW | DENY_UNKNOWN | DENY_QUOTA | DENY_CURFEW | ERROR",
  "target_user_sid": "<SID local de Filhos>",
  "session_id": 3,
  "child_id": 2,
  "expires_at": "<instante de validade curto>",
  "message": "mensagem não sensível"
}
~~~
Acima é contrato ilustrativo, NÃO significa colocar senha no JSON. O principal: resposta de fonte confiável, vinculada à requisição/sessão, validade curta, sem substring matching. Não usar só timestamp/nonce sem autenticar o peer. Se optar por protocolo binário, documentar campos e testes de limites.

## 6. Backlog de execução obrigatória (P0-43 a P0-55)

Cada etapa deve resultar em código, testes automatizados, commit e um registro de evidência no final deste documento (ou relatório de status separado na própria branch). Prioridades não são desculpa para parar depois de cada commit; avançar em sequência. Os IDs abaixo são desta nova rodada e NÃO afirmam existir como issues.

### P0-43 — Baseline, CI e contrato de testes (BLOQUEADOR)
**Implementar:** testes importáveis em Windows e Linux; refatorar FaceAuthenticator.evaluate para verificar falta de banco e pré-condições antes de carregar ONNX; diferir/lazy-load do Recognizer ou injeção fake. create_security_attributes deve ser testado só em Windows ou com mock explícito; isolar imports de plataforma. Não mascarar erros reais com skip geral. Adicionar smoke de contratos que exercitam nome da conta e caminhos mínimos sem webcam.  
**Arquivos:** facekids/auth_service.py, tests/test_auth_service.py, .github/workflows/tests.yml e, se necessário, recognition.py.  
**Aceite:** GitHub Actions Unit tests VERDE Windows + Ubuntu; toda a suíte antiga continua rodando; logs mostram contagem e zero errors/failures. Guardar links e SHA dos runs.  
**Não fazer:** criar arquivo ONNX real apenas para passar um teste que deveria ser unitário; reduzir cobertura para esconder erro.

### P0-44 — Build reprodutível do Credential Provider REAL
**Implementar:** job Windows que compile native/credential_provider_facekids/FaceKidsProvider.cpp, FaceKidsCredential.cpp, dllmain.cpp, etc. Garantir x64, dependências e exports corretos; rodar TestProviderHost.exe e TestPipeClient.exe com casos de NEGATIVA e timeouts em processo isolado. Não registrar DLL no runner/PC sem intenção. Gerar binário apenas como artifact de CI se desejado.  
**Aceite:** teste que falha se real source não compila; versão reportada por commit; diagnóstico separado continua verde; não confundir verde do antigo com novo.

### P0-45 — Prova de ciclo de vida do serviço facial sem admin logado
**Implementar:** remover dependência do Startup VBS do administrador, selecionar mecanismo de boot supervisionado com logs e recuperação, identificar contexto real de acesso à câmera.  
**Testes:** preflight start/stop/restart, reinício após crash, serviço ausente, pipe inacessível, Windows LogonUI sem congelar, processo alheio pythonw preservado.  
**Aceite:** com o admin desconectado, serviço continua disponível após reboot. Capacidade de abrir XWF-1080P durante Win+L comprovada fisicamente; se não viável, documentar matriz de alternativas, implementar worker de sessão apropriado e repetir prova. NÃO supor serviço SCM = acesso a câmera.

### P0-46 — Contrato pipe correto e status tipado
**Implementar:** remoção de SDDL IU GA, permissões apropriadas, autenticação do peer, protocolo com parse exato e versão/req ID/validade/identidade/sessão; códigos de erro definidos. Evitar aceitar string de status em campo aleatório como ALLOW.  
**Testes:** PING não autoriza, fake ALLOW no corpo é NEGADO, mensagem truncada/JSON inválido, tamanhos excessivos, cliente não autorizado, múltiplas solicitações, replay, servidor travado, timeout e cancelamento.  
**Aceite:** nenhum GetSerialization positivo se origem/parsing/condições não forem validados. Não exigir remoção da senha fixa "1".

### P0-47 — Máquina de estados do Credential Provider, autologon sem clique
**Implementar:** identificar tile de Filhos por SID; seleção automática e comunicação async; thread segura e serialização CredPack Negotiate; reset de estado após falha; quitação de recursos COM. Não iniciar loops de tentativas após negar, quota zerada ou indisponibilidade de webcam.  
**Testes:** host mock de ICredentialProviderEvents, mock de credenciais válidas/inválidas; 0 tiles para usuário errado; 1 tile quando Filhos presente; pbAutoLogonWithDefault somente com autorização vigente; senha "1" só para Filhos; GetSerialization nunca para admin; timeout sem UI travada.  
**Aceite FÍSICO:** Windows já bloqueado em Filhos => criança senta => webcam reconhece => LogonUI retorna ao desktop Filhos SEM clicar no tile/pressionar Enter/digitar senha. Se Windows exigir interação na tela ou selecionar provider de senha primeiro, investigar evento e seleção em LogonUI real e só declarar concluído quando houver prova. Preservar método de recuperação padrão.

### P0-48 — Sessão Filhos, agente e welcome após sucesso real
**Implementar:** tarefa de inicialização corretamente vinculada à conta Filhos/sessão interativa. Agente independente do login admin, uma instância, identificação por token, observação WTS. O worker não exibe Tkinter no desktop do SYSTEM. Registrar evento de reconhecimento limitado à sessão e fazer o agente exibir welcome após efetiva sessão ACTIVE.  
**Testes:** login por rosto, login por PIN, Win+L, troca de usuário, falha antes do logon, arquivo ausente/stale, duas janelas simultâneas, admin online.  
**Aceite:** nome/foto/tempo corretos uma única vez; nenhuma janela na conta administrador; o sistema não marca “desbloqueado” apenas por ALLOW da câmera.

### P0-49 — Identidade correta no login manual e troca de criança
**Implementar:** eliminar fallback para primeiro filho e ID=2/7200; estado UNIDENTIFIED após entrada por senha/PIN; reconhecimento na sessão ativa; reidentificação quando criança muda ou após período de ausência; política explícita de transição e pausas.  
**Testes:** entrada manual sem last_unlock; evento de outro dia; troca A->B; ausência de face; face desconhecida; dois rostos; webcam ocupada; remapeamento de ID após cadastro; reinício do processo.  
**Aceite:** nunca debitar filho errado por identidade presumida; no login por PIN criança pode se identificar sem bloquear login tradicional.

### P0-50 — Cronômetro/quotas de ponta a ponta
**Implementar:** integrar saldo, desconto por monotonic, estados WTS, curfew, bônus, notificação, bloqueio. Evitar cobranças duplas e saldos negativos. Estado NO_FACE/UNKNOWN não debita ninguém. Reavaliar quota no momento imediatamente anterior à serialização e após mudanças administrativas pertinentes.  
**Testes:** 3 filhos 120min independentes, horários configuráveis, ajuste customizado e +15/+30/+60, virada de dia, suspensão/hibernação, reinicialização do agente, troca de perfil, Win+L com pausa, tentativa de auto-unlock sem saldo deve NEGAR, login PIN ainda disponível.  
**Aceite:** saldo de A nunca debita B, sessões bloqueadas nunca geram cobrança, esgotamento bloqueia somente Filhos, administrador não recebe LockWorkStation acidental.

### P0-51 — Painel dos pais coerente e permissões domésticas
**Implementar:** painel lê/escreve a MESMA fonte de verdade; validação por conta administrativa/SID; PIN parental opcional; webcam para cadastro e arquivo de imagem permitido como auxiliar; histórico real sete dias; bônus/horário/renomear/remover. Configurar Brave/YouTube Kids e outros apps com argumentos seguros sem shell.  
**Testes:** painel admin permitido; painel Filhos negado; PIN certo/errado; alteração de quota impacta imediatamente agente e autorização; foto/embedding trocados; remoção facial não apaga tempo; nomes e IDs sem pressuposição.  
**Aceite:** pais podem fazer ajustes sem entrar na conta Filhos; todos os componentes refletem alteração consistente.

### P0-52 — Instalação, atualização e rollback idempotentes
**Implementar:** scripts relativos à pasta repo, preflight de conta Filhos/SID e arquitetura; registrar apenas a DLL real após validação consciente; instalar worker e agente; verificar instalação por status; rollback se falha; desinstalar SOMENTE FaceKids e deixar login Windows e outros pythonw intactos. Registrar manifesto dos recursos criados (serviço/tarefa/startup/registry/arquivo) para remoção.  
**Testes:** dry-run, instalação em diretório com espaços, instalação repetida, falha no meio, remove/reinstala, sem credenciais admin comprometidas, sem tarefa órfã, sem deixar pasta de fotos apagada sem consentimento.  
**Aceite:** instalador não mata processos alheios; uninstall confirma itens realmente removidos e não afirma restauração completa sem verificar; login manual continua funcionando.

### P0-53 — Suite integrada e hardware real
**Implementar:** cobertura unitaria, integração broker/pipe/CP/agent sem LogonUI e checklist manual de hardware. Registrar resultado verdadeiro por estado de sessão.  
**Matriz de hardware:** webcam XWF-1080P; luz clara/baixa; 1 filho de cada vez; óculos; rosto não autorizado; 2 faces; câmera desconectada; webcam ocupada; tela Win+L; suspender/acordar; reboot; admin deslogado; conta Filhos já logada; criança com 0 saldo; curfew; login manual.  
**Aceite:** nenhuma evidência inventada, CI verde + vídeo/log local/redação de teste físico com procedimento replicável. Logs sem rostos e sem senha.

### P0-54 — Documentação arquitetural e guia operacional
**Implementar:** atualizar README, ADR-003, docs/PROGRESSO-AUTONOMO.md e novos docs de instalação, recuperação e testes. Declarar claramente o que funciona em Win+L e no boot a frio, e que PIN manual contorna bloqueio facial. Arquivos legados marcados DIAGNOSTIC/EXPERIMENTAL.  
**Aceite:** um responsável não técnico consegue instalar, cadastrar 3 filhos, testar, restaurar e desinstalar sem adivinhar parâmetros; documentação coincide com código/testes.

### P0-55 — Pacote de entrega para revisão externa
**Implementar:** consolidar commits, URLs de CI, lista de riscos conhecidos, status de cada cenário físico e documentação de uso. Criar PR da branch para main SOMENTE se o proprietário pedir; deixar branch pronta para revisão sem merge automático.  
**Aceite:** revisor externo consegue rastrear cada requisito até código/teste/evidência. Diferenças da baseline explicitadas. Nenhum dado de criança versionado.

---

## 7. Sequência de execução recomendada (lotes, sem microparadas)

**Lote 1: base confiável (P0-43, P0-44).** Corrigir CI dos dois sistemas e construir o módulo nativo de verdade. Não exigir webcam. Commit(s), Actions verdes.  
**Lote 2: caminho de auto unlock (P0-45, P0-46, P0-47).** Inicialização independente do admin + acesso real à webcam no bloqueio + IPC + CP auto. Prioridade absolutamente maior. Se parte depende de teste presencial, continuar implementando harness/diagnósticos e marcar pendente.  
**Lote 3: experiência e quota (P0-48, P0-49, P0-50, P0-51).** Identidade individual correta, agente, interface, saldo, painel.  
**Lote 4: entrega robusta (P0-52, P0-53, P0-54, P0-55).** Instalação/rollback, teste no PC, docs e relatórios.

Não implementar apenas “uma tela bonita” sem desbloqueio nem adicionar novas features fora do objetivo. Manter foco no caminho mais curto comprovável para a criança SENTAR -> WINDOWS DESBLOQUEAR.

## 8. Requisitos funcionais e aceites (rastreabilidade)

| ID | Cenário | Resultado esperado | Evidência mínima |
|---|---|---|---|
| RF-01 | Admin bloqueado | FaceKids não tenta logar/desbloquear conta admin | teste SID/logon |
| RF-02 | Filhos em Win+L, filho A com saldo | Desbloqueia sozinho com webcam sem clique | teste Windows real |
| RF-03 | Filhos em Win+L, filho B com saldo | Mesmo resultado e ID B correto | teste Windows real |
| RF-04 | Filhos em Win+L, filho C com saldo | Mesmo resultado e ID C correto | teste Windows real |
| RF-05 | Face desconhecida | Sem autologon; login normal continua disponível | teste real e unit |
| RF-06 | Saldo zero | Sem autologon facial; mensagem correta | teste real/integração |
| RF-07 | Fora do horário | Sem autologon facial; curfew informado | teste real/integração |
| RF-08 | Entrada Filhos por PIN | Não quebrar login; não presumir filho | teste real |
| RF-09 | Windows Filhos ACTIVE identificado | Contar tempo do filho identificado | teste monotonic |
| RF-10 | Filhos Win+L | Pausar cobrança de minutos | teste WTS |
| RF-11 | Virada do dia | Quota renovada para novo dia local | teste unidade |
| RF-12 | Troca A -> B | A para, B começa apenas após identificação | teste integração |
| RF-13 | Falha na câmera | Não congelar LogonUI; fallback convencional | teste real |
| RF-14 | Broker/serviço ausente | Não travar Windows; senha/PIN disponível | teste real isolado |
| RF-15 | Admin concede bônus | Saldo atualizado e desbloqueio após rechecagem | teste integração |
| RF-16 | Notificações | 10/5/1 min uma vez por faixa, sem spam | mock/UI |
| RF-17 | Quota chega a zero | Bloquear Filhos, não admin | teste real acompanhado |
| RF-18 | Admin faz logout | Worker de reconhecimento permanece operacional | teste real |
| RF-19 | Reboot até tela de logon | Registrar se opera a frio sem login prévio | evidência real; se não, gap declarado |
| RF-20 | Desinstalação | CP do FaceKids removido, login normal permanece | teste recuperação |
| RF-21 | Dados biométricos | Somente armazenamento local, remoção individual | inspeção/teste |
| RF-22 | Programas infantis | Brave/YouTube Kids apenas em Filhos, opcional | teste conta |
| RF-23 | Duas faces simultâneas | Sem identificação silenciosa indevida (exigir política explícita) | teste câmera |
| RF-24 | Webcam ocupada/desconectada | Recuperação, timeout e não travar desktop | teste real |
| RF-25 | IDs e nomes editados | Quotas e fotos acompanham ID correto | teste persistência |

**Meta mínima de produto:** RF-01, RF-02, RF-03, RF-04, RF-05, RF-06, RF-08, RF-09, RF-10, RF-17, RF-18, RF-20.  
**Meta completa:** todos acima; RF-19 deve ser registrado honestamente conforme capacidade real, sem bloquear o MVP Win+L se o cold boot exigir componente adicional.

## 9. Plano de testes técnicos — unidade, integração e sistema

### Casos de autenticação e IPC
- AUTH_QUERY com formato correto, resposta ALLOW positiva somente após reconhecimento e quota.
- Rejeitar payload inventado sem token permitido, JSON inválido e status contendo "ALLOW" em mensagem em vez de campo status.
- Dois clientes concorrentes, cliente desconectado, pipe ausente, timeout de 2/5/10 segundos conforme contrato efetivo, resposta grande/truncada.
- A tentativa de usar um ALLOW vencido ou de outro session_id/userSid deve ser negada.
- Escopo LogonUI: não dar login se o tile Filhos não está presente no user array.
- Simular ReportResult de credencial inválida e verificar que o CP retorna estado NÃO AUTENTICADO; não disparar laço infinito.
- Verificar leak de handle/thread/COM em instâncias repetidas, cancelamento durante Win+L/UNLOCK, reabertura após erro.
- Se der para reproduzir em host COM, logar somente códigos de retorno e propriedades não sensíveis.

### Casos de reconhecimento
- Todas as faces da webcam no mesmo frame avaliadas; escolher política de 1 rosto válido para desbloqueio ou definir claramente critério, evitando usar indiscriminadamente maior área.
- Dois frames iguais não bastam como prova de presença real; neste PC doméstico aceitar limitação, mas usar pelo menos estabilidade temporal e score/margem, evitar travamento em reflexos.
- Limiar do novo auth_service usa identify(threshold=0.38, min_margin=0.04), diferente do default identify (0.50, 0.07); calibrar em webcam real com falsos positivos/negativos, não copiar valor arbitrário sem dados.
- Logs de score podem usar ID pseudônimo, jamais imagem real.
- Em falha de carregamento ONNX, reportar erro e manter login manual.
- Cadastros renováveis sem corromper outros perfis; uma criança por vez.

### Casos de quota/horário
- Regras de allowed interval inclusive turnos que cruzam meia-noite, exemplo 20:00->06:00, com interpretação documentada.
- Saldo 0, saldo 1 segundo, expiração durante processo facial, bônus aplicado enquanto bloqueado.
- Contagem após sleep/hibernação: usar monotonic e limite de deltas plausíveis; não debitar horas suspensas, não “perder” 2min por delta descartado após máquina ativa.
- Locks duplicados: não chamar LockWorkStation em todas as voltas quando já bloqueado.
- Reinício do agente sem duplo desconto, DB WAL concorrente, arquivo SQLite temporariamente busy.
- PIN manual com último unlock de ontem: não pode atribuir tempo ao último perfil ou default.

### Casos Windows e interface
- Win+L em conta Filhos; login a frio; login admin; usuário trocado; sessão desconectada; RDP se utilizado.
- Janela welcome na sessão certa com nome/tempo/foto, única, fechável.
- Brave só abre no perfil Filhos, com caminhos encontrados dinamicamente; no erro não travar login.
- Task startup em Filhos, sem exigência de login admin; logs locais rastreiam PID e sessão, não credencial.
- Cleanup total da instalação do CP, tarefa, serviço, configs; opção preservar dados pessoais.

## 10. Protocolo seguro de teste no computador real

O hardware fica sob controle do proprietário. Testes que mexem em LogonUI e registro de CP podem provocar falha no login. Antes de cada implantação real:

1. Confirmar uma conta administradora recuperável por senha/PIN NORMAL do Windows e acesso conhecido; não modificar esse provider.
2. Registrar os recursos que serão alterados, exportar chaves relevantes e criar mecanismo de rollback; para mudanças mais sensíveis usar ambiente descartável/VM com snapshot quando adequado. VM não substitui prova da webcam real.
3. Compilar nativamente em ambiente controlado, verificar arquitetura e integridade do binário.
4. Testar os componentes sem instalação (unit, host COM, pipe local, webcam read-only).
5. Testar primeiro o fluxo já LOGADO Filhos -> Win+L -> criança retorna -> unlock; responsável acompanha fisicamente.
6. Depois experimentar reboot e sessão administrativa ausente, sem alterar qualquer credencial admin.
7. Em qualquer falha, retornar via login normal e oferecer script de uninstall/rollback validado.
8. Não instruir o proprietário a apagar senha admin, excluir Microsoft CPs ou habilitar autologon genérico com a senha "1" no registro.

**Proibição de falsa evidência:** GitHub Actions não dispõe da XWF-1080P doméstica nem prova que o LogonUI nativo recebeu a credencial. A executora deve pedir somente os resultados manuais estritamente necessários quando houver bloqueio físico, não prometer automação completa a partir de CI.

## 11. Instruções de qualidade, logs e observabilidade

- Adicionar logs locais rotativos em C:\ProgramData\FaceKids\logs ou pasta equivalente. Incluir data/hora, processo, PID, Windows session_id, estado WTS, childId pseudônimo, etapa e duração; não incluir imagem nem senha.
- Usar correlation/request ID da câmera até CP/agent para depurar sem adivinhar qual criança desbloqueou.
- Para erro no desbloqueio registrar “camera indisponível”, “sem face”, “desconhecido”, “quota zero”, “curfew”, “IPC indisponível”, “credencial rejeitada” distintamente.
- Evitar log repetitivo contínuo em polling, implementar backoff e limitação de log.
- A CI deve executar Python 3.11 em Windows e Ubuntu, build nativo Windows e testes negativos. Não incluir webcam real na matriz CI.
- Commits coesos por lote, com mensagens claras, PR opcional somente ao final e após pedido do usuário.
- Documentar limitações sem linguagem alarmista: projeto doméstico, senha fixa por escolha, login PIN permitido, controle facial não é segurança antifraude inviolável.

## 12. Como trabalhar sem parar a cada microetapa

Procedimento obrigatório para IA executora, no início e a cada rodada:

~~~powershell
git fetch origin
git switch handoff/facekids-auto-unlock-stabilization-20261021
git pull --ff-only origin handoff/facekids-auto-unlock-stabilization-20261021
git status --short
git log -5 --oneline
~~~

1. Ler este handoff e revisar o HEAD atual e as últimas CI, identificando o que já foi implementado por outras rodadas para não duplicar.
2. Escolher o próximo lote P0 e trabalhar em várias subtarefas correlatas até entregar um resultado técnico verificável.
3. Antes do commit, executar testes locais compatíveis; após push, verificar os jobs GitHub e corrigir regressões — nada de declarar verde sem conclusão.
4. Em cada commit/entrega registrar ID P0, SHA, arquivos, testes locais, GitHub Actions (URL e conclusão), comportamento verificado e pendências reais.
5. Prosseguir automaticamente com o item seguinte **na mesma sessão de trabalho** quando houver capacidade. Não interromper por mera conclusão de uma etapa, não aguardar resposta para cada commit.
6. Se uma atividade depender de câmera/Winlogon no PC doméstico sem acesso remoto, identificar precisamente qual comando diagnóstico é seguro e qual evidência falta, e seguir com itens de código/testes independentes.
7. NÃO alegar que o assistente revisor ou automações externas estão implementando. A divisão é inequívoca: outra IA desenvolve; revisor audita.

## 13. Modelo obrigatório de relatório da IA executora

~~~text
FaceKids — Execução [data/hora BR]
Branch e HEAD:
P0(s) concluídas:
Resumo das alterações (arquivos/funções):
Comandos/testes locais executados e resultados:
Links GitHub Actions e estado final (success/failure):
Matriz de hardware: comprovado / não testado / falhou:
Auto unlock Win+L sem clique: SIM comprovado / NÃO comprovado
Autenticação a frio após reboot: SIM comprovado / NÃO comprovado
Login administrativo convencional intacto: evidência
Regressões/riscos remanescentes:
Próxima atividade a executar:
~~~

Evitar relatórios “100% pronto” sem testes de hardware/CI. Separar implementação de validação física.

## 14. Correções com maior relação custo/benefício

Executar primeiro as que destravam entrega:
1. Tornar CI verde, incluir novo CP real.
2. Provar processo facial/câmera vivo sob Win+L SEM admin logado.
3. Fazer CP reagir automaticamente e serializar credencial de Filhos após reconhecimento válido sem toque em tile.
4. Corrigir last_unlock e fallback de criança; quota individual confiável.
5. Garantir Startup de Filhos e instalação/rollback.
6. Atualizar painel/documentação e teste dos 3 filhos.

**NÃO priorizar neste momento:** firewall, DNS, bloqueio de YouTube/Redes Sociais, empacotamento Linux/Regata OS, mobile, API na nuvem, telemetria, dados remotos, liveness profissional por câmera IR, criptografia excessiva que inviabilize login doméstico, cadastro administrativo facial, troca obrigatória da senha "1" ou redesign visual completo.

## 15. Definição de pronto (DoD final do projeto nesta rodada)

Só considerar a versão “funcional doméstica” quando:
- Em teste acompanhado no PC real, pelo menos cada um dos três filhos destrava a conta Filhos após Win+L simplesmente sentando na frente da webcam, sem clique ou senha.
- A autenticação do administrador segue convencional e intacta.
- Quota/saldo/horário são consultados antes do desbloqueio facial.
- O tempo desconta apenas do filho confirmado, e Win+L pausa contagem.
- Login por senha/PIN é permitido sem falsificar identidade do filho.
- O painel parental altera quotas e bônus refletidos nos processos ativos.
- Serviço e agente sobreviveram a reinício na forma especificada, ou limitações do cold boot foram declaradas.
- Testes automatizados Windows/Linux e build do CP real passam; resultado e links registrados.
- Instalador e desinstalador não matam outros processos nem deixam o Windows sem login normal.
- Documentação, README e scripts descrevem o comportamento efetivo.
- Nenhuma foto, nome de criança, embedding, banco real ou senha foi publicada como artifact.

Se qualquer item físico não foi executado, informar “implementado mas não validado em hardware” sem inventar sucesso. O objetivo da rodada NÃO é certificação de segurança, mas uma experiência doméstica confiável e recuperável.

---

## 16. Fonte de referência para auditoria futura

**GitHub / baseline**
- Repositório: https://github.com/marquimRcc/FaceControlKidsPC
- HEAD analisado: https://github.com/marquimRcc/FaceControlKidsPC/commit/ef7eed1f324a9994528517ab4d3708ddc4248399
- CI Python falhando (baseline): https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/39634262101
- CI CP diagnóstica verde (não cobre CP real): https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/39630304875
- docs/ADR-003-WINDOWS-REAL-FACE-UNLOCK.md (arquitetura anterior a reconciliar).
- docs/PROGRESSO-AUTONOMO.md (histórico dos protótipos antigos).

**Microsoft**
- Credential Providers in Windows: https://learn.microsoft.com/en-us/windows/win32/secauthn/credential-providers-in-windows
- GetCredentialCount/autologon: https://learn.microsoft.com/en-us/windows/win32/api/credentialprovider/nf-credentialprovider-icredentialprovider-getcredentialcount
- GetSerialization: https://learn.microsoft.com/en-us/windows/win32/api/credentialprovider/nf-credentialprovidercredential-getserialization
- Interactive Services / Session 0: https://learn.microsoft.com/en-us/windows/desktop/Services/interactive-services

**Nota de evolução:** os números P0-43..P0-55 constituem a fila desta proposta. Se outra IA já estiver alterando a branch, checar os novos commits antes de editar, manter histórico e não sobrescrever progresso existente.

---

# PROMPT PRONTO PARA A OUTRA IA (copiar e usar)

Você é a IA executora principal do projeto FaceControlKidsPC. Leia integralmente o arquivo docs/HANDOFF-EXECUCAO-AUTO-UNLOCK-OUTRA-IA-20261021.md na branch handoff/facekids-auto-unlock-stabilization-20261021 do repositório https://github.com/marquimRcc/FaceControlKidsPC. Implemente o plano P0-43 a P0-55 nessa mesma branch, em lotes de várias tarefas, criando testes, commits e verificando GitHub Actions antes de declarar cada etapa concluída. Avance sem pedir autorização a cada passo. NÃO faça merge na main. A prioridade é a criança sentar diante da webcam, ser reconhecida e DESBLOQUEAR AUTOMATICAMENTE a conta Windows Filhos sem clicar/digitar, com quotas individuais e painel parental. A conta administradora deve permanecer intacta. A senha local da conta Filhos é deliberadamente fixa como "1" neste PC doméstico; não gastar esta rodada tentando trocá-la ou redesenhar sua gestão. O login convencional permanece disponível por escolha do proprietário. Firewall/Internet/conteúdo ficam fora do escopo. Não minta sobre testes físicos; se a câmera/LogonUI real exigir participação do proprietário, forneça o teste preciso e continue o restante do desenvolvimento. Corrija regressões da CI, inclua build da DLL de login REAL, consolide o processo de autenticação e não use fallback de ID de criança. O revisor apenas acompanhará e analisará seus commits e provas. Trabalhe até onde as ferramentas permitirem no mesmo ciclo, priorizando entregas reais com documentação de resultado.
