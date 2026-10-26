# Piloto presencial: rosto adulto como perfil fictício na conta Filhos (26/10/2026)

Branch exclusiva: `fix/facekids-ipc-security-hardening-20261024`, PR #4 draft. **Não instalar** o Credential Provider,
serviço SYSTEM ou novo broker no computador familiar nesta etapa.

## Escopo

O sistema deverá aceitar **uma ou mais crianças** configuradas, com quota e
biometria individual por perfil, compartilhando a conta Windows `Filhos`.
Não deve haver três slots obrigatórios. Os três perfis usados nos testes
anteriores são apenas dados sintéticos de regressão.

Para teste presencial, o responsável voluntário pode usar **o próprio rosto**
como **um único perfil fictício**, sem requisitar fotos/rostos de crianças.
O teste salva 12 vetores numéricos **biométricos do adulto** somente na conta
Windows `Filhos`, em
`%LOCALAPPDATA%\FaceKids\laboratorio-adulto-filhos\adulto-teste.sqlite3`.
Não armazena foto/vídeo persistente nem altera o cadastro da conta adulta ou o
banco real `C:\ProgramData\FaceKids\criancas.sqlite3`. Esse banco de
laboratório **não tem ACL de serviço SYSTEM**: deve ser apagado após o ensaio.

## Um comando — executar em PowerShell NÃO elevado na conta Windows Filhos

```powershell
& { $b='fix/facekids-ipc-security-hardening-20261024'; $p=Join-Path $env:LOCALAPPDATA 'FaceKids\codigo-laboratorio-adulto'; if (!(Test-Path "$p\.git")) { git clone --depth 1 --branch $b https://github.com/marquimRcc/FaceControlKidsPC.git $p } else { git -C $p pull --ff-only origin $b }; if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar branch de seguranca' }; & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$p\scripts\Iniciar-Teste-Adulto-Filhos.ps1" -WinL }
```

Requer Git e Python 3.11–3.13 (`py.exe`). O script prepara `.venv`, instala
OpenCV/numpy ali quando necessário e baixa modelos públicos YuNet/SFace se
ausentes. Não solicita elevação. Recusa contas distintas de `Filhos` e
tokens com papel Administrador.

1. Abre webcam; somente um adulto voluntário diante dela. Captura 12 vetores
   para o cadastro fictício isolado e testa reconhecimento ao vivo por 60 s.
   Para interromper, ESC/Q. Se não houver reconhecimento confirmado, encerra
   sem tentar Win+L.
2. Com `-WinL`, abre um diagnóstico de **leitura** do rosto no bloqueio:
   pressione **Win+L você mesmo**, fique na frente da câmera por 40–60 s
   e entre com o **PIN/senha Windows habituais** para ver o resumo.
   O programa **não desbloqueia Windows**, não altera a credencial nem
   registra tarefas/serviços.
3. Anote e compartilhe **somente** as linhas `RESULTADO:`, `Resumo:`,
   `MATCH_OBSERVED...` / `NO_USABLE...` e eventuais mensagens de erro
   (redigindo nomes, caminhos locais e SIDs). Não enviar fotos nem banco.

Para testar apenas cadastro/reconhecimento sem Win+L, repita o comando sem
`-WinL` na invocação final. Para recadastrar, acrescente `-ReEnroll`.

## Critérios e limitações

- Teste positivo ao vivo: `ROSTO_RECONHECIDO_DEMO` (3 frames confirmados).
- Teste positivo no bloqueio: `MATCH_OBSERVED_DURING_WIN_L_DIAGNOSTIC_ONLY`,
  **não** prova liveness nem capacidade de desbloquear LogonUI, pois a captura
  pertence ao processo já autenticado na conta `Filhos`.
- `NO_USABLE_LOCKED_FRAMES` ou `INCONCLUSIVE_...` não liberam mudança
  de login, não significam erro na conta Windows e podem exigir outra
  arquitetura para câmera em sessão 0.
- O serviço protegido de cobrança SCM/IPC do PR #4 continua VM-only;
  não será ativado na instalação familiar por esse teste. Quotas reais
  permanecem intocadas.
- Se o FaceKids instalado já estiver usando a câmera ou realizar login
  automático por outro componente existente, resultados Win+L podem ser
  inconclusivos; **não force a remoção de login/serviços para este teste**.

Para descartar apenas biometria do **piloto do adulto na conta Filhos**,
depois de fechar câmera/teste:
```powershell
Remove-Item -LiteralPath (Join-Path $env:LOCALAPPDATA 'FaceKids\laboratorio-adulto-filhos') -Recurse -Force
```
Esse comando de descarte é **opcional e manual**; nunca limpa o banco familiar.

## Regressões

Testes existentes de 3 perfis continuam como fixture legado; o novo
`configured_child_profiles` do `ChildQuotaEngine` lê perfis configurados
dinamicamente e exige pelo menos um. O CLI de piloto permite `add-profile`
e IDs positivos sem limite fixo. O workflow Windows testa 1 e 5 perfis
sintéticos, além de verificar sintaxe do novo launcher; Ubuntu executa os
testes unitários dinâmicos.
