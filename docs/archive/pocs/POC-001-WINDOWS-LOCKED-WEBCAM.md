# PoC P0-1 — Webcam com o Windows bloqueado (Win+L)

**Branch:** feature/windows-native-unlock-poc  
**Status:** diagnóstico implementado; **ainda não validado com webcam em Windows real**.

## Objetivo

A ADR-003 estabelece a primeira incerteza bloqueadora: um processo de captura
consegue ler frames **enquanto a conta Filhos permanece na tela de bloqueio nativa**?

Este utilitário investiga essa pergunta sem instalar Credential Providers,
sem alterar registro Windows e sem acessar qualquer senha.

## Como executar no PC Windows 10/11

1. Entre na conta comum **Filhos** normalmente.
2. Confirme que a webcam funciona em outros aplicativos e feche-os.
3. Abra um PowerShell na pasta do projeto e instale as dependências:
   \`\`\`powershell
   py -3.11 -m venv .venv
   .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
   \`\`\`
4. Inicie o teste por 120 segundos:
   \`\`\`powershell
   .\\.venv\\Scripts\\python.exe -m facekids.windows_lock_probe --duration 120
   \`\`\`
5. **Pressione Win+L manualmente**, deixe a tela bloqueada por 30–60 s e
   faça login normalmente usando a senha da conta.
6. Espere o diagnóstico concluir e verifique seu CSV no caminho exibido.

Também é possível experimentar \`--backend msmf\` e \`--camera 1\`, dependendo da webcam.
Teste **dshow**, **msmf** e **any** separadamente se houver falhas.

## O que o CSV mostra?

- \`session\` obtido pela API WTS: \`active\`, \`locked\` ou \`unknown\`.
- \`capture_ok\`: se a chamada \`VideoCapture.read()\` respondeu.
- \`frame_nonuniform\`: verificação rudimentar de variância luminosa.
- Somente timestamp relativo, dimensões, média e desvio-padrão de brilho.
- Erros pelo tipo, sem texto de driver, senhas, identidade ou caminho pessoal.

**Não grava vídeo, fotografias, biometria, rostos ou áudio.**
O CSV fica em \`%LOCALAPPDATA%\\FaceKids\\diagnostics\\\` e **não deve ser commitado**.

## Critério mínimo

\`CAMERA_READS_DURING_LOCK\` exige pelo menos cinco amostras reportadas como
\`locked\` pelo WTS e três frames não uniformes durante o período bloqueado.

Isso é uma **indicação preliminar**, não prova reconhecimento viável no
LogonUI. A câmera pode capturar frames sem haver acesso adequado ao processamento
facial ou à autenticação. \`INCONCLUSIVE\` não significa incompatibilidade, apenas
que a medição não estabeleceu o estado esperado.

Se não houver frames sob bloqueio, investigar os backends de webcam e as
restrições de sessão, sem tentar contornar a tela segura do Windows.

## Próxima prova

P0-2: DLL COM de Credential Provider, inicialmente com **zero credenciais
emitidas**, apenas para validar interfaces e toolchain em ambiente de teste.
Não ativar desbloqueio real antes de P0-1, P0-2, IPC protegido e recuperação.
