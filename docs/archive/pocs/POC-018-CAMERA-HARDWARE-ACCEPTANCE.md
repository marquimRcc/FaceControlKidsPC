# P0-18 - Critérios de aceitação para câmera real e desbloqueio facial

**Estado: PENDENTE DE TESTE COM HARDWARE.** A compilação no GitHub
Actions, a enumeração de câmeras e os testes com rostos simulados
não demonstram desbloqueio facial funcional.

## Fronteira de confiança

O serviço Windows é LocalSystem e o Credential Provider roda no
contexto do LogonUI. O Windows separa a sessão de serviço (Session 0)
das sessões interativas. Uma câmera enumerada no serviço não prova
que seu fluxo de vídeo é utilizável durante a tela de bloqueio.

O teste Win+L existente na conta Filhos só demonstra que um
programa já iniciado conseguiu receber frames com Windows bloqueado.
Ele não prova que esse mesmo programa seja confiável contra
falsificação de mensagens por outro processo da conta Filhos.

Nenhum valor como child_id, liveness_passed, contador de frames ou
quota fornecido diretamente por um aplicativo da criança pode
conceder autenticação. Um futuro worker de câmera precisará ser
protegido pelo serviço e seu canal de comunicação deverá autenticar
a identidade real de cada processo chamador.

## Critérios mínimos para o próximo teste de hardware

| Critério | Evidência exigida | Estado |
|---|---|---|
| Webcam em sessão Filhos desbloqueada | Frame válido sem gravar foto | Pendente no novo pipeline |
| Webcam durante Win+L | Captura consistente e WTS LOCKED | Diagnóstico anterior positivo; reproduzir |
| Webcam em contexto confiável | Captura pelo worker protegido, vinculada à mesma sessão | Não implementado |
| Reconhecimento dos três filhos | Enrollment local com autorização e perfis separados | Não implementado |
| Rejeição de pessoa desconhecida | Verificação negativa de rosto não cadastrado | Somente simulado |
| Rejeição de foto ou vídeo | Liveness real testado contra apresentação impressa/digital | Não implementado |
| Falha de câmera | Negação e recuperação sem desbloqueio | Somente simulado |
| Duas faces | Negação e reset da autorização | Somente simulado |
| Quota zerada e virada de dia | Persistência no SQLite protegido | Testado com dados simulados |
| Credencial do Windows | Autenticação segura no LogonUI, sem senha no processo infantil | Não implementado |
| Recuperação | Acesso admin intacto e rollback em VM com snapshot | Não implementado |

## Testes que podem continuar remotamente

- Testes de ACL, SQLite, WTS e conta SYSTEM em runner Windows descartável.
- Testes de host COM para Credential Provider sem registro.
- Regressão que mantém GetSerialization sem credenciais.
- Revisão do IPC para negar mensagens malformadas ou processos não autorizados.
- Análise e testes de transições de sessão, troca de criança e replay.

## Testes que não podem ser confirmados sem o PC físico

- Acesso contínuo à webcam específica após Win+L em contas infantis.
- Resiliência ao desligar ou desconectar fisicamente a webcam.
- Reconhecimento facial real e rejeição de ataques de apresentação.
- Comportamento com o Windows LogonUI e Secure Desktop no hardware alvo.

## Condições de segurança para futuros testes

1. Executar testes de câmera primeiro sem alterar login, registro ou senha.
2. Não salvar imagens ou vídeos por padrão; preferir apenas métricas técnicas.
3. Usar consentimento do responsável e realizar enrollment local.
4. Não instalar ou registrar DLL do Credential Provider no PC principal
   antes de rollback reproduzível em VM e validação de acesso admin.
5. Não afirmar que reconhecimento ou liveness reais estão prontos
   com base em bools simulados no código.

Este documento é uma lista de aceitação, não uma autorização para
instalar um autenticador no Windows da família.
