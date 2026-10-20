# ADR-002 — Plataforma Linux / Regata OS (FaceControlKidsPC)

**Status:** Decisões de arquitetura registradas; nenhuma integração Linux instalada ou implementada.  
**Data:** 2026-10-20  
**Projeto de origem:** https://github.com/marquimRcc/FaceControlKidsPC  
**Autor original:** Marcos Queiroz Gomes (@marquimRcc)  
**Derivada de:** docs/RFC-001-FACE-ACCESS-GATE.md  
**Alcance:** Regata OS baseado em openSUSE, KDE Plasma 6, com atenção especial ao Wayland.

## Objetivo funcional preservado

O cenário principal é **uma conta Linux de usuário comum compartilhada pelos três filhos**. A webcam reconhece individualmente o filho presente e um controlador local verifica **saldo por criança**, mesmo que todos estejam conectados ao mesmo usuário do sistema operacional. O responsável utiliza outra conta com privilégios administrativos.

O projeto NÃO pretende fazer o login nativo do Linux automaticamente em nome de várias crianças na mesma conta. A liberação facial inicial será uma autorização de uso da interface do FaceControlKidsPC dentro da sessão já aberta. Uma sobreposição visual não é equivalente a um bloqueio seguro do KDE ou a autenticação do PAM.

## Decisões adotadas para a primeira implementação Linux

| ID | Elemento | Tecnologia escolhida | Motivo |
|---|---|---|---|
| L-01 | Detecção de face | OpenCV + YuNet | Mesmo algoritmo do Windows; leve, reutilizável e local |
| L-02 | Identificação individual | OpenCV + SFace | Mesmas representações e regras de comparação; suporte a três identidades na mesma conta |
| L-03 | Estado e quotas | GateModel / Broker e SQLite, refinados para persistência segura | Saldo por rosto, não por usuário do Linux |
| L-04 | Captura de webcam | OpenCV VideoCapture/V4L2, com validação de dispositivos, permissões e PipeWire se necessário | A webcam pertence ao processo interativo da conta compartilhada, nunca ao serviço do sistema |
| L-05 | Executor da sessão dos filhos | Agente na sessão gráfica KDE, iniciado e supervisionado pelo systemd do usuário e/or autostart XDG | Integração com ciclo de vida do desktop; um usuário comum ainda pode encerrar o próprio agente |
| L-06 | Controlador privilegiado | Daemon de sistema gerenciado por systemd | Persiste limites e contabilização; não abre webcam nem desenha interface |
| L-07 | Comunicação local | Socket Unix autenticado por credenciais do SO (ex.: SO_PEERCRED), com política administrativa e validação de UID | Não confiar em nome de conta, UID, id da criança ou segundos declarados em JSON |
| L-08 | Banco | SQLite em diretório de serviço sob /var/lib/facecontrolkidspc/ e controle de permissões | A conta dos filhos não poderá alterar diretamente o saldo |
| L-09 | Estado da sessão | systemd-logind via D-Bus | Detectar sessão ativa, bloqueio, mudança de usuário, suspensão e retomada; contabilizar só quando autorizado |
| L-10 | Interface de bloqueio visual | **Qt 6 / PySide6** como opção prioritária a validar no KDE Plasma 6; avaliar LayerShellQt sob Wayland | Melhor alinhamento com o desktop KDE do que depender apenas do Tkinter/XWayland. Não é barreira de segurança |
| L-11 | Recuperação | Conta do responsável, senha tradicional e procedimento de desinstalação/reparação | Evitar bloqueio permanente, inclusive após falha de câmera ou serviço |

**Importante:** essas são decisões para implementação FUTURA; o Windows permanece funcional em versão experimental. As técnicas de inicialização, ACL, PipeWire, widget Qt e Wayland precisam ser testadas na versão específica do Regata OS, e a compatibilidade de pacotes do openSUSE NÃO deve ser presumida automaticamente.

## Tecnologias analisadas: decisões explícitas

### DeepFace / MiniFASNet ONNX — PRIORIDADE DE PESQUISA

O DeepFace tem anti-spoof baseado nos dois modelos MiniFASNetV2 e MiniFASNetV1SE e disponibiliza uma implementação ONNX Runtime que pode ser avaliada sem trocar o reconhecedor SFace. O código dos modelos de origem em Silent-Face-Anti-Spoofing é Apache-2.0, porém termos dos pesos e distribuição deverão ser confirmados arquivo a arquivo.

**Decisão:** investigar primeiro como **camada opcional de vivacidade** em Windows e Linux; aprovar somente depois de ensaios com webcam RGB real, foto em papel, fotografia na tela de um celular, vídeos, óculos, iluminação difícil e falsos negativos. Nenhuma alegação de segurança garantida.

### MediaPipe — RESERVADO

Utilizar somente se houver ganho mensurável em detecção de ausência, orientação e movimento da face. Piscada/cabeça em movimento não bastam para impedir fraude por replay de vídeo. Não adicionar como dependência obrigatória agora.

### InsightFace / ArcFace — ALTERNATIVA, NÃO PADRÃO

Tem reconhecimento e vivacidade opcionais atuais, mas seus pesos pré-treinados são declarados para pesquisa não comercial. Como o FaceControlKidsPC é aberto e permite redistribuição, NÃO incorporar os pacotes padrão de modelos à distribuição sem uma licença específica válida e verificação dos termos. Pode ficar como referência para benchmarking e estudo.

### Howdy — REFERÊNCIA DE AUTENTICAÇÃO NATIVA LINUX, **NÃO** O GATE PRINCIPAL

Howdy utiliza PAM e pode participar do login e do desbloqueio da sessão KDE, conforme configuração e suporte da distribuição. Isso autentica **uma identidade de conta Linux**, não três saldos independentes dentro da mesma conta. Conceder autenticação da conta "Filhos" a qualquer um dos três rostos permitiria ingressar na conta sem que o PAM soubesse se o saldo individual se esgotou.

**Decisão:** não usar Howdy no fluxo principal da opção A. Usar como referência técnica de integração PAM e, futuramente, avaliar apenas como autenticação adicional do responsável ou em uma arquitetura diferente com três contas. Nunca alterar PAM do sistema sem backup, acesso alternativo por senha e recuperação testada.

### KScreenLocker / PAM — LOCK NATIVO SOMENTE COMO ALTERNATIVA FUTURA

KScreenLocker é responsável pelo bloqueio nativo do KDE e utiliza PAM para autenticação. Isso não é a mesma coisa que um overlay do aplicativo. O systemd-logind oferece mensagens LockSession/UnlockSession, mas elas são solicitações a um gerenciador de sessão; não prometemos que desbloquearão a tela autenticada por PAM. Não automatizar o desbloqueio nativo por chamada de API ou por armazenamento de senha.

**Decisão:** na opção A, não acionar o bloqueio nativo como rotina de troca de crianças; tela de restrição visual do aplicativo com indicação explícita da limitação. Uma solução com PAM só entra em uma revisão de arquitetura específica e auditada.

### Timekpr-nExT — FONTE DE ARQUITETURA E FAILSAFE OPCIONAL

Timekpr-nExT é um gerenciador de tempo por **conta do sistema**, com administração parental e serviço de fundo. Tem suporte/documentação para pacotes openSUSE, mas pode haver diferenças no Regata OS. Não identifica três filhos que partilham uma conta Linux.

**Decisão:** não usar para contabilização por criança. Avaliar separadamente como **limite máximo global da conta Filhos** ou referência de serviço/supervisão, desde que não haja logout inesperado, dupla cobrança ou interrupção da sessão entre crianças. A integração é opcional, não obrigatória.

### Dlib, FaceNet, OpenFace, VGGFace e TensorFlow Model Garden — NÃO ADOTAR

Não substituem vantajosamente a combinação existente; várias referências dependem de pilhas legadas ou elevam custo de manutenção. Permanecem apenas como materiais de comparação técnica e histórica.

## Licença dos modelos e open source

- Código do FaceControlKidsPC: MIT, com preservação de copyright e LICENSE.
- OpenCV: Apache-2.0.
- Modelo YuNet 2023mar no OpenCV Zoo: diretório do modelo com licença **MIT**.
- Modelo SFace 2021dec no OpenCV Zoo: diretório do modelo com licença **Apache-2.0**, sujeito à checagem da procedência/termos dos pesos treinados e a eventuais obrigações associadas ao conjunto de treinamento.
- DeepFace: código MIT, porém componentes externos e pesos podem ter licenças independentes.
- InsightFace: código MIT e pesos pré-treinados normalmente restritos a pesquisa não comercial.
- Timekpr, componentes do KDE, LayerShellQt e PAM têm seus próprios termos; consultar licenças específicas antes de copiar código e, preferencialmente, integrar usando APIs e bibliotecas existentes.
- Não embutir pesos adicionais até confirmar a licença exata e documentar a origem e o checksum de cada arquivo.

## Requisitos de proteção no Regata OS

1. Não habilitar login automático como administrador; filhos em usuário comum.
2. O responsável controla configurações e recuperação, sem perder sua própria sessão.
3. Vetores biométricos dos menores em armazenamento local protegido, sem imagens brutas persistidas por padrão.
4. Na falha de webcam, autenticação incerta ou IPC fora do ar, não conceder autorização visual e oferecer recuperação parental segura.
5. O serviço de sistema identifica o usuário/sessão usando informações fornecidas pelo SO, não pelo cliente; comandos de créditos/limites exigem autorização do responsável.
6. A janela Wayland/LayerShellQt pode ser fechada por meios do desktop; portanto jamais prometer resistência completa a burlas. O watchdog e a política de restrição não criam uma fronteira de segurança equivalente ao bloqueio KDE.
7. Dois rostos simultâneos ou rosto desconhecido não autorizam automaticamente. Contagem pausa quando presença não for confirmada.
8. Suporte a duas telas, logout, reinício, hibernação, troca de usuário, reinício de serviço, câmera disputada por outro processo e atualização do KDE precisa de testes.

## Plano de pesquisa e validação sem alterações de código

**Etapa Linux 1 — descobrir o ambiente Regata OS:** confirmar versão exata, Plasma, Wayland/X11, gerenciador de login, PAM, systemd, dispositivos V4L2, opções de instalação e permissões da webcam.

**Etapa Linux 2 — portar o reconhecimento existente:** validar OpenCV com YuNet/SFace na webcam real, cadastrar voluntariamente os três perfis e calibrar falso aceite/rejeição com amostras diversas.

**Etapa Linux 3 — testar antifraude:** comparar MiniFASNet ONNX com a câmera e o hardware disponíveis; registrar taxa de rejeição de rostos legítimos e aceitação de fotos/replays.

**Etapa Linux 4 — experiência KDE:** verificar Qt6/Wayland, telas múltiplas e mecanismos de overlay, mantendo saída segura e explicitando que o overlay não é tela de lock nativo.

**Etapa Linux 5 — segurança do controlador:** avaliar systemd service, isolamento de SQLite, credenciais de IPC, detecção de estado via logind e medidas de recuperação.

**Etapa Linux 6 — opções adicionais:** reavaliar Timekpr-nExT como teto global; manter Howdy fora do gate de três crianças, salvo mudança explícita de arquitetura.

## Fontes verificadas em 2026-10-20

- Regata OS baseado em openSUSE: https://suporte.regataos.com.br/p/faq-do-regata-os.html
- SFace e licença: https://github.com/opencv/opencv_zoo/blob/main/models/face_recognition_sface/README.md
- YuNet e licença: https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/README.md
- DeepFace e módulos ONNX: https://github.com/serengil/deepface/tree/master/deepface/models/spoofing/onnx
- MiniFASNet: https://github.com/minivision-ai/Silent-Face-Anti-Spoofing
- InsightFace licenças: https://github.com/deepinsight/insightface
- MediaPipe: https://github.com/google-ai-edge/mediapipe
- Howdy: https://github.com/boltgolt/howdy
- Timekpr-nExT: https://github.com/polesapart/timekpr-next
- KDE KScreenLocker: https://github.com/KDE/kscreenlocker
- KDE LayerShellQt: https://github.com/KDE/layer-shell-qt
- systemd-logind: https://www.freedesktop.org/software/systemd/man/org.freedesktop.login1.html
- Serviços e autostart do desktop: https://github.com/systemd/systemd/blob/main/docs/DESKTOP_ENVIRONMENTS.md

**Esta ADR registra decisões e riscos, não implementa código nem altera configurações do sistema.**
