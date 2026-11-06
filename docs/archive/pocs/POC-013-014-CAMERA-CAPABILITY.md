# P0-13/14 — Diagnostico de camera no broker Windows

Status: compilado e aprovado em GitHub Actions. Nao houve teste com
webcam fisica no desktop seguro LogonUI do usuario.

## P0-13: inventario local

camera_capability.h usa Media Foundation (MFStartup e
MFEnumDeviceSources) para descobrir cameras no proprio processo.
Nenhuma imagem e aberta, enviada ou gravada no disco.

Quatro classificacoes internas: NO_CAMERA, CAMERA_ENUMERATED_NOT_VERIFIED,
MF_UNAVAILABLE e UNKNOWN. Nenhuma habilita autenticacao: a API
usable_for_authentication() devolve falso em todos os estados.

O diagnostico FaceKidsBrokerPoc.exe --camera-capability apenas informa
o estado atual do dispositivo e nunca consulta informacoes biometricas.

## P0-14: inventario consultado no servico LocalSystem

Durante o startup SCM, o broker obtem e guarda o inventario de camera
em memoria. O comando local CAM? apenas retorna CAMERA_NONE,
CAMERA_ENUMERATED ou CAMERA_UNAVAILABLE. O pipe exige usuario SYSTEM
ou administrador elevado (DACL do broker) e nao permite fornecer
SID, camera index, comandos de captura, caminho de arquivo ou rosto.

O executavel FaceKidsBrokerPoc.exe --camera-status consulta o broker,
e o CI Windows exercita essa operacao tanto no host isolado quanto
no SCM LocalSystem, antes de remover o servico descartavel.

## Limites reais

Cameras enumeradas podem falhar ao abrir; um frame nao uniforme
nao e prova de pessoa viva nem rosto valido. Ainda nao se testou
a captura num LogonUI real, nem liveness ativo ou reconhecimento
de crianca sob uma origem protegida. O comando nao altera quota,
nao registra Credential Provider e nao concede desbloqueio.

Proximo: estabelecer um worker de captura confiavel e testes em
hardware real e VM com recuperacao, antes de qualquer logon.
