# DIRETRIZES DE ATUAÇÃO E TRANSIÇÃO PARA SDD — FaceControlKidsPC

> **DESTINATÁRIO:** Qualquer Agente de IA (Claude Code, Antigravity, Cursor, etc.) que for assumir ou continuar o desenvolvimento deste repositório.  
> **OBJETIVO:** Estabelecer governança estrita via **Spec-Driven Development (SDD)**, organizar a base documental existente e executar os próximos marcos do roadmap sem degradar a estabilidade do sistema em produção.

---

## 1. REGRA DE OURO (NÃO QUEBRAR O QUE JÁ FUNCIONA)

O **FaceControlKidsPC** é um sistema em produção física homologado no computador da família, cobrindo autenticação biométrica em nível de sistema operacional (Windows LogonUI/LSA via C++ Credential Provider) com **339 testes automatizados de CI passando**.

### Proibições Absolutas:
1. **NÃO reescrever do zero** nenhum módulo existente.
2. **NÃO alterar** a DLL C++ (`native/FaceKidsCredentialProvider.dll`) ou contratos de autenticação Kerberos sem uma especificação formal aprovada.
3. **NÃO misturar** código de **Produção Física** com código de **Laboratório de VM**:
   - **Produção Física:** Usa `filhos_agent.py`, `agent_watchdog.py`, `welcome_screen.py`, `quota_agent_accounting.py`.
   - **Laboratório Experimental:** Módulos `quota_broker_*` e `quota_vm_*` (isolados para testes de cutover).
4. **NÃO comitar ou expor** vetores biométricos, fotos capturadas da webcam ou credenciais. Toda biometria é estritamente local e offline.

---

## 2. ESTADO OPERACIONAL DO SISTEMA (RESUMO TÉCNICO)

```text
Webcam USB (XWF-1080P)
      │
      ▼
Face Kids Auth Service (Python SYSTEM / Admin)
   ├── OpenCV YuNet (detecção) + SFace (reconhecimento 1:N)
   ├── Banco SQLite local (kids.sqlite3)
   ├── Watchdog Anti-Burla (agent_watchdog.py)
   └── Servidor Named Pipe: \\.\pipe\FaceKidsAuthPipe
      │
      ▼ (IPC com SID Binding exclusivo da conta Filhos)
Face Kids Credential Provider (C++ nativo / COM)
   └── AutoLogon transparente via KerbInteractiveLogon (senha fixa "1")
      │
      ▼
Agente de Sessão dos Filhos (filhos_agent.py)
   ├── Tela de Boas-Vindas (avatar + saldo diário, fecha em 4s)
   ├── Contabilidade de Quotas e Avisos periódicos (a cada 30min)
   ├── Proteção anti-inatividade física com REEMBOLSO (120s sem mouse/teclado)
   └── Bloqueio automático ao esgotar o tempo (LockWorkStation)
```

---

## 3. MISSÕES DA NOVA IA (PLANO DE ATUAÇÃO SDD)

A nova IA deve atuar estritamente nas 3 fases a seguir, sem pular etapas.

---

### FASE 1: CONSOLIDAÇÃO DA FONTE DE VERDADE (Reverse Spec)
**Problema atual:** A pasta `docs/` possui mais de 60 arquivos (`POC-001` a `POC-042`, relatórios isolados e handoffs de 80 KB). Isso sobrecarrega a janela de contexto de qualquer IA.

**Ações obrigatórias:**
1. **Criar a pasta canônica de especificações:** `specs/producao-windows/`
2. **Gerar 3 arquivos essenciais da produção atual:**
   - `specs/producao-windows/spec.md`: Escopo funcional observável, limites do sistema e comportamento esperado na máquina física.
   - `specs/producao-windows/rules.md`: Lista numerada de todas as regras de negócio ativas (ex: R-01 Quota diária padrão; R-02 Reembolso de 120s de inatividade; R-03 Fallback para contas de pais; R-04 Tolerância a webcam ocupada).
   - `specs/producao-windows/flows.md`: Fluxos de sequência do Named Pipe IPC, ciclo de vida do Watchdog e estados da sessão.
3. **Higienizar a pasta `docs/`:**
   - Mover os arquivos legados de exploração para `docs/archive/pocs/` e `docs/archive/handoffs/`.
   - Manter na raiz de `docs/` apenas as ADRs centrais, o diagrama de arquitetura e o Roadmap atualizado.

---

### FASE 2: GOVERNANÇA DOS PRÓXIMOS MARCOS DO ROADMAP
Qualquer nova funcionalidade deve obrigatoriamente seguir o fluxo **SDD**:
$$\text{Spec} \longrightarrow \text{Tasks} \longrightarrow \text{Code + Tests} \longrightarrow \text{Review} \longrightarrow \text{Security}$$

Os próximos marcos prioritários já definidos no Roadmap são:

#### Marco M1 — Teste Presencial Adulto na Conta Filhos (`scripts/Iniciar-Teste-Adulto-Filhos.ps1`)
- **Objetivo:** Validar o piloto presencial na webcam USB com perfil de teste adulto na conta `Filhos` sem alterar quotas familiares.
- **Antes de executar/alterar:** Abrir `specs/m1-teste-adulto/tasks.md` detalhando os passos e critérios de aceite.

#### Marco M2 — Câmera e Sessão Reais (Capacidade e Segurança)
- **Desafio 1 (Sessão 0):** Resolver a captura de webcam sob o serviço `SYSTEM` (Sessão 0 isolada do Windows). Se não for viável diretamente pelo driver/DirectShow, formalizar em spec a arquitetura de processo auxiliar em sessão de usuário com autenticação de canal.
- **Desafio 2 (Liveness / Anti-Spoofing):** Critérios para diferenciar rosto vivo de fotos/vídeos em tela de celular.
- **Desafio 3 (Duas faces):** Definir o comportamento quando mais de uma criança estiver em frente à câmera.

#### Cutover do Broker SCM Isolado (Migração do Agente Legado)
- Migrar a gravação direta de SQLite de `filhos_agent.py` para o serviço broker seguro apenas com aprovação formal e plano de rollback testado.

---

### FASE 3: POLÍTICA DE RESPOSTA E PROTOCOLO `BLOCKED:`

Quando a IA estiver implementando código:
1. **Regra de Bloqueio Proativo:** Se um requisito, dependência de hardware físico (webcam USB) ou detalhe de permissão do Windows (DACL, SID, UAC) não estiver explícito na especificação, a IA **DEVE PARAR** e responder com:
   ```text
   BLOCKED: [Descrição da ambiguidade ou necessidade de decisão do desenvolvedor]
   Opções técnicas viáveis:
   1. ...
   2. ...
   Aguardando confirmação antes de alterar arquivos.
   ```
2. **Validação Contínua de Testes:** Todo commit ou alteração deve rodar e manter 100% verdes os testes existentes:
   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   ```
3. **Checklist Pré-Commit (`/app.commit`):**
   - [ ] Não há paths absolutos hardcoded com nomes de usuários da família.
   - [ ] Não há imagens de rostos ou bancos SQLite de produção incluídos no diff.
   - [ ] Nenhuma ACL restritiva de segurança foi rebaixada para `Everyone` / `Todos`.

---

## 4. PROMPT PRONTO PARA INICIAR A OUTRA IA

Copie e envie o bloco abaixo para o Claude Code (ou outro agente de IA) ao abrir este repositório:

```text
Você está atuando no repositório FaceControlKidsPC sob a metodologia Spec-Driven Development (SDD).
Leia atentamente o arquivo INSTRUCOES-IA-SDD.md antes de qualquer ação.

Suas diretrizes imediatas são:
1. NÃO reescreva o código de produção nem altere os componentes C++ que já possuem 339 testes verdes.
2. Inicie pela FASE 1: execute a consolidação da especificação do estado atual de produção Windows em `specs/producao-windows/` (criando spec.md, rules.md e flows.md).
3. Mova as POCs antigas e handoffs obsoletos de docs/ para docs/archive/.
4. Se encontrar qualquer ambiguidade ou divergência entre os testes de laboratório e a operação física, pare e retorne com o status BLOCKED: explicando a dúvida.
```
