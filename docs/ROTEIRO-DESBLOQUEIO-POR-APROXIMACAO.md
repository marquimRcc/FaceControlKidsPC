# Roteiro de desbloqueio facial automatico ao sentar

Objetivo do responsavel: acordar o Windows ao aproximar-se do
computador, reconhecer seu rosto e abrir sua sessao Windows SEM senha
digitada. Este objetivo e diferente da prova de conceito YuNet/SFace.

## Prioridade 1 — recursos nativos Windows

- Windows Hello Face: **exige camera compatível**, em geral camera
  infravermelha/IR. A webcam RGB usada no piloto Python nao comprova
  que Windows Hello pode autenticar o responsavel.
- Wake on Approach: exige sensor de presenca compativel. A funcao
  pode acordar a maquina ao aproximar-se; so acordar nao autentica.
- A combinacao, quando oferecida pelo equipamento e ativada pelo
  proprietario, e o primeiro caminho a validar para Windows 11.

Leia:
- https://support.microsoft.com/en-us/windows/security/configure-windows-hello
- https://www.microsoft.com/pt-br/windows/tips/presence-sensing

O script \`scripts/Diagnosticar-Hello-Presenca.ps1\` verifica as classes
Windows Camera/Image/Biometric/Sensor, lista nomes e estado, e consulta
Windows Biometric Service **somente leitura**. Nao conclui se o
equipamento suporta Hello: nomes PnP sao apenas indicios. O usuario
deve confirmar as duas opcoes nas Configuracoes Windows.

O comando \`-OpenSettings\` abre a pagina de opcoes de entrada sem
alterar qualquer opcao. Nao registrar Credential Provider no PC real.

## Prioridade 2 — software customizado, caso Windows Hello nao sirva

Separar em duas provas distintas:
1. Determinar se existe caminho de captura confiavel na tela de
   bloqueio com hardware real e liveness anti-replay minimamente
   resistente. A observacao Win+L em processo normal nao prova isto.
2. Autenticacao Windows segura no LogonUI: Credential Provider
   testado APENAS em VM com snapshot e conta administrativa de
   recuperacao. A demonstracao YuNet/SFace NAO fornece credencial
   Windows nem acesso automatico.

Nao ativar auto-unlock por proximidade enquanto falta confianca:
um sensor de presenca ou foto nao identifica uma pessoa. A conta
\`Filhos\` e as quotas permanecem independentes do piloto adulto.


## Teste pratico recomendado com a XWF-1080P, na conta MarcosMiniPC

Confirmado no Windows 11 Pro build 26300: configuracoes Hello dizem
"nao foi possivel encontrar uma camera compativel"; PnP mostra
Camera XWF-1080P sem dispositivos nas classes Biometric ou Sensor.
Isso bloqueia a rota atual Windows Hello nativa, embora nao impeça
provas de conceito de captura de frames em Win+L.

Apos atualizar a branch \`feature/parent-face-pilot\`, executar
\`scripts/Testar-Camera-WinL.ps1 -Duration 90\`. Pressionar Win+L
quando solicitado, aguardar 40-60 segundos e desbloquear com a
senha/PIN normal para conferir o resumo no PowerShell.

Resultado \`FRAMES_DURING_WIN_L_PRELIMINARY_ONLY\` significa apenas
frames nao uniformes atribuídos a amostras WTS de sessao bloqueada.
\`NO_USABLE_LOCKED_FRAMES\` e
\`INCONCLUSIVE_NOT_ENOUGH_LOCKED_SAMPLES\` nao significam que
o LoginUI foi testado ou que uma operacao de autenticacao ocorreu.

Este teste nao instala servico nem Credential Provider, nao
salva videos, nao altera senha e nao tenta desbloquear o Windows.


## Evidência física: reconhecimento durante Win+L (20/10/2026)

Piloto local confirmado voluntariamente com Windows 11 Pro build 26300
e webcam XWF-1080P usando a conta do responsável. Registro contém
SOMENTE estatísticas fornecidas pelo operador, sem fotos, nome ou
vetores faciais.

Resultado do script Testar-Reconhecimento-WinL.ps1:
- Testes unitários locais: 7 aprovados
- Amostras totais: 90
- Amostras WTS bloqueadas: 45
- Frames obtidos nas amostras bloqueadas: 45
- Frames com um único rosto: 45
- Correspondências com o cadastro adulto: 44 (97,8% **nessa amostra**)
- Sequências positivas de 3 frames: 8
- Erros de câmera: 0
- Estados WTS desconhecidos: 0
- Veredicto: MATCH_OBSERVED_DURING_WIN_L_DIAGNOSTIC_ONLY

Esse resultado documenta que o reconhecedor YuNet/SFace que roda
no processo da sessão de usuário identificou vetores semelhantes
ao modelo cadastrado enquanto WTS reportava LOCKED. Não demonstra
funcionamento no Secure Desktop, prova de liveness, proteção contra
foto/replay, disponibilidade ao iniciar o computador, nem desbloqueio
autenticado de uma conta Windows. A porcentagem observada não é
métrica de precisão biométrica ou taxa de falso aceite.

### Próxima barreira: autenticação Windows em VM recuperável

O Credential Provider deste projeto ainda é estritamente
diagnóstico: GetSerialization não produz credenciais e não
pode desbloquear o Windows. Mesmo o resultado físico positivo não
autoriza registrar o Provider no computador da família.

O CI passa a validar também a DLL real de distribuição sem registro
COM, exigindo ausência de exports exclusivos dos autotestes e
nenhum tile de login quando o sistema não fornece usuário vinculado.
Testes não verificam LogonUI real. São apenas regressões negativas.

Antes de considerar um Provider realmente autenticante, exigir:
1. VM Windows com console do hipervisor, snapshot testado e conta
   administrativa alternativa recuperável.
2. Contrato de identidade baseado em token do SO e sessão, não
   identificadores fornecidos por cliente Python.
3. Worker de captura confiável, política de liveness e resistência a
   replay validadas com a câmera e cenário físico.
4. Estratégia segura de credenciais por mecanismo suportado pelo SO:
   uma correspondência facial comum não equivale a credencial Windows.
5. Ensaios de rollback após falhas no LogonUI. Nunca eliminar as
   opções padrão de autenticação e recuperação.
