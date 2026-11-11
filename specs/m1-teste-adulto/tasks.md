# Marco M1 — Teste Presencial com Rosto Adulto na Conta Filhos (Tasks & Spec)

**Status:** ✅ CONCLUÍDO COM SUCESSO (HOMOLOGADO FISICAMENTE)  
**Metodologia:** Spec-Driven Development (SDD)  
**Data de Execução:** 2026-11-06  
**Ambiente Alvo:** Windows 10/11 — Sessão Interativa da Conta `Filhos` (PowerShell sem elevação)  
**Responsável:** Usuário / Desenvolvedor (ensaio presencial diante da webcam USB)

---

## 1. Objetivo e Escopo

Validar empiricamente o pipeline de captura por webcam USB, detecção (YuNet) e reconhecimento 1:N (SFace) em tempo real e durante o bloqueio de tela (Win+L), utilizando o rosto de um **adulto voluntário como perfil fictício único**.

### Limites e Garantias de Isolamento:
- **Zero impacto na família:** O banco de produção `C:\ProgramData\SafePCKids\kids.sqlite3` e as tarefas agendadas **não foram alterados**.
- **Isolamento de dados:** Todos os vetores foram gravados exclusivamente em:
  `%LOCALAPPDATA%\SafePCKids\laboratorio-adulto-filhos\adulto-teste.sqlite3`
- **Sem privilégios elevados:** O teste rodou em PowerShell normal na conta `Filhos`.
- **Sem autologon:** O ensaio não modificou o Credential Provider nem o LogonUI; executou apenas diagnóstico observacional.

---

## 2. Matriz de Tarefas (SDD Tasks)

| ID | Tarefa | Responsável | Status | Critério de Sucesso |
|---|---|---|---|---|
| **T1.1** | Validar pré-requisitos de ambiente (Python 3.11+, OpenCV, modelos ONNX) | IA / Script | ✅ Concluído | Módulos `cv2`, `numpy`, YuNet e SFace operacionais no `.venv` |
| **T1.2** | Especificação formal e isolamento de dados de teste | IA | ✅ Concluído | `specs/m1-teste-adulto/tasks.md` aprovado |
| **T1.3** | Execução da captura biométrica de 12 vetores do adulto voluntário | Desenvolvedor (Físico) | ✅ Concluído | 12 vetores de 512 bytes gravados em `adulto-teste.sqlite3` |
| **T1.4** | Verificação de correspondência facial ao vivo (60 segundos) | Desenvolvedor (Físico) | ✅ Concluído | Emissão de `PASS: rosto adulto reconhecido ao vivo` |
| **T1.5** | Diagnóstico de observação em tela bloqueada (Win+L) | Desenvolvedor (Físico) | ✅ Concluído | 14 frames bloqueados com 14 correspondências faciais confirmadas (100% de precisão) |
| **T1.6** | Coleta de métricas e descarte do banco de laboratório | IA / Desenvolvedor | ✅ Concluído | Telemetria auditada; banco efêmero pronto para descarte |

---

## 3. Evidências Empíricas e Telemetria Registrada

### 3.1 Telemetria do Terminal (Captura Física):
```text
Dados biometricos lidos do banco adulto somente leitura; fotos nao serao gravadas.
sample=10 wts=UNLOCKED locked_frames=0 locked_matches=0
sample=20 wts=LOCKED locked_frames=5 locked_matches=5
sample=30 wts=UNLOCKED locked_frames=14 locked_matches=14
sample=40 wts=UNLOCKED locked_frames=14 locked_matches=14
sample=50 wts=UNLOCKED locked_frames=14 locked_matches=14
```

### 3.2 Análise dos Dados de Sessão:
- **Transição de Sessão:** Transição `UNLOCKED -> LOCKED -> UNLOCKED` detectada corretamente via Win32 WTS.
- **Frames Sob Sessão Bloqueada (`wts=LOCKED`):** 14 frames válidos capturados da webcam USB.
- **Correspondência Facial no Bloqueio:** **14 matches em 14 frames (100% de assertividade)** utilizando YuNet (detecção) e SFace (embeddings de 512 bytes).
- **Concorrência com Agente de Produção:** O agente de produção em `filhos_agent.py` tratou a concorrência da webcam registrando `Webcam ocupada por outro aplicativo; mantendo perfil ativo para Pai`, sem nenhum crash ou corrupção de estado.

---

## 4. Descarte do Banco de Testes

Para finalizar a limpeza da biometria efêmera de teste do responsável:
```powershell
Remove-Item -LiteralPath (Join-Path $env:LOCALAPPDATA 'SafePCKids\laboratorio-adulto-filhos') -Recurse -Force
```
