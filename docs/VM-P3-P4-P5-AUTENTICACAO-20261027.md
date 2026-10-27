# FaceKids - P3/P4/P5: autenticacao controlada na VM

Branch: developer. Nao foi instalado nada pelo ChatGPT dentro da sua VirtualBox.
O script esta em scripts/FaceKids-VM-Autenticacao.ps1.

## Ambiente e dados ja homologados

- VM VirtualBox Windows 10 Pro; XWF-1080P funcional em xHCI.
- Conta Filhos ativa e separada da conta administrativa Marcos.
- Cadastro de rosto adulto como perfil ficticio (12 amostras), reconhecimento no preview.
- Base VM: %LOCALAPPDATA%\FaceKids-VM-Lab\dados-isolados\data\criancas.sqlite3.
- Snapshots antes/depois do cadastro documentados e restaurados.
- Nenhum servico, tarefa, DLL ou Credential Provider instalado no diagnostico anterior.

## Limite da arquitetura

A fase StartAuth inicia o Python facekids.auth_service na sessao administrativa interativa.
NAO e servico SCM, nao persiste antes do primeiro login e nao comprova camera em Session 0.
O modulo quota_broker_writer_scm_win.py e um OUTRO servico, exclusivo de fixtures sinteticas.
A DLL legada usa a senha fixa Windows "1" de Filhos; este script nao altera a senha nem tenta verifica-la por login.
Nao confundir reconhecimento ALLOW com desbloqueio do Windows.

## Comandos em ordem, na conta administrativa da VM

Obter script e ver estado (sem alterar o login):

~~~powershell
$p=Join-Path $env:TEMP 'FaceKids-VM-Autenticacao.ps1'; Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/marquimRcc/FaceControlKidsPC/developer/scripts/FaceKids-VM-Autenticacao.ps1' -OutFile $p; powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p -Action Status
~~~

Iniciar worker, testar IPC e reconhecimento facial:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\FaceKids-VM-Autenticacao.ps1" -Action StartAuth
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\FaceKids-VM-Autenticacao.ps1" -Action Ping
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\FaceKids-VM-Autenticacao.ps1" -Action FaceProbe
~~~

Esperado: listening, PONG, ALLOW com saldo positivo. O FaceProbe oculta a senha do protocolo.
Se falhar, NAO registre CP; confira vm-auth-err.log e vm-auth-status.json dentro do workspace.
Deixe somente o rosto cadastrado na webcam, e nao abra simultaneamente o aplicativo Camera do Windows.

## Ativacao opt-in do Credential Provider

Somente depois de:
1. Confirmar snapshot externo RESTAURADO e login administrativo por senha/PIN.
2. Confirmar que Filhos possui de fato a senha Windows "1" usada pela DLL atual.
3. Ter Ping e FaceProbe aprovados, com o worker da conta administrativa ativo.
4. Abrir PowerShell x64 COMO ADMINISTRADOR dentro da VM.

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\FaceKids-VM-Autenticacao.ps1" -Action ActivateCP -SnapshotConfirmed -RecoveryConfirmed -FixedPasswordConfirmed
~~~

O script revalida rosto ALLOW, registra o CP somente se o CLSID estiver ausente, e
impõe correspondencia do SID do worker via HKLM. Copia DLL para ProgramData\FaceKids-VM-CP-Lab,
nunca para ProgramData\FaceKids. Nao bloqueia nem faz logout automaticamente.
Depois testar Win+L na conta Filhos mantendo a sessao administrativa logada,
com login convencional disponivel para emergencia. Se o worker cair, CP deve negar.

## Rollback direcionado na VM

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\FaceKids-VM-Autenticacao.ps1" -Action Rollback
~~~

Remove APENAS registro CP marcado como pertencente ao laboratorio e encerra
o worker rastreado pelo proprio script. Preserva dados faciais/SQLite e main.
Se nao conseguir entrar no Windows, use o snapshot externo do VirtualBox.

## Portoes ainda abertos

- Validar camera durante Win+L e troca de sessao (nao equivale a Camera do Windows).
- Validar CP realmente apresentado, senha Filhos correta e fallback administrativo.
- Homologar Session 0/LocalSystem e eventual SCM em VM com webcam fisica.
- Comprovar cold boot, ausencia de worker, webcam removida e recuperacao.
- Substituir senha fixa e mecanismo legado antes de qualquer implantacao real.
- Homologar transicao de quota em SQLite protegido sem escritor simultaneo.
- Manter main intocada e nao executar o instalador domestico legado.

CI: parse PowerShell, testes de integridade da etapa e deteccao de operacoes
de risco; CI nao comprova funcionamento fisico do Windows LogonUI.
