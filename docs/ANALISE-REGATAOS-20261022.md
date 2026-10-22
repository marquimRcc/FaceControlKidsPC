# Análise Linux / Regata OS — 22/10/2026

## Estado do trabalho
Branch remota criada: research/regataos-linux-20261022.
Base: main, commit 8548c872f4108de3c160291b3567f857040978ac.
Nenhuma implementação, instalação ou alteração de PAM foi feita.
A pasta local estava vazia e não continha .git; Git não está instalado.
Este arquivo local é um relatório, não um clone do projeto.

## Escopo e evidência
Revisitada a lista completa de tecnologias registrada na ADR-002 de 20/10.
Lidos os módulos recognition.py, policy.py, storage.py e filhos_agent.py e requirements.txt em main.
Consultados READMEs/documentação dos projetos relacionados abaixo.
Isto é triagem documental e inspeção local, não auditoria completa dos terceiros nem benchmark.
Parte do histórico de chats retorna referências sem texto; a ADR do repositório foi a fonte recuperável das decisões anteriores.
Não foram capturadas imagens nem cadastradas biometrias.

## Notebook observado
- Regata OS 26 Temerario; KDE Plasma workspace 6.6.5; sessão X11.
- Display manager em execução: SDDM, via display-manager-legacy.service.
- Intel i7-2630QM, 4 núcleos / 8 threads, cerca de 15 GiB de RAM.
- CPU anuncia AVX, mas não AVX2: verificar requisitos de cada binário/runtime.
- /dev/video0 e /dev/video1: ambos identificados como USB 2.0 Camera.
  Dois nós não provam duas câmeras nem presença de infravermelho.
- Python 3.13.14; NumPy importável; cv2, PySide6 e pip ausentes nesse interpretador.
- PAM de SDDM e KDE encontrado em /usr/lib/pam.d/, incluindo common-auth.
  /etc/pam.d/sddm e /etc/pam.d/kde não existem neste estado.
- Acesso efetivo a frames, formatos V4L2, FPS e desempenho ainda não testados.
- Não presumir compatibilidade de RPM Fedora ou Tumbleweed com este Regata OS.

## Repositórios já considerados

| Referência | Avaliação para este projeto |
|---|---|
| [OpenCV Zoo / YuNet e SFace](https://github.com/opencv/opencv_zoo) | Manter como primeira opção. Já usados no código e adequados para identificação 1:N. Medir desempenho real. O README atual de YuNet distingue o modelo 2026may para OpenCV 5; o FaceKids usa 2023mar e exige OpenCV menor que 5. Não atualizar modelo e motor sem validação conjunta. |
| [DeepFace](https://github.com/serengil/deepface) | Referência para experimentos e antifraude; não adicionar toda a pilha como requisito inicial. |
| [Silent-Face-Anti-Spoofing / MiniFASNet](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing) | Candidato opcional para teste de fotos e vídeo. Confirmar licenças dos pesos e medir falsos aceites/rejeições neste notebook. Não confundir score com garantia de vivacidade. |
| [MediaPipe](https://github.com/google-ai-edge/mediapipe) | Reserva para presença, orientação e movimento; não substitui identificação e quotas. |
| [InsightFace / ArcFace](https://github.com/deepinsight/insightface) | Alternativa de comparação; verificar termos de cada peso. Não justifica migração imediata do SFace. |
| [Howdy](https://github.com/boltgolt/howdy) | Referência PAM com instruções openSUSE. Autentica conta; sozinho não aplica quota por rosto. O projeto reconhece limitações contra fotos e pessoas semelhantes. |
| [Timekpr-nExT](https://github.com/polesapart/timekpr-next) | Boa referência de daemon, limites e acompanhamento por conta. Pode ser teto global opcional ou alternativa com contas separadas. Não separa três rostos na mesma conta. |
| [KScreenLocker](https://github.com/KDE/kscreenlocker) | Referência de bloqueio nativo. Janela fullscreen do FaceKids não oferece a mesma proteção. |
| [LayerShellQt](https://github.com/KDE/layer-shell-qt) | Relevante para Wayland; não é dependência prioritária na sessão X11 atual e não cria uma barreira de autenticação. |
| [systemd](https://github.com/systemd/systemd) e [logind](https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.login1.html) | Base de supervisão e observação de sessão. Conferir APIs disponíveis na versão local 254; documentação latest pode descrever APIs posteriores. Solicitar desbloqueio por D-Bus não comprova autenticação PAM. |
| [dlib](https://github.com/davisking/dlib) | Biblioteca válida, mas acrescenta outra cadeia de reconhecimento/compilação. Sem ganho demonstrado para substituir o motor atual. |
| [FaceNet](https://github.com/davidsandberg/facenet) | README ainda descreve TensorFlow 1.7, Ubuntu 14.04 e Python antigos; custo de adaptação injustificado para este piloto. |
| [OpenFace](https://github.com/cmusatyalab/openface) | Referência histórica de reconhecimento; não oferece o fluxo KDE e quotas necessário. |
| [keras-vggface](https://github.com/rcmalli/keras-vggface) | README referencia Keras 2.2.4 e TensorFlow 1.14; não adotar nesta plataforma Python 3.13. |
| [TensorFlow Model Garden](https://github.com/tensorflow/models) | Coleção ampla de modelos e treinamento; não é solução pronta de login ou controle parental. |

## Outras opções encontradas

| Projeto | Potencial e limite |
|---|---|
| [Gaze](https://github.com/GunduLabs/gaze) | Primeiro candidato externo para investigar integração KDE/PAM: documenta gaze-kde e pacotes openSUSE Tumbleweed. Isso não confirma suporte ao Regata OS. O RPM pode alterar PAM compartilhado no pós-instalação; examinar pacote antes de instalar. Não fornece as quotas faciais do FaceKids. |
| [LinuxCamPAM](https://github.com/Vladush/LinuxCamPAM) | Segundo candidato: utiliza YuNet/SFace, aceita webcam V4L2 e documenta aproximação/login e KDE. Distribuição principal Debian/Ubuntu; instalador ativa PAM automaticamente. Exige estudo de build/empacotamento para Regata. |
| [Facelock](https://github.com/tyvsmith/facelock) | PAM e inferência local; exige captura IR segundo README. Adiar até confirmar câmera IR e compatibilidade de runtime/CPU. |
| [Visage](https://github.com/sovren-software/visage) | Arquitetura Rust, daemon e PAM via D-Bus útil como referência. README registra falha em ensaio de vivacidade com foto em celular; não escolher por alegação genérica de antifraude. |
| [MrCodeEU/face-auth](https://github.com/MrCodeEU/face-auth) | Alternativa PAM centrada em IR; triagem inicial apenas, sem auditoria de código ou validação neste hardware. |
| [dax-auth](https://github.com/daxrpm/dax-auth) | Outra implementação PAM em Rust; triagem inicial apenas. Não há evidência local para preferi-la ao motor já existente. |

## O que reaproveitar do FaceKids
recognition.py já encapsula YuNet/SFace; identify faz comparação por pessoa, limiar e margem entre candidatos.
policy.py contém regras puras e relógio monotônico, facilitando reaproveitamento.
storage.py contém saldo e configurações, mas precisa de propriedade e permissões apropriadas no Linux.
filhos_agent.py não é um agente Linux pronto: contém caminhos C:/ProgramData, mutex Win32, named pipes,
tasklist e executável pythonw. Portar o núcleo e criar adaptadores Linux, em vez de executar esse módulo diretamente.

## Problemas de arquitetura que precisam de decisão
1. Preservar três filhos na mesma conta exige identidade facial além da identidade Unix.
   PAM comum verifica a conta solicitada: cadastrar três rostos não cria três saldos.
2. SO_PEERCRED autentica o UID do cliente, não a veracidade de child_id ou do resultado facial.
   Um processo comum da conta dos filhos não pode ser a autoridade final do reconhecimento.
   Para proteção contra adulteração, separar o reconhecedor em processo confiável com arquivos protegidos;
   definir acesso à câmera no boot e no lock e comunicação que o usuário não consiga forjar.
   Isso exige revisar a decisão anterior que colocava captura exclusivamente no processo interativo.
3. Um overlay pode ser encerrado ou contornado; serve a demonstração, não ao bloqueio final.
   A versão protegida precisa integrar a decisão facial + quota ao bloqueio/autenticação nativos
   ou usar outra forma de restrição comprovada. Bloquear e deixar senha compartilhada liberar
   novamente também permite contornar a quota.
4. PAM só entra quando o cliente inicia uma conversa de autenticação. Login ao sentar sem clicar
   depende também do SDDM/KScreenLocker e do disparo automático, não apenas do reconhecedor.
5. Três contas Linux separadas simplificam isolamento e Timekpr, mas mudam a experiência desejada
   de uma conta compartilhada. É alternativa para discussão, não mudança adotada.

## Proposta para discussão
Preservar a conta compartilhada e o motor YuNet/SFace como direção principal.
Primeira etapa: ambiente Python isolado e diagnóstico de câmera/reconhecimento, sem integração PAM.
Medir latência, CPU, iluminação, ausência, duas faces e confusão entre os três perfis.
Depois comparar Gaze e LinuxCamPAM como referências de integração nativa, sem entregar a eles
a lógica de quotas. Verificar código, licenças, pesos, pacotes, recuperação e compatibilidade.
Somente então detalhar o serviço confiável e a integração SDDM/KScreenLocker.
MiniFASNet entra como experimento posterior; Timekpr apenas se agregar uma proteção clara.
Não acrescentar TensorFlow, dlib ou InsightFace sem benefício medido.

## Critérios antes de uma instalação operacional
Reconhecimento e quota juntos autorizam acesso; falha de serviço/câmera não libera.
Reinício e suspensão não zeram nem cobram indevidamente o saldo.
Troca de filho, desconhecido e duas faces têm comportamento definido.
Usuário dos filhos não edita banco/configuração nem falsifica autorização por IPC.
Falha do agente não deixa desktop irrestrito.
Login inicial, desbloqueio e aproximação são testados separadamente.
Conta do responsável e recuperação por senha continuam disponíveis.
Estes itens são critérios futuros; não foram certificados nesta análise.
