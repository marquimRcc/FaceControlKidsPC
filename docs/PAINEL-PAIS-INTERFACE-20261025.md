# FaceControlKidsPC — Painel dos Pais (interface 2026-10-25)

**Branch:** `feature/parent-dashboard-ui-20261025`  
**PR:** [#5](https://github.com/marquimRcc/FaceControlKidsPC/pull/5) — draft, baseado em `handoff/facekids-auto-unlock-stabilization-20261021`.

## O que mudou

Modernizamos a aplicação que **já abre** pelo launcher `abrir-facekids.bat`, sem criar um segundo sistema. A janela principal continua em `facekids/admin_dashboard.py`, Tkinter padrão, sem novas bibliotecas gráficas.

- Cabeçalho de marca separado das ações para evitar botões cortados em notebook.
- Indicadores de quantidade de filhos, biometria cadastrada, tempo restante somado e horário global.
- Pesquisa imediata por nome/ID, ignorando maiúsculas e acentos.
- Avisos específicos: rosto pendente, tempo esgotado e biometria cadastrada.
- Editor de horário global **na tela principal**: habilitar/desabilitar, início, fim e salvar. Validação rigorosa `HH:MM`; edição parcialmente preenchida não é apagada quando a busca atualiza.
- Dados existentes são lidos diretamente do `Storage`; continuam disponíveis os botões de foto, webcam, renomear filho, quotas, bônus, histórico, PIN e programas.
- Um aviso explica quando o painel está usando SQLite **local**, e não `C:\ProgramData\FaceKids\criancas.sqlite3`, para evitar falsa impressão de dados compartilhados.

## Como abrir em uma instalação de desenvolvimento separada

1. Na cópia local *de desenvolvimento*, trocar para a branch `feature/parent-dashboard-ui-20261025`. Não usar a pasta instalada no PC familiar antes dos testes de aceite.
2. Instalar as dependências habituais do projeto e manter os modelos faciais conforme a documentação existente.
3. Executar `abrir-facekids.bat` **na conta administrativa**, não na conta `Filhos`. O script chama `python -m facekids.admin_dashboard`.

**Não executar o instalador nativo para testar a interface.** O painel já tem entrypoint próprio; não é necessário substituir o Credential Provider ou manipular tarefas do Windows.

## Validação

- `python -m unittest discover -s tests -v`: suite completa, Linux e Windows pelo GitHub Actions do PR.
- `tests/test_parent_ui_state.py`: quota e bônus independentes para três perfis fictícios, indicadores, busca com acentos e horários.
- `tests/test_parent_dashboard_entrypoint.py`: verifica a aplicação real chamada pelo BAT, métodos disponíveis e importação sem criar janela Tk.
- **Pendente:** smoke test *visual/interativo* em uma sessão gráfica Windows descartável; GitHub Actions verifica lógica, importações e compatibilidade, mas não comprova aparência final nem câmera.

## Limitações e segurança

Esta branch modifica a **interface**, não cria um novo limite de segurança. A conta `Filhos` ainda pode ter acesso ao SQLite legado conforme ACLs atuais. O PIN administrativo é uma proteção de interface, não substitui ACLs ou verificação do SID do processo. O reconhecimento de webcam, Winlogon, broker privilegiado e migração de banco protegido pertencem à branch/PR #4 e **não** são ativados aqui.

**Nenhuma atualização da instalação doméstica, merge em `main`, alteração de banco real ou registro de Credential Provider foi feita nesta rodada.**
