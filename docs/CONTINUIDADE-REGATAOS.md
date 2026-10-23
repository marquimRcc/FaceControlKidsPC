# Continuidade do trabalho no Regata OS

> Documento de passagem para outra IA ou para uma nova janela de trabalho.
> Deve ser atualizado e commitado nesta branch imediatamente antes de toda
> pausa planejada, incluindo pausas por limite de uso.

## Estado de referência

- Data da atualização: 22/10/2026, fuso `America/Sao_Paulo`.
- Repositório: `marquimRcc/FaceControlKidsPC`.
- Branch: `feature/regataos-linux-implementation-20261022`.
- Base do trabalho Linux: `research/regataos-linux-20261022`.
- Pull request draft: <https://github.com/marquimRcc/FaceControlKidsPC/pull/3>.
- Último commit funcional local antes deste documento: `308f85e`.
- Último commit funcional remoto antes deste documento: `15895bed37293d58c30b7832340997a124d37d90`.
- Ambiente observado: Regata OS 26, KDE Plasma 6.6.5, X11 e Python 3.13.

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

Concluída para o estado atual. A suíte local passou com 206 testes, dois
ignorados por dependerem de Windows real. Os workflows `Unit tests` passaram
em Ubuntu e Windows, e `Linux Regata OS checks` passou. Os scripts passaram em
`bash -n` e os novos módulos Linux passaram no Ruff.

### Fase 5 — validação física e experiência sem clique

Parcial. A webcam real passou no probe depois do aquecimento da autoexposição.
Ainda depende de instalar como root, cadastrar todas as crianças configuradas
e executar testes controlados de sessão e recuperação. O serviço já solicita
desbloqueio direto pelo logind após três confirmações; a validação física no
KScreenLocker/SDDM permanece pendente.

## Trabalho realizado

- Criadas as branches de pesquisa e implementação.
- Implementado runtime Linux para uma conta compartilhada e quantidade
  variável de perfis.
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
  retornou `CAMERA_UTILIZAVEL`: 31/31 quadros utilizáveis, 6,11 fps e brilho
  médio aproximado de 90,74. Nenhum rosto estava no quadro durante o teste.
- A conta `filhos` ainda não existia durante a análise.
- A instalação do sistema exige `sudo` interativo; a sessão automatizada não
  possui a senha do responsável.
- O helper PAM atende uma conversa de autenticação já iniciada. O runtime agora
  também solicita desbloqueio direto pelo logind, mas o comportamento sem
  clique ainda precisa ser comprovado fisicamente no KDE desta máquina.
- O PR aparece como draft e deve continuar assim até a validação física e a
  revisão final de segurança.

## O que falta fazer

1. Criar a conta compartilhada `filhos` e confirmar que ela não tem privilégios
   administrativos.
2. Instalar o serviço com `sudo`, informando a quantidade desejada, validar
   permissões e revisar o journal.
3. Cadastrar presencialmente todas as crianças configuradas com consentimento
   do responsável.
4. Testar troca de criança, ausência, múltiplos rostos, quota esgotada, bônus,
   virada do dia, suspensão e toque de recolher.
5. Testar bloqueio e desbloqueio KDE, além da recuperação pela conta
   administrativa e por senha.
6. Somente depois, testar a ponte PAM opt-in e seu script de recuperação.
7. Avaliar plugin de KScreenLocker/SDDM se o desbloqueio direto pelo logind não
   produzir a experiência sem clique desejada.
8. Avaliar uma verificação de vivacidade adequada; a confirmação temporal
   atual não impede apresentação de foto ou vídeo.
9. Avaliar notificações por um canal seguro para o barramento da sessão.
10. Fazer revisão final do PR, atualizar documentação de operação e decidir a
    estratégia de merge para a branch principal.

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

