# FaceKids — Segurança incremental (24/10/2026)

## Escopo e origem
- Base: handoff/facekids-auto-unlock-stabilization-20261021.
- Branch exclusiva: fix/facekids-ipc-security-hardening-20261024.
- Main e branch de origem nao alteradas.
- Preservar fluxo de desbloqueio facial informado pelo proprietario como funcional; nao instalar/testar Credential Provider no PC familiar.

## Entregas deste ciclo
1. cb02de5212b3bb0cc0ffcfeecaa4affdcf691999 — FaceKidsPipeClient.h: rejeicao de lixo apos numeros de child_id/timestamp e protecao da conversao de saldo fora da faixa int.
2. b1af4e064b0fdc58e6a132a78d944b870ea9c622 — TestPipeClient.cpp: casos negativos adicionais para IDs adulterados, timestamp com sufixo e saldo excessivo.

## Verificacao
- Inspecao de conteudo remoto dos arquivos: realizada.
- Compilacao/execucao Windows: NAO verificada neste ciclo.
- GitHub Actions desta branch: NAO confirmado; aguardar jobs e corrigir falhas antes de aprovar qualquer integracao.
- Nenhum teste deste ciclo comprova liveness, camera segura ou Winlogon.

## Rodada adicional — 24/10/2026
- 60dfdda688b575e6c808f0278ea1ce1e20387dc1: ALLOW exige quota positiva e representavel; child_id em decimal canonico.
- ee8718b3e59b4c3e0a9dd624d42fee72a92af94b: casos negativos para quota nula, negativa, malformada, overflow e ID com zero inicial.
- Testes C++ foram adicionados, mas ainda nao ha evidencia verificada de compilacao/execucao desta branch.
- Nao houve alteracao no SDDL, instalador, senha, Provider COM nem registro de componentes.

## Fila e riscos remanescentes
1. Conferir GitHub Actions do HEAD, sobretudo build-real-credential-provider e TestPipeClient.exe. Corrigir qualquer falha.
2. Reforcar validacao de JSON duplicado/malformado com parser correto, em alteracoes pequenas e testadas.
3. Restringir SDDL do pipe sem interromper cliente LogonUI; testar tokens e comportamento em VM descartavel.
4. Revisar o instalador: permissao Modify em ProgramData, senha em argumentos e preservacao da instalacao funcional.
5. Verificar continuidade do processo na troca de sessao/reboot antes de alterar a inicializacao.
6. Testes fisicos de webcam, anti-spoof e desbloqueio real exigem intervencao voluntaria do proprietario. Nao instalar componente nativo no PC familiar nesta branch.


## Rodada de estabilizacao — 24/10/2026 (continuidade)

- `40936539064fd4c3f3d48e6de739f8e8c0409ba1`: evita falso positivo de testes negativos por falta de quota; adiciona caso positivo com quota realista.
- `e55ce6dff76c0e35a6dcc7b062331cf6948858ea` e `bc454f2943f89532c99c56dc5c9109d035f30ed6`: o servico facial nao inclui senha na resposta; assertiva Python de privacidade. O Credential Provider segue com sua logica de credenciais, sem alteracao funcional.
- `0027cbf370347552014f056d5c167460b64da315`: validador isolado de sintaxe JSON, chaves duplicadas, profundidade e limite 2047 bytes.
- `9a2ab01df4224e9f25ce40eb535555c00ad1513d`: resposta negada quando envelope nao for JSON valido e nao ambiguo.
- `e732f8261398324cc2606031d8f6e04eed26e669`: regressao contra duplicatas, lixo, truncamento e caso valido aninhado.
- `2138276509ab354e48870db997cd225a06e80241`: impede confusao entre campo textual e numerico nos campos de autorizacao do envelope.
- `73c765402f007a80bef3ed218891cf6320023b7f`: casos negativos de tipos incorretos no parser C++.

### Evidencia efetivamente executada
- Validador C++ puro, em harness isolado Linux `g++ -std=c++17 -Wall -Wextra -Werror -pedantic`: **3 casos validos e 14 casos invalidos aprovados**. Esse teste executou apenas o validador independente, NAO compilou/rodou a DLL Windows e NAO executou o TestPipeClient completo.
- Codigo/testes Python e C++ publicados na branch. Nao houve execucao local da suite completa nem de webcam real.
- Consulta GitHub Actions para o commit `73c7654`: a integracao retorna lista vazia de workflows (a consulta desse conector e limitada a runs de pull request) e nenhum status combinado. **CI Windows/Python nao confirmado**; nao tratar lista vazia como sucesso ou como evidencia de ausencia de workflows.
- O codigo nao alterou `main`, instaladores, tarefas, registro COM ou dispositivos.

### Pendencias imediatas
1. Inspecionar o workflow `Credential Provider compile and host checks` e o `Unit tests` por commit/branch no GitHub; executar e corrigir ate ficarem verdes.
2. Validar o fluxo autorizado e o fluxo de negacao do IPC no Windows virtualizado antes de integrar qualquer mudanca na instalacao funcional do PC familiar.
3. Auditoria e ensaios em VM para ACL do Named Pipe e NTFS ProgramData: nao endurecer cegamente antes de medir a identidade do cliente LogonUI e os acessos necessarios do agente.
4. Liveness, camera no Secure Desktop e resistencia anti-spoof nao sao comprovadas por estes testes sinteticos.
