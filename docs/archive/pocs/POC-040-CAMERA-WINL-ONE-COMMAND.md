# P0-40 — Teste de webcam em um so comando no Windows

O script \`scripts/Testar-Camera-WinL.ps1\` verifica a branch, prepara
um ambiente Python privado na pasta do projeto caso esteja ausente,
executa os testes WTS de diagnostico e abre uma captura temporaria
que so acumula contadores de frames e estado LOCKED.

**Sem fotos nem modelos armazenados.** Ele nao modifica registro,
Winlogon, senhas, usuarios ou a configuracao de servicos Windows.
Nenhuma DLL do Credential Provider e instalada.

Na conta Windows em que deseja testar a webcam e com o projeto
ja clonado, em um PowerShell normal:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\Testar-Camera-WinL.ps1"

Pressione Win+L durante o teste e aguarde o prazo padrao de 120 segundos;
depois desbloqueie normalmente. Opcionalmente use
\`-Duration 60\` e \`-CameraIndex 1\`.

O resultado \`FRAMES_DURING_WIN_L_PRELIMINARY_ONLY\` apenas prova
captura de frames naquela sessao bloqueada e naquele processo,
nao prova identificacao facial, liveness ou Secure Desktop.
Nao execute o script no GitHub Actions; CI testa os contadores
com amostras sinteticas sem webcam fisica.

A conta Filhos deve executar o teste em seu proprio clone do repositorio
caso nao tenha acesso ao projeto na pasta da conta administrativa.
Nao modificar permissoes de pastas administrativas para facilitar
o acesso pela conta Filhos.
