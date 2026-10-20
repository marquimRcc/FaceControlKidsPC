# RFC-001 — Face Access Gate para conta compartilhada

**Status:** Proposta para análise; não implementada.  
**Branch:** `feature/face-access-gate`  
**Origem:** `main`, MVP 0.4  
**Autor/projeto:** Marcos Queiroz Gomes — [FaceControlKidsPC](https://github.com/marquimRcc/FaceControlKidsPC)  
**Data:** 2026-10-20

## 1. Objetivo

Na conta compartilhada **Filhos**, uma webcam comum identifica uma entre três crianças, consulta o saldo individual e **libera a área de trabalho** enquanto houver tempo. Na ausência de alguém, ao encontrar rosto desconhecido ou quando o saldo acaba, exibe uma tela de restrição. Uma outra criança com saldo pode se sentar e continuar, sem novo login nem senha do Windows.

A conta administradora do responsável permanece separada e sem limitação.

## 2. Distinção crítica: gate de aplicativo ≠ bloqueio do Windows

Uma janela em tela cheia/sempre no topo **não é a tela segura de bloqueio do Windows** e não autentica/desbloqueia a sessão do sistema. Atalhos privilegiados, Gerenciador de Tarefas, troca de usuário, encerramento de processos e falhas de inicialização podem permitir contorno. Não prometer resistência completa a alguém motivado. Não usar digitação automática de senha do Windows, armazenamento de senha do responsável, hooks no secure desktop ou substituições de credenciais nesta fase.

**Trade-off escolhido para explorar:** priorizar praticidade e transição instantânea entre crianças com uma conta compartilhada, aceitando que o mecanismo não equivale a autenticação do Windows. Se for necessária garantia forte, reavaliar contas individuais e autenticação nativa ou controles de sessão mais restritivos.

## 3. Arquitetura pretendida

```text
[Windows: conta ADMINISTRADOR]
        |
[Painel parental] ---- controles autenticados ----+
                                                 |
                              [Serviço de regras / quota]
                              [SQLite protegido em ProgramData]
                              [validação de SID e sessão do SO]
                                                 |
                              IPC autenticado (named pipe)
                                                 |
[Windows: conta compartilhada FILHOS]             |
[Agente da webcam] -------------------------------+
  -> OpenCV YuNet + SFace (processamento local)
  -> observa UM rosto, gera vetor/estado
  -> NÃO altera limites, saldos ou relógio diretamente
        |
[Tela de restrição — aplicativo na sessão Filhos]
  -> aguarda reconhecimento ou mostra saldo esgotado
  -> recolhe tela após autorização positiva do serviço
  -> reaparece ao acabar saldo / ausência / erro
```

O serviço não abre webcam nem desenha interface na sessão do usuário, pois serviços do Windows funcionam em Session 0. A identificação facial e a tela são executadas pelo agente interativo da conta Filhos.

**Separação de arquivos:** o banco e as configurações sensíveis ficam sob ACL de SYSTEM/Administradores; a conta Filhos não deve ter acesso de escrita. A comunicação deve usar autenticação real do Windows por token/SID no servidor, não um valor enviado no JSON. O protótipo `broker.py` 0.4 é apenas um núcleo de regras, ainda **não** é serviço/IPC seguro.

## 4. Estados e transições

| Estado | Condição | Ação |
| --- | --- | --- |
| STARTUP | A sessão Filhos acabou de iniciar | Gate visível, acesso ainda não liberado |
| IDENTIFYING | Uma face observada, sem confiança suficiente | Continuar gate; não cobrar tempo |
| AUTHORIZED(id) | Mesma criança reconhecida com confiança em checagens consecutivas; saldo positivo | Recolher gate; cobrar apenas tempo validado dessa identidade |
| SWITCHING | Identidade mudou ou duas faces aparecem | Mostrar gate temporariamente; confirmar nova criança |
| ABSENT | Ninguém presente além da tolerância | Mostrar gate; pausar contagem |
| EXHAUSTED(id) | Tempo dessa criança terminou | Mostrar gate; informar limite, permitir que outra identidade seja reconhecida |
| CAMERA_ERROR | Câmera indisponível/desconectada | Gate permanece; opção de intervenção do responsável |
| SERVICE_ERROR | Serviço/IPC fora do ar | Gate permanece; oferecer recuperação autenticada do responsável |

**Proposta inicial**, a validar: reconhecimento a cada 5 s, confirmação de duas amostras consecutivas, ausência tolerada por 15 s, mudanças de criança exigem nova confirmação. Valores devem ser configuráveis pelo responsável depois. O tempo não deve ser debitado em sessão bloqueada/suspensa. A medição usa relógio monotônico, data local e persistência; transição de meia-noite e retorno de hibernação precisam de testes.

A interface deve mostrar o saldo antes de permitir uso. Uma criança sem tempo não pode se beneficiar do saldo da outra: se apenas a criança bloqueada for reconhecida, o gate continua. Em caso de múltiplos rostos ou resultados ambíguos, não liberar automaticamente.

## 5. Riscos de burla e controles graduais

| Risco | Possível mitigação | Limite honesto |
| --- | --- | --- |
| Fechar a janela por Alt+F4 ou Gerenciador de Tarefas | Gate sem ação de fechar pública, watchdog e reinício do agente | Um overlay de aplicativo não é fronteira de segurança |
| Impedir inicialização do agente | Inicialização automática na conta Filhos e supervisão por serviço | Existe uma janela de tempo antes do agente aparecer após login; avaliar shell/kiosk se necessário |
| Alterar limites ou resetar SQLite | Arquivo sob serviço privilegiado com ACL restrita, administração via IPC autenticado | Só funciona após instalar/validar serviço e ACL |
| Desconectar webcam / cobrir lente | Falha segura: gate visível; recuperação do responsável | Não usar câmera ausente como autorização |
| Exibir foto/vídeo de um filho com saldo | Estudar liveness, múltiplos quadros, câmera IR e desafio ativo apropriado | YuNet/SFace 2D não é resistente a spoofing sozinho |
| Reiniciar o PC ou matar serviço | Supervisão, persistência e política de falha segura no login | Mecanismos de usuário comum e watchdog não são invioláveis |
| Pressionar Ctrl+Alt+Del / alternar conta | Limitar permissões da conta Filhos e avaliar recursos nativos de kiosk/Assigned Access | Não é possível controlar a tela segura Ctrl+Alt+Del usando uma janela normal |
| Alterar o relógio do SO | Medição monotônica para duração e verificação de transição de dia | Alterações do relógio devem ser registradas e validadas |

**Não** implantar políticas agressivas que afetem a conta administradora, nem desabilitar ferramentas de recuperação sem teste de restauração.

## 6. Prioridades de implementação (após aprovação)

1. Provar apenas UX do gate em **simulação**: tela de acesso, desbloqueio visual e troca de criança, sem bloquear o Windows de fato; chave de saída para o responsável.
2. Integrar motor facial e estados. Validar câmera real, vários ângulos, falsas identificações, duas pessoas, rosto ausente e latência.
3. Implementar serviço Windows com IPC autenticado, SIDs reais, ACL em ProgramData e testes de instalação/recuperação.
4. Integrar painel do responsável executado na conta de administrador com quotas no serviço.
5. Adicionar watchdog que detecte interrupções e opções nativas de recuperação, observando que gate não vira bloqueio de segurança real.
6. Estabelecer critérios de confiabilidade, privacidade e segurança antes de oferecer o instalador.

## 7. Critérios de aceitação

- Três perfis com saldos independentes, sem necessidade de três logins Windows.
- Se Filho 1 terminar o saldo, Filho 2 pode sentar e ser liberado; Filho 1 continua negado.
- Falha de reconhecimento, duas faces ou ausência não liberam acesso.
- Ao sair, o cronômetro da criança anterior pausa após tolerância configurada.
- Reabrir/reiniciar o agente não zera saldos. A criança não altera quotas sem autorização parental.
- A conta do responsável permanece acessível independentemente do gate.
- Em erro de câmera/serviço, há recuperação segura do responsável; sem bloqueio permanente.
- Testes de bypass documentados, incluindo limitações que permanecerem aceitas.

## 8. Perguntas ainda em aberto (não bloqueiam protótipo de UX)

- Qual será o comportamento preferido se alguém apenas olhar para longe por alguns segundos?
- A tela de restrição deve cobrir todos os monitores? (sugestão: sim)
- Crianças podem usar PC simultaneamente diante da câmera? (sugestão: não identificar/cobrar enquanto duas faces aparecem)
- Qual grau de resistência a burlas se espera: dissuasão casual ou controles mais rígidos?
- Devemos admitir alternativa manual pelo responsável em caso de falta da câmera? (sugestão: sim, com autenticação parental)

**Decisão atual:** analisar e prototipar a experiência nesta branch; **não** alterar `main` nem declarar desbloqueio nativo do Windows implementado.
