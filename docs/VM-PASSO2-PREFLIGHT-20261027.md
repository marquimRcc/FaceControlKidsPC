# FaceKids VM — Passo 2: preparo do login facial (somente laboratorio)

**Branch:** developer. Este passo NAO registra DLL, altera senha, cria servicos
ou inicia automaticamente um login Windows.

## Situacao confirmada

- VM Windows 10 Pro no VirtualBox; webcam XWF-1080P funcionando.
- Conta administrativa Marcos; conta de teste Filhos habilitada.
- Cadastro facial de adulto com 12 amostras no banco isolado da VM.
- Autenticador interativo iniciado sem console visivel (ultimo PID informado: 8060).
- FaceKidsAuthPipe respondeu PONG e AUTH_QUERY identificou perfil 1 com ALLOW.
- Credential Provider ainda nao registrado.

## 1. Validacao automatica somente leitura

Na conta Marcos, abra PowerShell e execute:

~~~powershell
irm 'https://raw.githubusercontent.com/marquimRcc/FaceControlKidsPC/developer/scripts/Validar-Passo2-FaceKids-VM.ps1' | iex
~~~

Verifica: ambiente VirtualBox, contas habilitadas, privilegios da conta
administrativa, banco facial isolado, executavel do worker e SID correspondente,
DLL fonte e ausencia de Credential Provider instalado.

O comando NAO solicita, le ou valida senhas. Um aviso ATENCAO significa
que o instalador do proximo passo NAO deve ser executado ainda.

## 2. Confirmacoes manuais antes de mexer no LogonUI

1. Verifique que consegue entrar na conta administrativa Marcos por
   senha/PIN comum, sem depender do FaceKids.
2. Verifique que a conta Filhos faz login usando a senha do Windows,
   e nao somente o PIN. A DLL legada atual usa senha de teste fixa 1.
   Se Filhos possuir outra senha, NAO ative a DLL ainda.
3. Nao compartilhe senhas, nem inclua credenciais em capturas ou logs.
4. Verifique que o worker permanece ativo em segundo plano. Ele pode
   parar ao encerrar a sessao administrativa porque ainda nao e SCM.

## 3. Teste atual sem instalar nada

~~~powershell
$p="$env:LOCALAPPDATA\FaceKids-VM-Lab\scripts\FaceKids-VM-Autenticacao.ps1"; powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p -Action Ping; if ($LASTEXITCODE -eq 0) { powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p -Action FaceProbe }
~~~

Esperado: PONG, seguido de ALLOW e quota positiva.

## 4. Proximo passo (separado)

Somente depois das verificacoes anteriores: registrar a DLL do Credential
Provider com PowerShell administrativo, com os dois reconhecimentos manuais
de conta recuperavel e senha esperada (-RecoveryConfirmed e
-FixedPasswordConfirmed). A rotina vai revalidar a webcam e o IPC no ato
do registro e manter o metodo tradicional de login do Windows.

Rollback direcionado da instalacao de laboratorio:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\FaceKids-VM-Lab\scripts\FaceKids-VM-Autenticacao.ps1" -Action Rollback
~~~

A DLL nativa depende de um worker interativo enquanto a sessao
administrativa estiver conectada. Este ensaio nao garante login automatico
apos cold boot, Session 0 ou substituicao do writer de quotas.

**Main nao e modificada. Uso restrito a VM descartavel.**
