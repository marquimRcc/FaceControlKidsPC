# FaceControlKidsPC — Desbloqueio Facial Automático e Controle de Quotas

Na branch `feature/facekids-cold-boot-auto-unlock-20261022`, consulte
[Boot sem login previo do administrador](docs/BOOT-SEM-LOGIN-ADMIN-20261022.md).
Inclui supervisor SYSTEM no boot e repeticao facial sem clique. Requer ativacao
explicita pelo script e teste fisico da webcam/LogonUI; nao altera o firewall.

> **Estado do Sistema:** Sistema doméstico de controle parental e desbloqueio facial automático via webcam para a conta compartilhada **Filhos** no Windows 10/11.
> **Comprovação em Hardware:** Testado e comprovado funcional no PC doméstico pelo proprietário. A criança senta em frente à webcam, o rosto é reconhecido, a quota diária e horário permitido são verificados, e o Windows desbloqueia automaticamente sem cliques ou digitação de senha.
> **Recuperação e Segurança:** O login convencional (PIN / senha "1" da conta Filhos e credenciais da conta administradora) permanece 100% intacto e acessível.

---

## 1. Visão Geral da Arquitetura

O sistema integra três componentes principais:

```text
       Webcam USB (XWF-1080P)
                 │
                 ▼
   Face Kids Auth Service (Python)
      - OpenCV YuNet (detecção) + SFace (biometria)
      - Consulta SQLite (quotas independentes e toque de recolher)
      - Servidor Named Pipe: \\.\pipe\FaceKidsAuthPipe
                 │
                 ▼ (IPC Seguro / Status Tipado)
   Face Kids Credential Provider V2 (C++ / COM)
      - DLL nativa: FaceKidsCredentialProvider.dll
      - Visível EXCLUSIVAMENTE para a conta "Filhos" (filtragem por SID)
      - AutoLogon com serialização KerbInteractiveLogon (senha fixa "1")
                 │
                 ▼
          LogonUI / Windows LSA
      - Desbloqueia a sessão Filhos sem interação manual
                 │
                 ▼
     Agente de Sessão dos Filhos (filhos_agent.py)
      - Exibe Tela de Boas-Vindas com Foto/Avatar e Tempo Restante
      - Rastreamento monotônico de uso (desconta apenas da criança identificada)
      - Pausa contagem durante Win+L ou suspensão
      - Avisos flutuantes aos 10, 5 e 1 minutos restantes
      - Bloqueio automático (LockWorkStation) ao esgotar a quota ou atingir o toque de recolher
```

---

## 2. Decisões Operacionais e Diretrizes

1. **Conta Filhos e Senha Fixa "1":** Decisão consciente do proprietário para o computador doméstico compartilhado pelas três crianças.
2. **Conta Administradora Intacta:** O Credential Provider do FaceKids filtra estritamente pelo SID da conta `Filhos`. A conta administrativa nunca é alvo de autologon ou bloqueios do agente.
3. **Quotas Independentes:** Cada criança possui sua quota configurável (padrão de 120 minutos/dia), bônus diários acumuláveis e horários permitidos gerenciados no Painel dos Pais.
4. **Login Manual por PIN:** Caso a entrada seja realizada manualmente por PIN ou senha convencional, o sistema entra em modo *UNIDENTIFIED*, sem atribuir tempo arbitrário a nenhuma das crianças até haver identificação facial válida.

---

## 3. Instruções Rápidas de Uso

### A. Instalação e Atualização do Sistema
Para instalar o Credential Provider nativo e iniciar o serviço em segundo plano:
1. Clique com o botão direito em **`Instalar-FaceUnlock.bat`** e execute como Administrador (ou execute diretamente via prompt elevado).
2. O instalador compila os binários nativos (se necessário), copia a DLL para `C:\ProgramData\FaceKids`, registra o CLSID COM via `regsvr32`, configura a inicialização automática do serviço e agenda o agente da conta Filhos.

### B. Cadastro Facial das Crianças
Execute os atalhos correspondentes na conta dos pais:
- **`cadastrar-filho-1.bat`**: Cadastra o rosto do Filho 1
- **`cadastrar-filho-2.bat`**: Cadastra o rosto do Filho 2
- **`cadastrar-filho-3.bat`**: Cadastra o rosto do Filho 3

Ou abra o **Painel dos Pais**:
```cmd
abrir-facekids.bat
```
No painel, o responsável pode gerenciar fotos, limites de tempo, conceder bônus (+15, +30, +60 min) e definir horários de uso.

### C. Desinstalação Segura / Rollback
Caso queira desativar o FaceKids e restaurar o LogonUI padrão:
1. Execute **`Desinstalar-FaceUnlock.bat`** como Administrador.
2. O script desregistra a DLL, remove o serviço da inicialização e limpa os registros, mantendo intactos os logins normais do Windows e o banco de dados.

---

## 4. Testes e Verificação

### Execução de Testes Unitários
Para rodar a suíte completa de 150+ testes de regressão (Windows e Linux):
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### Testes do Credential Provider e IPC Nativo
Na pasta `native/credential_provider_facekids`:
```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
.\TestPipeClient.exe --unit-only
.\TestProviderHost.exe
```

---

## 5. Licença e Privacidade

- **Licença:** MIT — software livre e de código aberto.
- **Privacidade Biométrica:** Nenhuma foto, vídeo, nome ou vetor facial é enviado para a internet ou versionado no Git. Todos os dados permanecem estritamente locais no PC doméstico (`C:\ProgramData\FaceKids`).
