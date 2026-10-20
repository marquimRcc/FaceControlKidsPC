# FaceControlKidsPC — Checkpoint de desenvolvimento autonomo

> Documento de retomada da branch `feature/windows-native-unlock-poc`.
> Atualizar apos cada ciclo. Nao confundir testes sinteticos com login facial real.
> A `main` nao deve ser alterada nem mesclada sem ordem explicita.

## Ultima entrega — 20/10/2026

Etapas tecnicas realizadas nesta rodada:

| Etapa | Mudanca concreta | Prova automatizada |
|---|---|---|
| P0-21 | Validacao de data civil e limite acumulado de bonus no WinSQLite nativo | Tests de broker e SCM Windows |
| P0-22 | Teste real de mensagem binaria invalida no named pipe retorna DENIED | Workflow Windows broker IPC |
| P0-23 | PRAGMA quick_check verificado antes de inicializar o ledger; arquivo SQLite invalido recusado | Testes de host e SCM Windows |
| P0-24 | SFace rejeita vetores NaN, infinito, zerados e dimensoes invalidas | Testes de reconhecimento Python Windows/Linux |
| P0-25 | Storage Python igualou teto de bonus por crianca/dia (480 min) | Testes de Storage Windows/Linux |

Comprovacoes GitHub Actions:
- C++/SCM apos controle de integridade: runs 39447068762 e 39447068788
- Teste de input de protocolo: run 39446548826
- Testes de novos vetores faciais: run 39447476627
- Testes Python com regras de bonus: run 39447759390

Os workflows acima podem levar alguns instantes a terminar na ocasiao
do commit. Nao afirmar que um workflow em andamento passou por completo
antes de conferir sua conclusao.

## Baseline mantida

- Broker C++ protegido, executado como LocalSystem apenas no runner de teste
- Credenciais Windows nunca sao serializadas pelo Credential Provider de diagnostico
- Login real e registro da DLL COM continuam desativados
- Quotas SQLite persistentes por 3 perfis e WTS/SID isolados
- Webcam no broker: apenas inventario/estado; NAO prova reconhecimento ou liveness
- Testes de camera Win+L anteriores vieram de um processo interativo da conta Filhos,
  nao de uma captura comprovadamente confiavel em LogonUI

## Proximas etapas em ordem

1. **P0-26: fronteira de captura confiavel.** Projeto e testes de um worker
   de video isolado com origem verificavel. Nao promover flags recebidas da
   conta Filhos a verdades do broker. Nenhum ticket de login neste estagio.
2. **P0-27: auditoria de dados biometricos.** Cadastro/descarte local,
   diretorio seguro, minimizacao, consentimento parental e protecao da
   conta administrativa. Sem capturar imagem infantil em GitHub Actions.
3. **P0-28: teste em hardware.** Medir se um worker confiavel consegue
   abrir e ler a camera no contexto real do Windows bloqueado.
4. **P0-29: testes de ataques de apresentacao.** Rejeicao de foto, video e
   duas faces com liveness valido, comprovado em equipamento real.
5. **P0-30: VM com snapshot e rollback.** Credencial de Windows e
   serializacao COM apenas depois de ter recuperacao comprovada.

## Padrao para cada execucao autonoma

1. Ler este checkpoint e HEAD atual no GitHub; nao repetir trabalho entregue.
2. Escolher **varias subtarefas relacionadas**, nao um commit isolado.
3. Escrever codigo e testes negativos; rodar GitHub Actions e corrigir falhas.
4. Atualizar o checkpoint com commit, provas verificadas e pendencias.
5. Comunicar "etapa X concluida; avancando para Y" durante o ciclo.
6. Parar somente por limite de duracao ou bloqueio verdadeiro (por exemplo,
   hardware fisico sem acesso). Uma automacao horaria retoma no ciclo seguinte.
7. Nunca executar procedimentos de login experimentais no computador familiar.

## Fora do escopo de provas ate nova evidencia

Nenhum resultado de testes simulados confirma protecao contra falsificacao
de rosto, liveness efetivo, acesso ao Secure Desktop ou desbloqueio Windows.
