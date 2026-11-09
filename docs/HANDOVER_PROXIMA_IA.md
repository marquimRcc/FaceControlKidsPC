# Handover Técnico: Branch `feature/redesign-installer-admin-panel`

> **Repositório**: `C:\Users\MarcosMiniPC\Documents\git\FaceControlKidsPC`  
> **Branch**: `feature/redesign-installer-admin-panel`  
> **Base**: `origin/main`  
> **Status dos Testes**: 531 testes automatizados (100% aprovados)  
> **Status do Git**: Árvore de trabalho limpa, commitada e sincronizada com o GitHub (`origin`).

---

## 1. Visão Geral do que foi Desenvolvido nesta Branch

Esta branch implementou a modernização completa do instalador e do painel administrativo do FaceKids (substituindo a antiga interface em Tkinter por uma interface web moderna baseada no **Conceito A** acelerada via Microsoft Edge `--app`), além de restaurar paridade total com a `main`, corrigir problemas críticos de segurança e reorganizar a arquitetura do repositório.

### A. Redesign Visual e Arquitetura Frontend
- **Interface Conceito A**: Telas em HTML5, CSS moderno (Tailwind CDN) e Vanilla JS nativo sem build tools ou dependências do Node.js/pnpm.
- **Janela de Aplicação Acelerada**: O backend Python sobe um servidor HTTP local (`facekids.app_server`) e abre a janela através do Microsoft Edge nativo em modo `--app` (`facekids.app_window`), garantindo responsividade instantânea e fluidez visual.
- **Streaming de Câmera e Captura**: Exibição da webcam em tempo real via MJPEG (`/api/camera/stream`) com captura automática de 12 amostras faciais e seleção de foto oficial.

### B. Correções e Paridade com a `main`
- **Exclusão de Crianças (`handle_child_delete`)**: Corrigida a chamada no backend de `store.remove_person` para `store.delete_person`, adicionando o alias `remove_person` na classe `Storage` e limpeza dos avatares e pastas de amostras faciais no disco.
- **Entrada de PIN por Teclado Físico**: Suporte unificado a números da linha superior, teclado numérico (Numpad), Backspace e botões do teclado virtual.
- **Redução de Tempo / Quota**: Implementada a dedução prioritária de bônus diários e acréscimo no uso diário (`reduce_time`), suportando o botão `-15m` sem erro.
- **Galeria de 12 Fotos**: Modal interativo para visualização e troca da foto de perfil ativa a partir das 12 amostras coletadas.
- **Renomeação de Perfis**: Edição em tempo real do nome de qualquer perfil infantil cadastrado.
- **Cofre DPAPI do Windows**: Gravação e leitura criptografada da senha da conta Windows supervisionada (`filhos_secret.bin` via Windows DPAPI).

### C. Segurança, Privilégios e Smart App Control (Windows 11)
- **Eliminação de Bloqueio pelo Smart App Control (SAC)**: O Windows 11 bloqueia binários `.exe` locais sem assinatura digital válida. Para contornar isso com 100% de legitimidade, atalhos e inicializadores utilizam o binário oficial assinado `pythonw.exe` do `.venv` (assinado pela *Python Software Foundation*), permitindo execução silenciosa e sem tela preta de terminal.
- **Eliminação de Loops de UAC na Conta Filhos**: O agente de monitoramento `FaceKidsFilhosAgent` foi blindado para rodar com **privilégios limitados de usuário comum** na sessão da criança, sem solicitar elevação administrativa ao fazer logon.

### D. Reorganização Arquitetural e Limpeza da Raiz (Opção A)
- **Padronização Python (`pyproject.toml`)**: Implementada especificação PEP 621 com pontos de entrada de console:
  - `facekids` (Smart Launcher: detecta se o sistema já está configurado para abrir direto o Painel dos Pais, ou abre o Assistente de Instalação se novo).
  - `facekids-admin` (abre diretamente o Painel dos Pais).
  - `facekids-installer` (abre diretamente o Assistente de Instalação).
- **Limpeza da Raiz**: Eliminados mais de 25 arquivos dispersos da pasta principal. A raiz agora conta exclusivamente com 5 arquivos essenciais:
  - `.gitignore`, `LICENSE`, `pyproject.toml`, `README.md`, `requirements.txt`.
- **Organização de Pastas**:
  - `scripts/`: scripts PowerShell e BAT administrativos (`Instalar-FaceKids.bat`, `Painel-FaceKids.bat`, `Desinstalar-FaceKids.bat`, `Criar-Atalhos.ps1`).
  - `packaging/`: arquivos de empacotamento PyInstaller e specs (`packaging/pyinstaller/FaceKids-Instalador.spec`).
  - `docs/`: documentações, especificações SDD e requisitos de laboratório.
  - `legacy/`: protótipo antigo e abandonado do Electron/pnpm devidamente arquivado.

---

## 2. Estado Atual do Computador de Teste

Para atender ao pedido do usuário de testar todo o fluxo do zero:
1. **Atalhos do Usuário Limpos**: Atalhos no Desktop e pasta Startup do usuário atual foram removidos.
2. **Desinstalação Completa Automatizada**: O script [`scripts/Desinstalar-FaceKids.bat`](file:///C:/Users/MarcosMiniPC/Documents/git/FaceControlKidsPC/scripts/Desinstalar-FaceKids.bat) foi atualizado com as flags `-RemoveData` e `-RemoveWindowsUser`.
   - Ao ser executado como Administrador pelo usuário, ele:
     - Encerra processos residuais (`FaceKids-Instalador.exe`, `pythonw.exe`).
     - Desregistra o Credential Provider (`regsvr32 /u`).
     - Remove as tarefas agendadas (`FaceKidsAuthService`, `FaceKidsFilhosAgent`).
     - Exclui `C:\ProgramData\FaceKids` (banco de dados SQLite e fotos).
     - Exclui a conta Windows `Filhos` (`net user Filhos /delete`).

---

## 3. Diretrizes para a Próxima IA

Ao assumir este projeto, observe as seguintes diretrizes:

### A. Regras do Usuário Obrigatórias
- **Comportamento Narrativo**: Envie sempre uma mensagem curta e descritiva em português antes de executar qualquer ferramenta, comando ou edição.
- **Foco Descritivo sem Excesso de Código**: Não despeje blocos de código brutos ou logs extensos na conversa; seja conciso e objetivo.
- **Transparência de Etapas**: Mantenha o usuário informado sobre o progresso de cada etapa.

### B. Pontos de Atenção na Continuidade
1. **Fluxo do Primeiro Acesso (Instalador do Zero)**:
   - A entrada recomendada para o usuário testar com 2 cliques é [`scripts/Instalar-FaceKids.bat`](file:///C:/Users/MarcosMiniPC/Documents/git/FaceControlKidsPC/scripts/Instalar-FaceKids.bat) ou digitar `facekids` no terminal.
   - O assistente executa em 3 passos:
     - **Passo 1**: Detecção de webcam e captura facial (12 amostras).
     - **Passo 2**: Definição do nome da criança e limite diário de uso.
     - **Passo 3**: Criação do PIN mestre dos pais e provisionamento da conta Windows `Filhos`.
   - Ao concluir, o instalador deve transicionar diretamente para o Painel dos Pais e registrar os atalhos no Menu Iniciar e Desktop.

2. **Sessão da Criança ('Filhos')**:
   - Quando a criança faz login, o `FaceKidsFilhosAgent` é iniciado automaticamente via tarefa agendada sem pedir permissão de administrador (UAC).
   - O serviço de autenticação facial (`FaceKidsAuthService`) roda como `SYSTEM` e atende ao Credential Provider via named pipe `\\.\pipe\FaceKidsAuthPipe`.

3. **Validação de Testes**:
   - Antes de qualquer novo commit, certifique-se de executar a suíte de testes:
     ```powershell
     .\.venv\Scripts\python.exe -m unittest discover -s tests
     ```
   - Todos os 531 testes devem passar (`OK (skipped=13)`).

4. **Mesclagem para a `main`**:
   - Assim que o usuário aprovar o teste prático de instalação e funcionamento no computador, a branch `feature/redesign-installer-admin-panel` estará pronta para ser mesclada (`merge`) na branch `main`.
