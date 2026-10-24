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

## Fila e riscos remanescentes
1. Conferir GitHub Actions do HEAD, sobretudo build-real-credential-provider e TestPipeClient.exe. Corrigir qualquer falha.
2. Reforcar validacao de JSON duplicado/malformado com parser correto, em alteracoes pequenas e testadas.
3. Restringir SDDL do pipe sem interromper cliente LogonUI; testar tokens e comportamento em VM descartavel.
4. Revisar o instalador: permissao Modify em ProgramData, senha em argumentos e preservacao da instalacao funcional.
5. Verificar continuidade do processo na troca de sessao/reboot antes de alterar a inicializacao.
6. Testes fisicos de webcam, anti-spoof e desbloqueio real exigem intervencao voluntaria do proprietario. Nao instalar componente nativo no PC familiar nesta branch.
