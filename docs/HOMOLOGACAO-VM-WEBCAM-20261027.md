# Homologação da webcam na VM — 27/10/2026

## Escopo e ambiente

- Host: Windows, Oracle VirtualBox 7.2.22 r175245.
- Extension Pack: 7.2.22, compatível com o VirtualBox instalado.
- VM descartável: `Windows 10 Pro`, usuário administrativo `Marcos`.
- Webcam USB: XWF-1080P, VID `1bcf`, PID `2281`.
- Código: branch `developer`; a branch `main` não foi alterada.
- Dados faciais e SQLite: `%LOCALAPPDATA%\FaceKids-VM-Lab\dados-isolados`.

O ensaio usou o rosto consentido de um adulto como perfil fictício. Nenhuma
foto ou vídeo foi incluído no repositório.

## Causa confirmada e correção do VirtualBox

A webcam estava capturada pela VM, mas a configuração tinha somente o
controlador USB 1.1 ativo (`usb=on`, `ehci=off`, `xhci=off`). A XWF-1080P é um
dispositivo USB 2.0 High Speed. Essa incompatibilidade explicava o diagnóstico
DirectShow `CAMERA_GUEST_INTERACTIVE=UNAVAILABLE` observado anteriormente.

Com a VM desligada, o controlador xHCI foi habilitado. Depois do reinício, o
VirtualBox confirmou `xhci=on` e a câmera continuou anexada à VM. Não foi
necessário trocar `opencv-python` por `opencv-contrib-python`.

## Evidência observada no Windows convidado

1. O aplicativo Câmera do Windows exibiu vídeo ao vivo da XWF-1080P.
2. O Painel dos Pais abriu na `developer` usando o banco isolado.
3. `Cadastrar com Webcam` concluiu 12 amostras do perfil fictício `Teste`.
4. O preview de reconhecimento identificou o perfil e exibiu
   `Acesso visual autorizado`, com saldo individual de `01:59:53`.
5. O primeiro quadro apareceu como desconhecido e convergiu para reconhecido
   após novas amostras; não houve falha de abertura ou perda da câmera.

Esse resultado comprova captura, cadastro e reconhecimento na sessão
interativa. Ele não comprova captura em Session 0, LogonUI, liveness ou
desbloqueio nativo do Windows.

## Isolamento corrigido na `developer`

O preview de webcam usava `storage.default_data_path()` e podia ignorar o
opt-in `FACEKIDS_VM_LAB_DIR`, enquanto o painel usava o banco isolado. A função
agora respeita o mesmo diretório quando `FACEKIDS_VM_LAB_ACK=ISOLATED_VM_ONLY`.
Um teste impede regressão desse caminho.

Também foi removida a suposição ativa de exatamente três crianças no piloto:
o engine usa todos os perfis explicitamente cadastrados, aceita um ou mais e
o menu permite criar e selecionar qualquer ID positivo. O provisionamento de
três pseudônimos permanece apenas como fixture legada de testes.

Validação local no host: 470 testes aprovados, 13 ignorados; parser do script
PowerShell aprovado; `git diff --check` sem erros.

## Snapshots e restauração comprovada

- `pre-homologacao-webcam-2026-10-27`
  (`c306a963-2d6f-4248-8126-392133c50c70`): criado antes do cadastro e de
  qualquer ensaio futuro de SCM, LogonUI ou Credential Provider.
- `post-webcam-enrollment-2026-10-27`
  (`224647e6-a7bc-40f4-8870-90219ee0273a`): contém xHCI, ambiente isolado,
  atalhos de laboratório e o perfil fictício com 12 amostras.

O snapshot anterior foi restaurado, inicializou até o desktop administrativo
e manteve xHCI/câmera anexada. Em seguida, o snapshot posterior foi restaurado,
inicializou normalmente e o painel voltou a mostrar o perfil `Teste`, 12
amostras e duas horas de quota. A VM ficou no snapshot posterior.

## Portões ainda abertos

- Testar ausência, múltiplas faces e replay/liveness com critérios reais.
- Criar/usar uma conta Windows padrão `Filhos` para ensaios de sessão.
- Testar Win+L e captura durante bloqueio sem alterar credenciais.
- Comprovar ou rejeitar captura em Session 0 antes de escolher a arquitetura.
- Homologar serviço SCM, IPC, ACL e agente read-only em fixture protegida.
- Somente depois avaliar Credential Provider dentro da VM, preservando login
  administrativo convencional e os dois snapshots de recuperação.

Nenhum serviço SCM, tarefa agendada, Credential Provider, senha, login ou
componente de inicialização foi instalado ou alterado nesta etapa.
