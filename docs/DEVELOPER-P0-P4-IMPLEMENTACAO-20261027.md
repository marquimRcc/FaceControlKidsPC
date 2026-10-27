# FaceKids `developer` — P0 a P4: integração e limites de homologação

**Data:** 27/10/2026. **Alvo:** `developer` derivada da `main`
`4f2ec165`. **NÃO implantado no computador familiar; nenhuma alteração da main.**

## Invariantes da `main` preservados

- Uma ou mais crianças; sem cardinalidade fixa de três.
- Perfil atual mantém prioridade se reconhecido entre as faces.
- Teclado/mouse usado nos últimos 15s mantém o operador atual.
- Múltiplos rostos bloqueiam trocas de perfil em sessão.
- Troca para uma face única quando o operador anterior não é detectado
  e há inatividade de pelo menos 15s; sessão ainda sem perfil pode adotar
  sua primeira identificação sem esperar 15s.
- Inatividade efetiva `min(GetLastInputInfo, idade da sessão desbloqueada)`
  e bloqueio/reembolso legado de até 120s.
- Painel, fotos oficiais, boas-vindas, launcher/Tcl e boot da main não foram
  substituídos. Credential Provider C++ permanece fora deste lote.
- O serviço SCM de cobrança protegida continua exclusivamente em VM sintética.

## P0 — Fronteiras de confiança e sinais de desbloqueio

**Mudanças:**
- Criado `SESSION_QUERY` para a verificação facial periódica. `AUTH_QUERY`
  continua compatível com o Credential Provider de desbloqueio.
- O reconhecedor recebe `publish_unlock_event=False` na sessão e na
  recaptura do broker; não escreve `last_unlock.json`, avatar ou senha no
  retorno da observação. Apenas o caminho legado de unlock pode gerar o
  arquivo de conveniência de UI.
- `last_unlock.json` passou a disparar **somente interface**: não troca o
  perfil debitado e não redefine o temporizador de inatividade. Transições
  LOCKED->ACTIVE observadas pelo agente redefinem o temporizador; perfis
  passam a ser escolhidos apenas pelo caminho controlado de observação.
- ALLOW, DENY_QUOTA e DENY_CURFEW agora exigem envelope coerente, evento
  recente, IDs reais, nomes, saldo, contagem facial e candidatos consistentes
  antes de qualquer troca/bloqueio derivado de câmera; perfis precisam
  existir no banco. As demais regras locais de curfew/quota permanecem.

**Limitação crítica:** o marcador do envelope não autentica criptograficamente
o servidor Named Pipe. A identidade do pipe para o agente interativo ainda
precisa de verificação de origem/ACL e testes Windows. O arquivo UI pode
ser falsificado para exibir saudação; isso não autoriza a troca de quota.

## P1 — Decisão de sessão pura e centralizada

Novo `facekids/session_transition_policy.py` e testes parametrizados
incluindo dados malformados, face secundária, jogador ativo, múltiplas faces,
ausência de perfil, limiar exato de 15s e observação expirada. `filhos_agent`
invoca diretamente a mesma função para ALLOW e para transições DENY.
Há um único local de decisão de identidade na sessão.

## P2 — Recorte correto de rosto

`auth_service.py` conserva a box da face cujo embedding realmente produziu
o `child_id` reconhecido. Não usa a maior face indiscriminadamente. Teste
sintético: desconhecido maior + criança conhecida menor; a foto da criança
recebe a box menor.

## P3 — Estorno protegido idempotente (somente primitiva, **não ativado**)

`Storage.refund_capped_once(event_id,session_epoch,person_id,seconds,charge_event_ids,day)`:
- serviço deve emitir os IDs e epoch; **nunca aceitar do IPC infantil**;
- requer recibos de ticks já debitados para mesmo perfil e mesmo dia;
- teto de 120s, saldo usado real, teto por somatório dos ticks originais;
- cada tick pode ser associado no máximo a um estorno, impedindo
  reutilização com outro ID;
- uma devolução por epoch/desbloqueio + criança + dia;
- `BEGIN IMMEDIATE`, recibos e vínculos duráveis; replay exato retorna 0;
  evento reaproveitado com payload ou ticks diferentes falha;
- preserva `Storage.refund()` legado somente enquanto este ainda for
  único escritor; writer VM-only impede `refund()` não privilegiado.

**Ainda precisa:** origem independente da ociosidade de mouse/teclado,
persistência e manutenção confiável do epoch pelo serviço, e ligação
do estorno ao SCM writer. Ter recibo não prova que a alegação de
inatividade enviada por um processo `Filhos` é verdadeira.

## P4 — Recaptura de face sem cobrança nem revogação prematura

- O binder pausa a cobrança, mantendo a última identidade comprovada.
- Durante captura `RECHECKING` não há débito.
- Se falha transitória de câmera/rosto e sessão WTS inalterada, carência
  limitada a 30s SEM débito; expirado o prazo, o lease é revogado.
- Mudança, lock, logoff e desconexão WTS invalidam o lease sem tolerância.
- Curfew e quota esgotada têm precedência e revogam a tolerância.
- ALLOW legítimo restaura um lease com relógio novo; não soma o período
  suspenso. Evidência em testes sintéticos de clock/WTS.
- Não confundir carência não faturada com autorização biométrica renovada.

**Ainda precisa:** testes com WTS/SCM e webcam físicos/VM interativa,
retomada de sessão, camera contention e LogonUI; não implantar o writer
no computador familiar.

## Testes e próximos portões

- `tests/test_session_transition_policy.py`
- `tests/test_p0_p2_face_integration.py`
- `tests/test_developer_integration.py`
- `tests/test_protected_refund.py`
- `tests/test_face_recheck_grace.py`
- `tests/test_scm_face_recapture_contract.py`
- suites antigas de storage, auth, agente, broker, WTS e native CP.
- CI Windows/Ubuntu e Linux Regata. Resultados disponíveis em
  https://github.com/marquimRcc/FaceControlKidsPC/actions?query=branch%3Adeveloper

**NÃO promover a main ainda:** homologação em VM com snapshot/rollback,
revisão de confiança dos Named Pipes, possível conflito de captura USB,
serviço idempotente com ociosidade comprovada, instalação e ACL segregadas
e teste de recuperação administrativa são portões obrigatórios.

Nenhum merge para `main`, nenhum SCP/SCM/credential provider instalado,
nenhuma ACL de máquina física alterada.
