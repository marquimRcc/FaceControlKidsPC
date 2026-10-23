# Continuidade do trabalho no Regata OS

> Documento de passagem para outra IA ou para uma nova janela de trabalho.
> Deve ser atualizado e commitado nesta branch imediatamente antes de toda
> pausa planejada, incluindo pausas por limite de uso.

## Estado de referência

- Data da atualização: 23/10/2026, fuso `America/Sao_Paulo`.
- Repositório: `marquimRcc/FaceControlKidsPC`.
- Branch: `feature/regataos-linux-implementation-20261022`.
- Base do trabalho Linux: `research/regataos-linux-20261022`.
- Pull request draft: <https://github.com/marquimRcc/FaceControlKidsPC/pull/3>.
- Último commit funcional local e remoto: `69e119a`.
- Ambiente observado: Regata OS 26, KDE Plasma 6.6.5, X11 e Python 3.13.

## Regra de continuidade autônoma

Este trabalho deve continuar sem aguardar novas mensagens como `continue` ou
`avance`. A automação `continuar-facekids-regata-os` permanece ativa neste
chat e dispara a cada dez minutos enquanto houver cota. A cota da janela de
cinco horas deve ser consultada durante o trabalho.
Quando restarem 8% ou menos, atualizar e commitar este documento, enviar os
commits à branch e pausar. A retomada deve ocorrer automaticamente três minutos
depois do horário exato de renovação da cota. Atualizações rotineiras ficam em
silêncio; somente bloqueios que exijam ação humana devem ser comunicados.

## Objetivo do produto no Linux

O FaceKids deve controlar uma conta Linux compartilhada por uma ou mais
crianças. O rosto presente determina qual quota individual é debitada. A contagem ocorre
somente enquanto a sessão está ativa e desbloqueada. O sistema bloqueia a
sessão quando a quota termina, o horário permitido acaba ou a identidade fica
incerta além da tolerância. Reconhecimento e dados permanecem locais.

O responsável mantém uma conta administrativa separada, controla cadastro,
limites, bônus e horário, e sempre conserva um caminho de recuperação por
senha. Alterações no PAM são opcionais, explícitas e reversíveis.

## Arquitetura definida

```text
Webcam V4L2 (/dev/video0)
          |
          v
Serviço root facekids-linux.service
  - captura e rejeição de quadros inválidos
  - YuNet: detecção de exatamente um rosto
  - SFace: vetor e comparação local
  - ChildQuotaEngine: uma ou mais identidades, quota e tempo monotônico
  - SQLite protegido em /var/lib/facekids
          |
          +--> systemd-logind: estado Active/State/LockedHint
          +--> loginctl lock-session: bloqueio da sessão correta
          +--> socket root /run/facekids/auth.sock
                    |
                    v
            helper PAM opcional
            - ticket ligado à sessão
            - uso único, validade de 10 s
            - quota e horário revalidados no consumo
            - senha continua disponível como fallback
```

### Interface compartilhada definida em 23/10/2026

- Monorepo `pnpm` com React + TypeScript compartilhado e Electron no desktop.
- `apps/desktop`: composição dos papéis administrativo e infantil, main e
  preload Electron.
- `packages/admin`: painel e fluxo de cadastro.
- `packages/ui`: componentes compartilhados.
- `packages/contracts`: esquemas Zod e tipos das mensagens.
- O renderer está isolado, sem Node.js e sem acesso direto ao SQLite. O serviço
  Python permanece autoridade sobre biometria, quota e sessão.
- Integração planejada por socket Unix autenticado no Linux e named pipe com
  ACL no Windows. A interface móvel será uma etapa posterior, com API opt-in e
  pareamento explícito.
- A decisão completa está em `docs/ARQUITETURA-INTERFACE-DESKTOP.md`.

## Interface implementada em 23/10/2026

O commit `17365bb` adicionou o primeiro protótipo navegável do painel dos pais
e da tela de boas-vindas infantil. O painel lista quantidade variável de
perfis, saldo, limite, amostras e bônus; inclui rotina, atividade e cadastro em
três etapas. O cadastro impede avançar sem nome e sem completar 12 amostras
simuladas. A tela infantil mostra identidade reconhecida, saldo, horário e
próximo aviso. Há layout responsivo e alternador de papéis no navegador.

O protótipo usa dados de demonstração e ainda não persiste operações. Isso é
intencional: a API privilegiada será ligada somente após definir autorização e
contratos de erro. O Electron foi configurado com `contextIsolation`, sandbox,
`nodeIntegration: false`, navegação bloqueada, CSP e preload mínimo.

Validações executadas:

- `pnpm typecheck`: aprovado nos quatro pacotes.
- `pnpm test:ui`: 2 testes de contratos aprovados.
- `pnpm build`: build Vite e Electron TypeScript aprovado.
- Fluxo visual no navegador: painel, cadastro completo com 12 amostras e tela
  infantil revisados.
- Smoke test do Electron: iniciou por oito segundos sem erro da aplicação; a
  mensagem `hybrid_drv_video.so init failed` é do driver VA-API e não impediu a
  janela. O processo foi encerrado pelo timeout esperado.
- Suite Python completa: 211 testes aprovados, 2 ignorados por dependerem do
  Windows.

Pendências específicas da interface:

1. Definir comandos e respostas reais em `packages/contracts`.
2. Implementar cliente do socket Unix e autorização de cada operação.
3. Substituir o snapshot de demonstração por leitura do serviço.
4. Ligar cadastro, quota, bônus e horários ao backend e tratar indisponibilidade.
5. Criar empacotamento e inicialização integrada ao instalador do Regata OS.
6. Validar a janela Electron no monitor real em resolução desktop e na conta
   `filhos` depois que a integração estiver operacional.

O serviço protegido é a autoridade única. A conta infantil não informa sua
identidade nem escreve quota, vetores ou tickets. A mesma captura que reconhece
a criança alimenta a decisão de cobrança, evitando confiar em IPC controlado
pela sessão compartilhada.

### Componentes principais

- `facekids/linux_runtime.py`: ciclo de captura, reconhecimento, cobrança,
  bloqueio e servidor de autorização.
- `facekids/session.py`: descoberta da sessão gráfica e interpretação
  conservadora do estado publicado pelo logind.
- `facekids/linux_auth.py`: confirmações e tickets faciais efêmeros.
- `facekids/linux_pam_helper.py`: cliente mínimo do socket protegido.
- `facekids/linux_admin.py`: operações administrativas e cadastro.
- `facekids/linux_probe.py`: diagnóstico de câmera sem biometria.
- `facekids/platform_paths.py`: caminhos corretos por plataforma.
- `packaging/facekids-linux.service`: execução como root e endurecimento do
  serviço systemd.
- `scripts/*RegataOS.sh`: criação da conta, instalação, remoção e ativação ou
  recuperação do PAM.

## Princípios e boas práticas adotados

1. **Falhar de forma fechada.** Estado de sessão ausente, relógio inválido,
   câmera sem imagem, rosto múltiplo ou identidade incerta nunca autorizam nem
   debitam uma criança arbitrária.
2. **Menor privilégio.** Somente o serviço root escreve o banco e emite
   autorização. O socket usa modo `0600` e valida `SO_PEERCRED` com UID zero.
3. **Decisão no servidor.** Identidade, quota, horário e sessão são verificados
   pelo processo protegido, inclusive novamente no consumo do ticket.
4. **Biometria local e mínima.** O cadastro persiste vetores, sem guardar fotos
   ou transmitir imagens.
5. **Tempo monotônico.** O débito de uso não depende de alterações no relógio
   civil; a data civil é usada apenas para a quota diária.
6. **Recuperação antes de integração.** O instalador não inicia o serviço sem
   cadastro e não altera PAM. A ativação PAM possui backup e script de retorno.
7. **Senha preservada.** A integração facial complementa o desbloqueio; não
   remove as credenciais convencionais.
8. **Mudanças pequenas e verificáveis.** Cada correção recebe teste relevante,
   suíte completa e CI nas plataformas afetadas.
9. **Sem artefatos locais no Git.** `.venv`, modelos, ferramentas extraídas,
   banco, fotos e diagnósticos permanecem ignorados.
10. **Não contornar hardware ruim.** Quadros pretos ou uniformes são recusados;
    limiares não devem ser enfraquecidos para fazer o teste parecer aprovado.

## Planejamento técnico

### Fase 1 — análise e escolha da integração

Concluída. Foram avaliados os repositórios e a base existente, o Regata OS, o
KDE/SDDM, logind, câmera V4L2 e as diferenças em relação ao Credential Provider
do Windows. A opção escolhida foi um serviço root com logind e uma ponte PAM
opt-in, deixando uma integração gráfica específica para etapa posterior.

### Fase 2 — núcleo Linux protegido

Concluída em software. Inclui sessão, captura, reconhecimento, quotas, horário,
bloqueio, administração, modelos verificados por SHA-256 e armazenamento root.

### Fase 3 — empacotamento e recuperação

Concluída em software. Inclui unidade systemd endurecida, scripts de conta,
instalação e remoção, wrappers e ativação/desativação reversível do PAM.

### Fase 4 — verificação automatizada

Concluída para o estado atual. A suíte local passou com 211 testes, dois
ignorados por dependerem de Windows real. Os workflows `Unit tests` passaram
em Ubuntu e Windows, e `Linux Regata OS checks` passou (todos os 4 jobs com
status success no commit remoto 78bd46e). Os scripts passaram em `bash -n`,
os novos módulos Linux passaram no Ruff e as diretivas de serviço systemd foram
validadas com `systemd-analyze verify`.

### Fase 5 — validação física e experiência sem clique

Avançada. A webcam real passou no probe com detecções faciais confirmadas,
o perfil da criança 1 foi cadastrado localmente com sucesso, e o serviço
`facekids-linux.service` foi habilitado e iniciado com status ativo/running
sob o isolamento systemd (`User=root`, `UMask=0077`, `RuntimeDirectory=0700`,
sem sockets IP ou privilégios extras). O próximo passo é efetuar login na
conta `filhos` e validar o reconhecimento em sessão gráfica ativa, o débito
monotônico da quota e o desbloqueio automático do KScreenLocker pelo logind.

## Trabalho realizado

- Criadas as branches de pesquisa e implementação.
- Implementado runtime Linux para uma conta compartilhada e quantidade
  variável de perfis.
- A conta compartilhada `filhos` foi criada sem grupos suplementares ou acesso
  direto à webcam; o serviço `facekids-linux.service` foi instalado e iniciado.
- O perfil da criança 1 foi cadastrado com sucesso presencialmente via
  `facekids-admin enroll 1`.
- O instalador aceita de uma a vinte crianças e usa uma quando a quantidade é
  omitida; o runtime não contém mais a exigência fixa de três perfis.
- Implementada descoberta de sessão por logind e bloqueio dirigido por ID.
- Implementadas quotas individuais, bônus e toque de recolher.
- Implementado cadastro local sem persistência de fotos.
- Implementado download atômico dos modelos oficiais YuNet/SFace com hashes.
- Implementada recusa de quadros pretos ou sem contraste.
- Implementado broker de aprovação com três confirmações, ticket de uso único
  e revalidação de quota e horário.
- Implementado desbloqueio direto e limitado por sessão via `loginctl`, com
  revalidação, intervalo mínimo entre pedidos e fallback PAM preservado.
- Implementado recarregamento de cadastros durante a execução; alteração ou
  remoção revoga evidência e tickets anteriores.
- Falhas transitórias do logind ao bloquear são contidas e limitadas a uma
  tentativa a cada dez segundos, sem derrubar o controlador nem abrir acesso.
- A preparação da conta infantil remove e verifica todos os grupos
  suplementares, cobrindo também privilégios indiretos como `docker` e
  `libvirt`, além de `wheel` e `video`.
- Os comandos reversíveis de ativação e recuperação PAM são instalados em
  `/usr/local/sbin`, para não depender da permanência do checkout do Git.
- Erros de leitura ou bloqueio do SQLite durante a revalidação de um ticket
  negam o desbloqueio de forma fechada, sem encerrar o serviço principal.
- Implementado isolamento de motivos de bloqueio (`determine_lock_state`),
  corrigindo o problema de registro onde a exaustão de quota herdava
  indevidamente o motivo do horário permitido (`Dentro do horário permitido`),
  garantindo que o journal registre `quota esgotada`.
- Falhas de solicitação de desbloqueio pelo logind (`_maybe_unlock`) agora
  capturam `RuntimeError` e são limitadas a uma tentativa a cada dez segundos,
  evitando repetição contínua em loop.
- O método `close()` do runtime finaliza de forma limpa a thread servidora de
  autorização e remove o arquivo de socket em `/run/facekids/auth.sock`.
- Corrigida a permissão de instalação dos modelos ONNX (`0644`), permitindo que
  o diagnóstico `facekids-linux-probe` leia os modelos sem privilégios de root.
- Implementada ponte PAM opcional, com backup e restauração.
- Criados instalador, desinstalador, criador da conta infantil e wrappers.
- Corrigidos caminhos Windows que criavam `C:` acidentalmente no Linux.
- Criados testes Linux e workflow dedicado; corrigida portabilidade do mock de
  `AF_UNIX` no runner Windows.
- Criado o PR draft 3 com a implementação.

## Evidência e limitações conhecidas

- `/dev/video0` foi identificado como `USB 2.0 Camera` e anuncia YUYV
  640x480 a 30 fps.
- `/dev/video1` é um nó de metadados e não serve para captura.
- A conta atual pertence ao grupo `video`.
- Após descartar 15 quadros para estabilizar a autoexposição, o probe real
  retornou `CAMERA_UTILIZAVEL`: no segundo teste em 22/10/2026 (22:24), registrou
  30/30 quadros utilizáveis, 5,95 fps, brilho médio de 87,07 e 8 detecções
  faciais confirmadas na câmera.
- A conta `filhos` e os arquivos de sistema em `/usr/lib/facekids` e
  `/var/lib/facekids` foram instalados pelo responsável.
- A instalação do sistema exige `sudo` interativo; a sessão automatizada não
  possui a senha do responsável.
- O helper PAM atende uma conversa de autenticação já iniciada. O runtime agora
  também solicita desbloqueio direto pelo logind, mas o comportamento sem
  clique ainda precisa ser comprovado fisicamente no KDE desta máquina.
- O PR aparece como draft e deve continuar assim até a validação física e a
  revisão final de segurança.

## O que falta fazer

1. Entrar na sessão gráfica da conta compartilhada `filhos` e verificar se o
   serviço reconhece o rosto cadastrado e inicia o débito da quota diária.
2. Testar bloqueio por ausência ou tempo esgotado e comprovar se o logind
   desbloqueia automaticamente sem clique quando o rosto reaparecer.
3. Testar a senha de recuperação da conta `filhos` e a administração pela conta
   `marcos` (ajuste de limite, concessão de bônus e consulta de status).
4. Testar toque de recolher e virada de dia civil.
5. Avaliar aviso sonoro ou notificação segura na sessão ativa antes do bloqueio
   (ex.: aviso prévio de 15 segundos antes de travar a tela).
6. Somente depois de homologado o desbloqueio por aproximação, testar a ponte
   PAM opt-in (`facekids-enable-pam`) e seu retorno (`facekids-disable-pam`).
7. Fazer revisão final do PR draft #3 e preparar o merge para a branch principal.

## Próximos passos recomendados para outra IA

1. Ler este arquivo e `docs/IMPLEMENTACAO-REGATAOS-LINUX.md`.
2. Confirmar branch, árvore limpa, commits locais e cabeça remota. O Git do
   sistema não estava instalado; o binário extraído está em
   `./.local-tools/git/usr/bin/git` e `.local-tools/` está no exclude local.
3. Consultar o estado do PR 3 e dos workflows antes de modificar código.
4. Revisar ameaças nos limites `linux_runtime`/socket/PAM e a concorrência do
   SQLite. Criar testes somente para riscos reais descobertos.
5. Não executar instalação root, alterar PAM ou cadastrar biometria sem a
   presença necessária do responsável e uma imagem válida da câmera.
6. Usar a câmera já aprovada no probe somente com presença e consentimento do
   responsável para os cadastros e testes físicos.
7. Manter commits pequenos e atualizar o PR após cada conjunto validado.

### Comandos de validação local

```bash
PYTHONPATH="$PWD/.local-tools/python-tk/usr/lib64/python3.13:$PWD/.local-tools/python-tk/usr/lib64/python3.13/lib-dynload" \
  .venv/bin/python -m unittest discover -s tests -v

.venv/bin/ruff check \
  facekids/linux_auth.py facekids/linux_runtime.py facekids/linux_admin.py \
  facekids/linux_probe.py facekids/linux_pam_helper.py facekids/platform_paths.py \
  tests/test_linux_auth.py tests/test_linux_runtime.py \
  tests/test_linux_admin.py tests/test_linux_installer.py tests/test_linux_probe.py

for script in scripts/*RegataOS.sh packaging/facekids-admin \
  packaging/facekids-linux-probe packaging/facekids-pam-helper; do
  bash -n "$script"
done
```

## Procedimento obrigatório antes de pausar

Antes de qualquer pausa planejada, a IA deve:

1. Atualizar data, commits, PR, testes e estado do hardware neste documento.
2. Mover itens entre realizado, pendente e próximos passos conforme a realidade.
3. Registrar decisões novas, riscos, bloqueios e comandos necessários para
   reproduzir o estado.
4. Executar ao menos as verificações relacionadas às últimas mudanças.
5. Commitar a atualização nesta mesma branch e, quando possível, enviá-la à
   branch remota.
6. Só então encerrar ou aguardar a próxima janela de trabalho.


## Integração real do painel — 23/10/2026

Foi implementado o socket administrativo `/run/facekids/admin.sock`, separado
do socket PAM. Ele usa `SO_PEERCRED`, grupo administrativo configurável,
diretório `0750` e socket `0660`. O renderer Electron continua sem Node.js e
sem acesso ao SQLite; somente o processo principal fala o protocolo JSON
limitado. A conta `filhos` não pertence ao grupo `wheel`.

O painel agora lê perfis, quotas, bônus, horário, sessão e progresso reais. O
fluxo **Nova criança** cria o perfil e inicia no serviço a captura real de 12
amostras. O serviço mantém a câmera, não envia imagens à interface e grava os
vetores atomicamente. Cancelar remove o perfil novo ainda vazio. O runtime pode
permanecer ativo com cadastro incompleto para permitir a recuperação pelo
painel, mas mantém a sessão bloqueada até todos os perfis terem amostras.

Foi criado o aplicativo KDE **FaceKids — Painel dos pais** em
`~/.local/share/applications/facekids-admin.desktop`, além dos scripts
`Abrir-Painel-RegataOS.sh`, `Criar-Atalho-Painel-RegataOS.sh` e
`Atualizar-FaceKids-RegataOS.sh`.

Validação desta etapa: 213 testes Python aprovados (2 skips específicos do
Windows), typecheck dos quatro pacotes, 2 testes TypeScript, build Vite/Electron,
Ruff dos módulos Linux alterados, sintaxe shell e `systemd-analyze verify` da
unidade. O lançador abriu o Electron no KDE; o aviso VA-API do driver híbrido
não impediu a execução.

O atualizador foi executado com sucesso na máquina em 23/10/2026 às 10:08
(`America/Sao_Paulo`). O serviço foi reiniciado e permaneceu ativo, com grupo
`wheel`. As permissões observadas foram `/run/facekids` `0750`, `admin.sock`
`0660 root:wheel` e `auth.sock` `0600`. Uma consulta real feita pela conta
`marcos` retornou serviço online, um perfil existente, nenhuma captura em
andamento e resposta JSON válida. O banco existente foi preservado.

Para reaplicar esta versão após alterações futuras, use:

```bash
sudo bash scripts/Atualizar-FaceKids-RegataOS.sh filhos wheel
```
