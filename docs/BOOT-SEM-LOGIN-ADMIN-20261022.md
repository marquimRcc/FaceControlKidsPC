# FaceKids: ligar o PC e reconhecer sem login previo do administrador

Branch: `feature/facekids-cold-boot-auto-unlock-20261022`.
Base preservada e publicada: `939bf0b6cbeb36bc86a8720fb8d0b32ee2004801`.

## Decisao do proprietario

Prioridade: funcionar no PC domestico dedicado aos filhos. Nao exigir a abertura
da conta administrativa apos cada reinicializacao. A senha da conta `Filhos`
continua `1`; reconhecimento individual, quotas e horarios continuam sendo
aplicados pelo autenticador existente. Firewall/conteudo sao outro projeto.
Nao configurar AutoAdminLogon nem entrar silenciosamente na conta administrativa.

## Implementacao deste lote

- `FaceKidsBootAuth`: tarefa `AtStartup`, principal `SYSTEM/ServiceAccount`,
  independente de senha/logon interativo, sem limite de duracao da tarefa e sem
  instancias paralelas. Ativacao por script separado, nao automatica no PC.
- `facekids.boot_auth`: supervisor inicia o autenticador Python existente, tenta
  DirectShow e Media Foundation alternadamente e repete a cada 5 segundos quando
  um worker falha. Limite de inicializacao: 30 s por processo; requisicao parada:
  15 s. Um pipe ocioso nao e considerado falha.
- Se uma chamada nativa da camera ou do pipe travar, o supervisor termina apenas
  o subprocesso que ele criou. A morte desse processo fecha seus handles.
- O worker verifica o mutex ANTES de tocar na camera; fecha-o explicitamente em
  todas as saidas. Se ja existe instancia interativa funcional, nao abre outra
  camera e nao encerra essa instancia. O supervisor volta a tentar depois.
- Em SYSTEM, a sondagem usa o MESMO backend e API que o reconhecimento real.
  Nao se infere sucesso do OpenCV a partir de um diagnostico de outra API.
- Assinaturas ctypes completas de entrada e saida impedem truncamento de HANDLE
  em 64 bits, tanto no servidor quanto no agente da sessao.
- Credential Provider: repete reconhecimento sem clique apos rosto ausente,
  desconhecido, quota/horario negado ou servico ainda iniciando. A repeticao roda
  em worker, com intervalo de 1 s entre chamadas, enquanto a tile esta ativa.
  Ao deselecionar/UnAdvise, rejeita a resposta pendente da ativacao anterior.
  Nenhuma repeticao ignora o resultado facial nem as regras de tempo.
- Mantem a tarefa interativa anterior e o login Windows convencional. O
  desinstalador para/remove a tarefa de boot ANTES de encerrar workers.
- O instalador e o ativador exigem a DLL com `FACEKIDS_IPC_V1` e
  `FACEKIDS_BOOT_RETRY_V1`, evitando usar o binario anterior sem repeticao.
- Binarios distribuidos incorporam os runtimes GCC/C++; nao dependem de
  `libgcc_s_seh-1.dll`, `libstdc++-6.dll` ou `libwinpthread-1.dll` no PATH do
  LogonUI. A CI verifica o carregamento com PATH restrito ao Windows.

## Ativacao no Windows

Somente depois do build/testes da branch e da sincronizacao dos binarios:

```powershell
git fetch origin
git switch feature/facekids-cold-boot-auto-unlock-20261022
git pull --ff-only origin feature/facekids-cold-boot-auto-unlock-20261022
powershell -ExecutionPolicy Bypass -File .\scripts\Instalar-FaceKids-Nativo.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\Ativar-Desbloqueio-No-Boot.ps1
```

Executar os scripts como administrador. Os modelos ONNX, Python `.venv`, banco
compartilhado ja cadastrado e Credential Provider devem existir. O ativador
interrompe se faltarem arquivos; nao cria um banco vazio sob a conta SYSTEM.
O instalador pode exigir fechar o LogonUI/reiniciar para substituir uma DLL
carregada. Nunca interpretar falha de copia/registro como atualizacao concluida.

Reiniciar MANUALMENTE. Nao entrar no administrador. Aguardar o carregamento do
Windows/webcam, exibir a opcao FaceKids da conta Filhos se o Windows mostrar
outra opcao e apresentar o rosto cadastrado. A selecao inicial de usuario/tile
depende do LogonUI; a CI nao comprova selecao automatica dessa opcao no PC.

Sucesso significa chegar ao desktop de `Filhos`, com a crianca correta e seu
saldo. Uma camera aberta ou uma resposta `ALLOW` sozinha NAO comprova login.

## Evidencias e verificacao

- `C:\ProgramData\FaceKids\boot_status.json`: estado atual, tentativa,
  backend, PID do supervisor/worker, timeout/exit code quando aplicavel.
- `C:\ProgramData\FaceKids\boot_events.jsonl`: eventos `camera_ready` e
  `allow`, timestamp, backend, sessao do worker e quantidade de usuarios com
  sessao WTS. `logged_on_users = 0` e `session_id = 0` registram evidencia de
  funcionamento antes de um logon interativo. `null` significa leitura WTS
  inconclusiva, nunca prova de ausencia de login. Nao grava fotos, vetores,
  nomes das criancas, senhas ou nomes dos usuarios nesse relatorio.
- `auth_service.log` e `provider_debug.log`: diagnostico dos componentes.

Testar: primeiro boot sem admin; sair e entrar por PIN; `Win+L`; tres filhos;
quota zerada/horario negado; camera desconectada e reconectada; nova
reinicializacao. Quando indisponivel, continuar entrando normalmente por
senha/PIN; o controle por firewall permanece independente.

Se a camera nao fornecer frames em nenhum backend em SYSTEM, esse caminho
nao esta validado para o driver. Retentativas nao tornam um dispositivo
incompativel em compativel. Registrar os logs para decidir a proxima adaptacao;
nao declarar resolvido ou instalar silenciosamente outro mecanismo de logon.

## Voltar ao comportamento anterior

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Ativar-Desbloqueio-No-Boot.ps1 -Desativar
```

Remove somente a tarefa de boot. Mantem cadastros, banco, fotos e inicializacao
interativa. O desinstalador completo tambem remove a tarefa de boot.

## Validacao automatizada

- Testes Python simulam driver travado, reinicio por PID exato, alternancia de
  backends, espera ociosa, mutex duplicado e liberacao apos camera indisponivel.
- O job Windows exercita servidor/cliente Named Pipe reais, com resposta facial
  simulada, sem camera, autenticacao do Windows ou alteracoes de instalacao.
- `TestCredentialRetry.exe` exercita o worker C++ real contra um pipe simulado:
  primeira negativa seguida de ALLOW sem clique; ALLOW atrasado apos deselecao
  e descartado; referencias do worker liberadas apos UnAdvise.
- AST PowerShell verificado pelo job Windows. A CI nunca instala tarefas nem
  registra o Credential Provider. Instalacao fisica e webcam continuam pendentes
  ate teste no PC do proprietario.
