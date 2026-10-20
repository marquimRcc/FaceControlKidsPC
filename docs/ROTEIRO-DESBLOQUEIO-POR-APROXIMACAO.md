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
