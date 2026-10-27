# FaceKids VM — Passo 2: snapshot e recuperacao antes do Credential Provider

**Branch:** developer | **Status:** verificador somente leitura. Nao instala DLL, SCM ou tarefas.

## Estado confirmado em teste manual

- Webcam XWF-1080P funcional no VirtualBox com xHCI.
- Rosto adulto cadastrado, 12 amostras; conta Filhos criada e habilitada.
- Auth worker PID 8060 na ultima verificacao relatada.
- FaceKidsAuthPipe PONG; reconhecimento ALLOW, perfil 1, saldo 7200 segundos.
- Credential Provider ausente do Windows.

Os snapshots anteriores foram feitos antes de a conta Filhos e o worker estarem
prontos. Exige-se NOVO snapshot para essa etapa.

## A. Verificador de precondicoes — dentro da VM

Na conta administrativa Marcos, execute no PowerShell:

~~~powershell
irm 'https://raw.githubusercontent.com/marquimRcc/FaceControlKidsPC/developer/scripts/Validar-Passo2-FaceKids-VM.ps1' | iex
~~~

Checagens somente leitura: VirtualBox, contas habilitadas, administradores locais,
paths do banco/modelos/DLL fonte, PID e SID do worker, CP nao registrado.
A senha de Filhos NAO e consultada nem testada.
Snapshot no host e login por senha sao evidencias MANUAIS e nunca ficam
automaticamente aprovados por esta etapa.
Se houver ATENCAO, nao executar ActivateCP.

## B. Criar snapshot novo — no VirtualBox do HOST

1. Dentro da VM, salve seu trabalho e faca Iniciar > Desligar normalmente.
2. No VirtualBox Manager do computador host, selecione VM > Snapshots.
3. Clique Take/Criar e nomeie: pre-CP-FaceKids-Filhos-2026-10-27.
4. Descricao: Windows 10 Pro, Filhos presente, webcam xHCI, 12 amostras,
   sem Credential Provider, login administrativo convencional.
5. Inicie a VM novamente e entre como Marcos pelo metodo tradicional.
6. Confirme que o novo snapshot aparece no host.
7. Se restaurar para comprovar recuperacao, observe que a restauracao elimina
   alteracoes feitas DEPOIS do snapshot; nao deixe dados novos a perder.
   Comprove a entrada administrativa e os cadastros apos a restauracao.

O snapshot com VM ligada tambem e possivel, mas esta recomendacao escolhe
shutdown normal, sem depender de memoria/driver de webcam congelados.

## C. Login de recuperacao e senha de Filhos (manual)

- Comprove que Marcos entra normalmente por senha/PIN, sem FaceKids.
- Verifique que Filhos entra por SENHA Windows (nao apenas PIN).
- A DLL legada usa a senha fixa 1 para Filhos, somente na VM de teste.
- Nao compartilhe senhas nem as inclua em prints, logs ou arquivos.
- Se a senha de Filhos nao for a esperada, nao instale o CP.
- Confirme acesso ao Gerenciador do VirtualBox e a opcao de restaurar snapshot
  mesmo se o login da VM vier a ficar indisponivel.

## D. Religou a VM? Reiniciar apenas worker interativo e testar

Na conta Marcos, PowerShell:

~~~powershell
$p="$env:LOCALAPPDATA\FaceKids-VM-Lab\scripts\FaceKids-VM-Autenticacao.ps1"; powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p -Action RestartAuth; if ($LASTEXITCODE -eq 0) { powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p -Action Ping }
~~~

E para confirmar o rosto:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\FaceKids-VM-Lab\scripts\FaceKids-VM-Autenticacao.ps1" -Action FaceProbe
~~~

Criterio para o proximo passo: snapshot novo + recuperacao administrativa,
senha de Filhos manualmente comprovada, CP ausente, PONG e ALLOW com saldo.

NÃO execute ActivateCP no passo 2. A instalacao do CP e rollback serao
tratados separadamente. Este teste nao prova camera em SYSTEM/Session 0,
cold boot ou instalacao domestica. Main permanece intocada.
