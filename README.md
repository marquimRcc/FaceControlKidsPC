# FaceControlKidsPC — Desbloqueio Facial Automático e Controle de Quotas

Sistema doméstico de controle parental e autenticação biométrica facial para computadores compartilhados com **Windows 10 e Windows 11**.

> **Estado do Sistema:** Homologado e funcional no computador físico da família. A criança senta em frente à webcam, o rosto é reconhecido via IA local (YuNet + SFace), a quota diária e horários são validados e o Windows desbloqueia automaticamente a conta **Filhos** sem cliques ou digitação de senha.  
> **Segurança e Fallback:** As contas administrativas e os métodos convencionais (PIN e senha) permanecem 100% acessíveis e intactos.

---

## 1. Principais Funcionalidades

- **Desbloqueio Facial Transparente no Logon (LogonUI):** Credential Provider nativo em C++ (`FaceKidsCredentialProvider.dll`) que atua exclusivamente na conta compartilhada `Filhos`, executando AutoLogon via `KerbInteractiveLogon` com senha fixa `"1"`.
- **Painel dos Pais Centralizado (`abrir-facekids.bat`):** Interface Tkinter com tema moderno (Catppuccin Macchiato) para criação e gestão de perfis, quotas diárias, bônus de tempo (+15, +30, +60 min) e toque de recolher (*curfew*).
- **Cadastro Facial com Galeria de 12 Fotos:** Captura guiada de 12 fotos da webcam (salvas limpas, sem retângulo de detecção verde sobreposto no rosto) permitindo escolher visualmente o avatar oficial da criança na galeria.
- **Tela de Boas-Vindas Inteligente:** Exibe avatar e saldo diário imediatamente após o desbloqueio facial, fecha-se automaticamente após 4 segundos e reaparece brevemente a cada 30 minutos como lembrete suave do tempo restante.
- **Proteção Anti-Inatividade com Reembolso (120s):** Se o computador ficar sem uso de teclado e mouse por 2 minutos, a sessão é bloqueada e o tempo de ausência é **automaticamente reembolsado** para a criança.
- **Watchdog Anti-Burla do Agente:** O serviço do sistema monitora continuamente a sessão ativa da conta `Filhos`. Se o agente for finalizado (ex.: via Gerenciador de Tarefas), o watchdog tenta relançá-lo via Agendador de Tarefas e, caso persista fechado, executa bloqueio preventivo para impedir uso ilimitado.
- **Tolerância a Webcam Ocupada:** Caso a criança esteja em uma videochamada ou jogo web no navegador (Brave) que retenha a webcam, as checagens periódicas em segundo plano mantêm o perfil ativo sem falsos bloqueios.

---

## 2. Scripts Principais no Windows

Os scripts na raiz do projeto centralizam toda a operação:

| Script | Finalidade |
|---|---|
| **`Instalar-FaceUnlock.bat`** | Instala a DLL do Credential Provider, registra no COM e agenda os serviços automáticos. |
| **`abrir-facekids.bat`** | Abre o Painel dos Pais para cadastrar crianças, gerenciar quotas e visualizar a galeria de fotos. |
| **`Ativar-Desbloqueio-No-Boot.bat`** | Ativa o serviço de biometria facial como `SYSTEM` no boot do Windows (antes do logon). |
| **`Desinstalar-FaceUnlock.bat`** | Desinstala com segurança o Credential Provider e tarefas agendadas, preservando o banco de dados. |

---

## 3. Arquitetura e Estrutura de Código

Para entender detalhadamente a divisão entre os módulos de **Produção Windows**, módulos de **Laboratório Experimental** (`quota_broker_*`, `quota_vm_*`) e **Linux** (`linux_*`), consulte:
👉 **[Documento de Arquitetura de Produção Windows](docs/ARQUITETURA-PRODUCAO-WINDOWS.md)**

```text
       Webcam USB (XWF-1080P)
                 │
                 ▼
    Face Kids Auth Service (Python SYSTEM / Admin)
       - OpenCV YuNet (detecção) + SFace (biometria)
       - Consulta SQLite local (kids.sqlite3)
       - Watchdog Anti-Burla (agent_watchdog.py)
       - Servidor Named Pipe: \\.\pipe\FaceKidsAuthPipe
                 │
                 ▼ (IPC Seguro / Status Tipado)
    Face Kids Credential Provider (C++ / COM)
       - DLL nativa: FaceKidsCredentialProvider.dll
       - Filtragem estrita por SID (apenas conta Filhos)
       - AutoLogon transparente (senha "1")
                 │
                 ▼
           LogonUI / Windows LSA
                 │
                 ▼
      Agente de Sessão dos Filhos (filhos_agent.py)
       - Tela de Boas-Vindas com Avatar (welcome_screen.py)
       - Contabilidade de Quota (quota_agent_accounting.py)
       - Reembolso de inatividade física (120s)
       - Heartbeat contínuo para o Watchdog
       - Bloqueio automático ao esgotar o tempo (LockWorkStation)
```

---

## 4. Testes e Validação de Qualidade

O projeto possui uma suíte rigorosa de testes unitários automatizados cobrindo instaladores, contratos IPC, contabilidade de quotas, watchdog e biometria:

```powershell
# Execução completa da suíte de testes (Windows)
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Validação da sintaxe dos scripts de instalação e desinstalação
.\.venv\Scripts\python.exe -m unittest tests/test_installer_scripts.py -v
```

---

## 5. Ambientes Linux (Regata OS)

O desenvolvimento para ambientes Linux (KDE Plasma, SDDM, logind e PAM) está documentado na branch `feature/regataos-linux-implementation-20261022` e em:
- [Implementação Regata OS](docs/IMPLEMENTACAO-REGATAOS-LINUX.md)
- [Documento de Continuidade Linux](docs/CONTINUIDADE-REGATAOS.md)

---

## 6. Licença e Privacidade

- **Licença:** MIT — software livre e de código aberto.
- **Privacidade Biométrica Total:** Todo o processamento facial e dados biométricos ocorrem 100% offline no hardware local. Nenhuma imagem, vetor ou dado de uso é transmitido pela internet.
