# FaceKids `developer` — iniciar laboratório da VM com uma linha

**Importante:** executar somente no PowerShell de uma **VM Windows 11 descartável**, com uma conta administrativa convencional, após criar e testar um snapshot no hipervisor.

## Comando único

```powershell
irm https://raw.githubusercontent.com/marquimRcc/FaceControlKidsPC/developer/scripts/Iniciar-FaceKids-VM-Developer.ps1 | iex
```

O comando baixa e executa o script versionado em
`scripts/Iniciar-FaceKids-VM-Developer.ps1`, que:

1. Confere que o Windows apresenta indicadores de máquina virtual e que a conta não é `Filhos`.
2. Baixa o ZIP da branch `developer` do GitHub, sem exigir Git instalado.
3. Prepara Python 3.11/Tk (via `winget`, caso necessário), `.venv`, OpenCV e NumPy.
4. Tenta baixar e verificar os modelos faciais YuNet/SFace.
5. Executa preflight P6, testes unitários e uma leitura breve da câmera interativa (quando disponível).
6. **Abre automaticamente o Painel dos Pais** com um banco de dados de laboratório, permitindo cadastrar **um ou mais perfis**, inclusive um rosto adulto voluntário.

O laboratório é separado em `%LOCALAPPDATA%\FaceKids-VM-Lab`:
- `codigo-developer`: arquivos do GitHub;
- `.venv`: dependências do Python;
- `dados-isolados`: SQLite, fotos, configurações e log da interface.

**Nenhuma instalação de Credential Provider, serviço SCM, tarefas, alterações de ACL, registro de login ou alteração de senha ocorre por esse comando.** A existência de uma VM não prova recuperação de snapshot, acesso à webcam pela Sessão 0 ou desbloqueio automático na LogonUI.

Se Python e modelos não puderem ser baixados por falta de rede, o script informa o erro. Caso o download dos modelos falhe, o painel ainda pode abrir, mas o cadastro facial ficará indisponível até corrigi-lo.

## Diagnóstico complementar

Após a primeira abertura, para repetir o preflight isolado da VM:

```powershell
& "$env:LOCALAPPDATA\FaceKids-VM-Lab\codigo-developer\scripts\Testar-P5-P6-VM-FaceKids.ps1"
```

O roteiro completo está em
[DEVELOPER-P5-P6-ROTEIRO-VM-20261027.md](DEVELOPER-P5-P6-ROTEIRO-VM-20261027.md).
