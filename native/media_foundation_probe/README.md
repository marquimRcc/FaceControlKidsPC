# P0-1B — Diagnóstico nativo de webcam Media Foundation

O WinFace demonstra como capturar frames com Windows Media Foundation no
contexto do Credential Provider. Antes de usar essas APIs no LogonUI, precisamos
validar captura **durante Win+L** com um executável pequeno e não privilegiado.

Este utilitário C++17 roda dentro da conta Filhos como um programa comum,
sem alterar credenciais, sem instalar drivers, sem registrar Credential Provider
e sem bloquear ou desbloquear Windows por conta própria.

## Rodar sem instalar Python

No GitHub Actions da branch, abra o workflow Native Media Foundation webcam PoC,
baixe o artifact FaceKidsMFProbe-windows-x64 e descompacte.

1. Faça login na conta Filhos e feche programas usando a webcam.
2. Execute FaceKidsMFProbe.exe 120 0 em um terminal aberto nessa pasta.
3. Pressione Win+L manualmente e mantenha a sessão bloqueada por 30 a 60 s.
4. Desbloqueie normalmente, espere a medição terminar.
5. Consulte FaceKids-MediaFoundation-WinL.csv no mesmo diretório.

O primeiro argumento é a duração (segundos, entre 10 e 600);
o segundo é índice da câmera (0, 1 etc.). Se o formato RGB32 não for
suportado pelo driver/conversor, o diagnóstico falhará explicitamente.

O CSV registra somente estado WTS, existência de frames, brilho médio,
desvio-padrão e HRESULT numérico; não grava imagem, vídeo ou reconhecimento.
Três frames não uniformes durante lock são **evidência preliminar** da
captação, não garantia de funcionamento dentro de LogonUI.

## Compilar manualmente

Em Developer PowerShell x64 com Visual Studio C++ e Windows SDK:

    cl /nologo /std:c++17 /EHsc /W4 native\media_foundation_probe\probe.cpp /link /OUT:FaceKidsMFProbe.exe

A compilação também é executada automaticamente no GitHub Actions.
A prova anterior P0-1 (Python/OpenCV com DSHOW/MSMF) continua disponível;
comparar os dois relatórios e não assumir equivalência entre backends.

**Não executar esse diagnóstico em uma sessão sem possibilidade de login
normal.** Nenhuma alteração de autenticação é efetuada.
