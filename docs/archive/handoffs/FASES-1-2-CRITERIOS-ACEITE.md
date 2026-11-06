# Fases 1 e 2 — Critérios verificáveis

Objetivo: 3 filhos em uma conta Windows Filhos, cada um com 7.200
segundos por dia, identificados individualmente pelo rosto.

A Fase 1 tem componentes de software implementados e validados
sinteticamente, mas NÃO está aprovada para hardware real:

- P0-43: worker LocalSystem controla inventário; captura real segura pendente
- P0-44: diagnóstico Win+L pronto; prova física pendente
- P0-45: matching SFace em SQLite protegido; cadastro real pendente
- P0-46: consenso de três candidatos; validação física pendente
- P0-47: desafio de movimento é diagnóstico; liveness real pendente

A Fase 2 prossegue sem depender da conclusão física:
- P0-48: cruzamento do candidato facial, SID/WTS e quota
- P0-49: uso único e expiração de 8s, atualmente simulado
- P0-50: medidor monotônico, atualmente simulado
- P0-51: política de bloqueio por criança, somente dry-run

Todos os resultados de reconhecimento, consenso, movimento e
candidato de bloqueio deixam o login real desabilitado.

Teste físico opcional, após atualizar o clone da branch, em
PowerShell normal a partir da raiz do projeto:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\Testar-Camera-WinL.ps1"

Nenhuma imagem ou vídeo é salvo. Não instalar DLL de login ou
alterar credenciais antes de validar a recuperação da VM.
