# FaceControlKidsPC — Roadmap de produto e homologação

**Referência:** 27/10/2026. **Projeto:** Windows primeiro; Linux/Regata OS
em trilha separada. **Branch de segurança:** `fix/facekids-ipc-security-hardening-20261024`;
[PR #4](https://github.com/marquimRcc/FaceControlKidsPC/pull/4) em **draft**.
Esta página consolida os checkpoints anteriores; não certifica hardware
nem substitui relatórios de homologação detalhados.

## Objetivo final

Uma **ou mais crianças** compartilham a conta Windows `Filhos`.
Cada perfil tem reconhecimento facial, quota, bônus e horários próprios.
Ao sentar diante da webcam, uma criança reconhecida poderá entrar/continuar
a sessão, com avisos de tempo e bloqueio ao se ausentar ou esgotar a quota.
A conta administrativa mantém entrada normal e recuperação independente.
O recurso de firewall/filtragem de conteúdos permanece fora do escopo atual.

No **ensaio físico inicial**, o rosto de um adulto voluntário é um
**perfil fictício** na conta `Filhos`, sem precisar de rostos de menores.

## Estado verificado

| Área | Situação | Limite da evidência |
|---|---|---|
| Painel dos Pais, 3 temas | Integrado à `main` pelo PR #5 | Não refazer |
| Cadastro de 1 ou mais perfis | Piloto Python generalizado para perfis configurados dinamicamente | Fluxos legados e instalador exigem revisão para retirar suposições de 3 perfis |
| YuNet/SFace | Implementação de detecção e comparação 1:N | Não implica liveness ou desbloqueio Windows homologado |
| Regras de quota, bônus, sessão e avisos | Implementadas; regressões sintéticas | Operação doméstica ainda usa agente legado escritor de SQLite |
| Serviço SCM, WTS, SID, IPC, saldo vinculado à identidade facial | Implementados e testados em laboratório isolado | SCM writer de VM recusa por projeto a base familiar |
| Débito exclusivo, recibos, backup SQLite WAL/rollback, NTFS | Testados em fixtures sintéticas e runner Windows | Cutover produtivo, VM interativa e recovery externo não homologados |
| Diagnóstico voluntário de rosto adulto na conta `Filhos` | Script pronto em `scripts/Iniciar-Teste-Adulto-Filhos.ps1` | Sem resultados da webcam física deste piloto |
| CI no SHA `96a9630b` | **339 unitários por plataforma e workflows nativos aprovados** | CI não captura webcam real nem valida LogonUI |

**Evidências de CI:** [Windows + Ubuntu](https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40264109787)
e [Credential Provider nativo](https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40264109763).

## Roadmap prioritário (sem estimativas artificiais)

### M0 — Base técnica e regressões [CONCLUÍDO NO LABORATÓRIO]
- Broker, SCM, contratos IPC, WTS, SID, testes de chamadas falsas.
- Writer protegido **apenas em VM**, recibos idempotentes, cutover e rollback sintéticos.
- Testes positivos/negativos em Windows e Ubuntu; pipeline nativo.
**Aceite:** CI verde no commit considerado, sem confundir mocks com biometria.

### M1 — Primeiro teste presencial com rosto adulto na conta Filhos [PRONTO PARA EXECUÇÃO]
- Executar [o roteiro de comando único](TESTE-REAL-ADULTO-FILHOS-20261026.md)
  no PowerShell normal da própria conta `Filhos`.
- Capturar 12 vetores adultos locais e obter `ROSTO_RECONHECIDO_DEMO`.
- Depois observar Win+L manual com relatório WTS + frames.
- Guardar apenas métricas de resultado, sem fotos, vetores, bancos ou senhas.
**Aceite:** correspondência positiva ao vivo e relatório Win+L conclusivo,
ou erro/limitação da webcam documentado como bloqueio real. O teste não faz
autologon e nunca altera quotas familiares.

### M2 — Câmera e sessão reais (capacidade e confiança) [PENDENTE]
- Verificar abertura da webcam USB, lock/unlock, troca de usuário,
  desconexão/reconexão e reinício.
- Verificar se captura sob serviço SYSTEM/Sessão 0 é tecnicamente possível;
  se não for, definir arquitetura de captura segregada e autenticação da origem.
- Testar ausência de rosto, duas faces, foto/vídeo e liveness com critérios
  realistas, sem presumir resistência só por desafio simulado.
**Aceite:** logs de casos reais, negativas seguras e limitações documentadas.
Sem confiança suficiente, não habilitar autologon.

### M3 — VM interativa recuperável [PENDENTE]
- Preparar VM Windows com snapshot **externo comprovadamente restaurável**.
- Testar login administrativo tradicional, falha proposital e restauração.
- Homologar Credential Provider e IPC dentro da VM, sem instalar no PC familiar.
- Ensaiar Win+L/LogonUI, alterações de sessão, falta de webcam e serviço parado.
**Aceite:** login convencional sempre recuperável; rollback realmente executado
e verificado, não somente descrito.

### M4 — Uma autoridade de quota e agente Filhos read-only [PENDENTE]
- Generalizar **todos os fluxos ativos** para um ou mais perfis; remover
  menus, mapeamentos e expectativas legadas de 3 perfis.
- Substituir no agente familiar a escrita direta por consulta ao serviço
  privilegiado, **sem fonte dupla de cobrança**.
- Banco/embeddings/SQLite WAL/SHM sob ACL adequada, backup consistente e
  migração supervisionada; teste com token `Filhos` não privilegiado.
- Reinício, troca de rosto, contagem por perfil e recuperação de falha.
**Aceite:** apenas o serviço debita; agente não altera SQLite; recibos,
saldos e rollback coincidem em testes VM reais; nenhum perfil é inventado.

### M5 — Desbloqueio/bloqueio facial integrado [PENDENTE]
- Fluxo Windows `Filhos` ao sentar, reconhecer, consultar quota e liberar.
- Bloquear por ausência/quota/horário; avisos de 10/5/1 min quando previstos.
- Tratar PIN manual, desconhecido, troca de criança e sessão bloqueada
  sem atribuir tempo ou identidade incorretamente.
- Conta administrativa permanece fora das regras automáticas.
**Aceite:** execução real de ponta a ponta na VM, mais cenários negativos,
sem dependência de credencial infantil enviada por IPC nem bypass acidental.

### M6 — Piloto doméstico e entrega estável [NÃO LIBERADO]
- Só depois dos portões anteriores: backup familiar e procedimento de reversão.
- Piloto assistido com rosto adulto, depois cadastros consentidos quando desejado.
- Conferir painel/3 temas, 1 ou mais perfis, quotas, reinício, mensagens,
  câmera indisponível e rotina de suporte.
- Harmonizar branch de segurança com `main` **somente após revisão e autorização
  explícita de merge**. Não fazer merges automáticos.
**Aceite:** uso doméstico repetível, reversível, sem risco de bloquear o admin.

## Próxima ação concreta

**M1:** executar o diagnóstico real do adulto na conta `Filhos`, sem elevar
privilégios e sem instalar novos componentes. Enviar somente as linhas
`RESULTADO:`, `Resumo:`, `MATCH_OBSERVED...` ou `NO_USABLE...`;
jamais imagens ou biometria. Em paralelo, preparar M3 e investigar M2
sem precisar de hardware infantil adicional.

## Impeditivos estruturais e premissas

1. **A webcam real ainda não foi observada nesta branch como prova de
   desbloqueio seguro**; o positivo sintético não cobre Sessão 0 e LogonUI.
2. **Writer familiar ainda é legado**: novo serviço é VM-only e não pode ser
   instalado apontando para o banco doméstico.
3. **Snapshot de VM interativa não validado fisicamente**; testes hosted
   Windows comprovam apenas o laboratório descartável.
4. **Generalização 1+ foi aplicada ao piloto**; código e scripts antigos podem
   ainda conter suposições de três perfis. Não declarar sistema inteiro
   generalizado sem auditoria completa.
5. **PR #4 é draft e sua base não é `main`**: integrar requer análise de
   conflitos e testes, preservando interface do PR #5.
6. Não instalar, registrar, atualizar ou remover Credential Provider/serviço
   no PC familiar por comandos deste roadmap; não agendar automações.

## Fontes técnicas da própria branch

- [Progresso autônomo](PROGRESSO-AUTONOMO.md)
- [P0-1 a P0-5 / cutover VM](P0-1-A-P0-5-CUTOVER-VM-20261025.md)
- [Homologação SCM / quotas](HOMOLOGACAO-VM-SCM-WRITER-20261025.md)
- [Aceite de segurança Windows](ACEITE-SEGURANCA-WINDOWS.md)
- [Teste real do responsável na conta Filhos](TESTE-REAL-ADULTO-FILHOS-20261026.md)

**Critério de honestidade:** cada marco fica “concluído” apenas no ambiente
efetivamente testado. Aprovação do GitHub Actions não aprova câmera, liveness,
login real, quota doméstica ou rollback externo.
