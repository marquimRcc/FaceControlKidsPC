# ADR-003 — Desbloqueio nativo por rosto com quotas individuais (Windows)

**Status:** Arquitetura proposta para validação; não implementada  
**Data:** 2026-10-20  
**Projeto:** [FaceControlKidsPC](https://github.com/marquimRcc/FaceControlKidsPC)  
**Continuidade:** [RFC-001](RFC-001-FACE-ACCESS-GATE.md), [ADR-002 Linux](ADR-002-REGATA-OS-LINUX.md) e [SERVICO_WINDOWS](SERVICO_WINDOWS.md)

## 1. Decisão de produto: mudou a arquitetura

**Antes (opção A):** após login manual na conta compartilhada `Filhos`, uma janela do programa restringia ou liberava visualmente o desktop. A janela poderia ser encerrada.

**Novo objetivo:** usar o **bloqueio nativo do Windows** (`LockWorkStation`) e um **Credential Provider próprio** para fornecer ao LogonUI credenciais legítimas da **única conta local padrão `Filhos`** somente quando uma das três crianças tiver sido reconhecida e ainda possuir quota diária. O administrador permanece em conta separada e não é desbloqueado pelo reconhecimento das crianças.

Limites diários iniciais: 120 minutos por criança, configuráveis; cada criança tem saldo independente, embora compartilhe uma conta do SO.

**Importante:** o Credential Provider empacota credenciais; a autorização final é feita pelo Windows. Ele **não substitui** o mecanismo de autenticação do SO nem bloqueia outros Credential Providers. O caso de senha/PIN alternativa da conta `Filhos` precisa ser tratado como política familiar: crianças não devem conhecer a senha se a quota precisar prevalecer sobre login manual. Nunca ocultar a opção de senha do administrador ou desabilitar indiscriminadamente os providers do sistema.

## 2. Componentes Windows escolhidos

| Componente | Execução | Tecnologia / dever | Fronteira de segurança |
|---|---|---|---|
| **Painel dos pais** | Conta Windows administradora | Python GUI, cadastro, limites, bônus, logs e recuperação | Opera por IPC autenticado; não lê a senha dos filhos |
| **Quota Broker** | Serviço protegido iniciado no boot pelo SCM | Windows Service; regras, saldos, persistência e decisões | Armazenamento em ProgramData com ACL; só ele pode modificar quotas |
| **Secret Vault** | Acessível apenas ao serviço privilegiado | Credencial local exclusiva da conta `Filhos` protegida pelo Windows, com ACL restrita | Nunca gravar senha em JSON/log, no perfil `Filhos`, em variável ambiente nem na UI |
| **Face Worker** | Processo isolado para captura e inferência, com acesso à câmera | OpenCV + YuNet + SFace + camada de MiniFASNet a validar | Local de execução sob bloqueio e antes do login **ainda não comprovado** |
| **Credential Provider** | DLL nativa C++ V2 carregada pelo LogonUI | Interfaces Win32 CP, verificação do veredito do Broker e serialização para autenticação da conta `Filhos` | Não conter Python/TensorFlow ou inferência pesada dentro da DLL; não retornar senhas a clientes comuns |
| **Presence Agent** | Sessão interativa `Filhos` | Monitor de identidade/presença, contagem e solicitação de `LockWorkStation` | Não decide ou edita quotas por conta própria; se morrer, serviço detecta e trata o evento |
| **Supervisor/Watchdog** | Serviço e agente | Monitora presença do processo de câmera e do monitor de sessão | Não declarar inviolabilidade; sem bloqueio indevido da conta administradora |

Arquitetura conceitual:

```text
                      Conta ADMINISTRADOR
                   [Painel de gerenciamento]
                              |
                       IPC autenticado
                              |
     Windows Service / Quota Broker / SQLite + credencial Filhos
                    /          |           \
            quotas por rosto   |       veredito de acesso
                               |
                    [Face Worker / webcam]
                     YuNet -> SFace -> Liveness
                               |
  [Conta FILHOS]        [LogonUI / Winlogon]
  Presence Agent --lock--> [Credential Provider FaceControlKids]
        |                                |
  monitora sessão              se rosto válido + saldo positivo
        |                       -> credencial local do usuário Filhos
        +----------------------- Windows autentica e desbloqueia
```

**Transporte:** named pipe local com ACL explícita e checagem de identidade/token pelo servidor. Uma operação de observação não pode consultar senha, alterar limite, enviar saldo ou atribuir identidade arbitrária. Processos da conta `Filhos` nunca devem receber senha descriptografada. O CP precisa autenticar o Broker, e o Broker deve restringir o fornecimento de credenciais ao contexto confiável de login (não apenas a um SID arbitrário). Não copiar o pipe NULL-DACL usado no MVP de `caochitam/windows-face-unlock`.

**Fronteira de confiança adicional:** um agente da webcam executado com permissões da criança é manipulável por esse usuário; enviar um embedding pronto por IPC não comprova que ele foi capturado naquele momento. É necessário investigar caminho confiável da câmera ao processo protegido, ou aceitar e documentar explicitamente o limite como ameaça doméstica de baixo risco. Liveness facial não resolve sozinho forjamento de mensagens IPC.

## 3. Dois cenários tecnicamente distintos

### Cenário A — Desbloquear uma sessão existente após Win+L (P0)

1. O Windows já tem uma sessão da conta `Filhos`, agora bloqueada.
2. O Face Worker recebe imagem da webcam **com a sessão bloqueada**.
3. Reconhece um único filho em amostras consecutivas e verifica liveness.
4. Quota Broker confirma o saldo e emite uma **autorização curta, de uso único**, vinculada à sessão e identidade.
5. O Credential Provider da conta `Filhos` é selecionado ou ativado no LogonUI e solicita a autorização.
6. Somente após veredito positivo, o CP serializa a credencial local para autenticação do Windows.
7. O Windows desbloqueia; o Broker associa a identidade ao monitor de uso e contabiliza o tempo.

**Bloqueador técnico inicial:** validar, no Windows real, webcam acessível com tela bloqueada e comportamento de ativação/autoenvio do Credential Provider. O Windows tem mecanismos de provider/tile default, mas isso não garante operação totalmente mãos livres em toda configuração do LogonUI.

### Cenário B — Login inicial após reinício ou logoff (P1)

**Não existe ainda uma sessão interativa da conta `Filhos`.** Um agente executado apenas quando essa conta efetua login não resolve o reconhecimento pré-login. Será necessário comprovar estratégia apropriada de captura/inferência antes do login: processo auxiliar supervisionado em contexto acessível, media stack ou outro desenho testado no Windows.

**Decisão:** entregar primeiro o cenário A e só anunciar login direto pelo rosto após boot quando o cenário B passar em testes reais; jamais usar autologon genérico sem quotas como atalho.

## 4. Estados e lógica funcional

| Estado | Evento | Resultado |
|---|---|---|
| BOOT_OR_LOCKED | Tela nativa do Windows aguardando rosto | Nenhum desbloqueio sem decisão positiva |
| RECOGNIZING | Uma face detectada | Requer N confirmações e teste de vivacidade |
| UNKNOWN_OR_MULTIPLE | Desconhecido ou 2+ pessoas | Não autorizar; permitir nova tentativa |
| AUTHORIZED(child_id) | Filho reconhecido + saldo positivo + sessão válida | CP pode oferecer credencial da conta `Filhos` para o Windows |
| SESSION_ACTIVE(child_id) | Desktop aberto e criança presente | Descontar quota individual por tempo validado |
| ABSENT_OR_CHANGED | Ausência/mudança de rosto além da tolerância | Parar débito indevido, bloquear sessão e exigir nova identificação |
| EXHAUSTED(child_id) | Saldo terminou | LockWorkStation; recusar nova autorização para aquele filho |
| CAMERA_OR_SERVICE_ERROR | Erro na webcam, serviço ou IPC | Sem liberação pelo rosto; recuperação pelo responsável |
| PARENT_RECOVERY | Responsável usa credenciais próprias | Configuração, reparação e atualização continuam acessíveis |

Configurações preliminares (calibrar): quota inicial 120 min, identificação por 2-3 amostras consistentes, monitoramento frequente de 1–3 s quando autorizado, tolerância de ausência de 10–15 s. A contabilização deve usar tempo monotônico + estado de sessão do SO; persistir consumos e deduplicar janelas após sleep/hibernate/restart. Mudanças de data, fuso e relógio precisam ser testadas.

**Observação importante:** presença contínua de um irmão com saldo, mesmo com o outro exaurido, não deve permitir que ambos apareçam ou que o irmão exaurido continue usando. Com dois rostos, suspender autorização e pedir enquadramento único. Não equivale a garantir quem realmente usa teclado/mouse.

## 5. Credencial da conta Filhos

Para um Credential Provider tradicional de conta local, provavelmente precisaremos de credencial válida para serialização. A solução inicial proposta é uma **senha exclusiva e forte da conta local padrão `Filhos`**, conhecida apenas pelo responsável/armazenamento protegido do Broker.

O Broker guarda a credencial protegida sob o contexto do serviço, sem expô-la ao agente da criança, painel normal ou outro processo da conta `Filhos`. O CP recebe dados necessários **apenas sob autenticação/autorizações restritas**, minimizando a presença de senha em memória e canais IPC. O armazenamento com DPAPI e ACL deve ser estudado em conjunto, sem pressupor que criptografia user-scope na própria conta Filhos seja proteção contra processos dessa conta.

**Condição essencial:** o Credential Provider **não impede** que o Windows aceite a senha real da conta `Filhos` por outro tile. Isso é intencional para recuperação. Para tornar as quotas eficazes, os filhos não podem conhecer/usar essa senha. O administrador mantém sua conta separada e método de login próprio. Não bloquear nem esconder provedores de credenciais nativos do sistema na primeira versão.

## 6. Anti-spoof e privacidade

- Manter YuNet + SFace; avaliar MiniFASNet ONNX (DeepFace) como segunda decisão obrigatória antes de liberar por rosto; considerar controle de múltiplos rostos e resolução/iluminação.
- Não afirmar que câmera RGB comum impede fotografia, replay ou deepfake. Medir falso aceite e falso bloqueio em diferentes pessoas/condições.
- Não guardar fotos, vídeo ou credenciais de familiares sem necessidade. Embeddings biométricos ficam em armazenamento local com ACL; observar termos dos pesos/ONNX antes de redistribuir.
- Falha de webcam não pode conceder saldo, emitir credencial ou deixar o Windows aberto indefinidamente por ausência de monitoramento.

## 7. Compatibilidade e evolução Linux

A [ADR-002](ADR-002-REGATA-OS-LINUX.md) continua válida para reconhecimento, banco e escolha de Qt/KDE. A revisão de produto altera a **camada de autenticação**, não a identificação facial:

- Linux: estudar Gaze + KScreenLocker/PAM como referência real de desbloqueio; exige **gate de quota por criança** antes do resultado positivo do PAM.
- Manter a mesma conta compartilhada; não cadastrar três faces e permitir desbloqueio direto por Gaze sem controle individual.
- Gaze é GPL-3.0; avaliar integração como componente instalado separadamente, sem copiar código GPL para o núcleo MIT inadvertidamente.
- Primeiro validar Windows; depois revisar a integração do SDDM/login pré-sessão no Regata OS.

## 8. Critérios de entrada para implementação (provas técnicas)

| Ordem | Prova | Critério de aprovação |
|---|---|---|
| P0-1 | Webcam após Win+L | Face Worker captura e identifica com sessão bloqueada, sem precisar desbloquear primeiro |
| P0-2 | Credential Provider mínimo | DLL funciona no LogonUI e permite volta à senha quando falha; também é desinstalável |
| P0-3 | IPC autenticado | Nenhum processo normal da conta Filhos consegue obter senha, conceder bônus ou fingir autorização |
| P0-4 | Cofre de credencial | Credencial da conta Filhos persistida sem acesso de leitura pelo perfil infantil |
| P0-5 | Quotas + autorização | Filho 1 com 0 min não desbloqueia; Filho 2 com saldo desbloqueia a MESMA conta |
| P0-6 | Lock/monitoramento | Quota esgotada ou ausência leva ao lock nativo; suspend/restart não zera dados |
| P0-7 | Recuperação | Senha original/fallback e a conta ADMIN continuam funcionais; instalador permite rollback |
| P1-1 | Login inicial após boot | Worker disponível antes de haver sessão Filhos, sem contornar quota |

**Não instalar CP no Windows principal na primeira iteração.** Testar em VM com imagem/restore ou PC de testes, manter recuperação administrativa. Só liberar instalador após provas P0.

## 9. Referências de pesquisa

- Microsoft Credential Providers: https://learn.microsoft.com/en-us/windows/win32/secauthn/credential-providers-in-windows
- Microsoft ICredentialProvider::GetCredentialCount: https://learn.microsoft.com/en-us/windows/win32/api/credentialprovider/nf-credentialprovider-icredentialprovider-getcredentialcount
- Microsoft recomenda não ocultar providers nativos com CredentialProviderFilter: https://learn.microsoft.com/en-us/windows/win32/api/credentialprovider/nn-credentialprovider-icredentialproviderfilter
- Microsoft Interactive Services / Session 0: https://learn.microsoft.com/en-us/windows/desktop/services/interactive-services
- Windows Face Unlock, CP experimental: https://github.com/caochitam/windows-face-unlock
- Issue sobre named pipe/credenciais: https://github.com/caochitam/windows-face-unlock/issues/3
- Microsoft SampleCredentialProvider: https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/CredentialProvider
- Gaze KDE/PAM: https://gaze.gundulabs.com/guide/kde

**Esta ADR é somente de arquitetura. Nenhum código, configuração, senha ou provider foi instalado ou modificado.**
