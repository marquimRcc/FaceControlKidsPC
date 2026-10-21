# ADR-003 — Desbloqueio nativo por rosto com quotas individuais (Windows)

**Status:** Implementado e validado em hardware real no ambiente doméstico (Outubro/2026)  
**Data:** 2026-10-21  
**Projeto:** [FaceControlKidsPC](https://github.com/marquimRcc/FaceControlKidsPC)  
**Continuidade:** [RFC-001](RFC-001-FACE-ACCESS-GATE.md), [ADR-002 Linux](ADR-002-REGATA-OS-LINUX.md) e [SERVICO_WINDOWS](SERVICO_WINDOWS.md)

## 1. Decisão de produto: arquitetura nativa com desbloqueio automático

**Antes (opção A):** após login manual na conta compartilhada `Filhos`, uma janela do programa restringia ou liberava visualmente o desktop. A janela poderia ser encerrada.

**Implementação Efetiva (Nativa):**
1. O desbloqueio automático facial utiliza o **bloqueio nativo do Windows** (`LockWorkStation`) e um **Credential Provider nativo C++ V2** (`native/credential_provider_facekids/FaceKidsCredentialProvider.dll`).
2. A criança senta diante da webcam (XWF-1080P), o serviço em segundo plano detecta o rosto via YuNet e extrai a biometria via SFace.
3. Se a criança cadastrada tiver saldo positivo e o horário estiver dentro do permitido (toque de recolher), o serviço autoriza e o Credential Provider serializa a credencial da conta Windows padrão `Filhos` (com a senha local consciente "1").
4. O Windows aceita a serialização KerbInteractiveLogon e **desbloqueia a máquina sem necessidade de cliques ou toques em teclado**.
5. O agente interativo na sessão `Filhos` (`filhos_agent.py`) exibe a tela de boas-vindas com o nome e foto da criança, monitora o tempo via relógio monotônico e bloqueia o PC ao fim da quota.
6. A conta administrativa (`MarcosMiniPC`) permanece 100% isolada e intocada. O login manual por senha e PIN permanece sempre disponível.

Limites diários iniciais: 120 minutos por criança, configuráveis; cada criança tem saldo independente, embora compartilhe uma conta do SO.

**Importante:** o Credential Provider empacota credenciais; a autorização final é feita pelo Windows. Ele **não substitui** o mecanismo de autenticação do SO nem bloqueia outros Credential Providers. O login por senha e PIN permanece disponível para recuperação e contingência.

## 2. Componentes Windows em Produção

| Componente | Execução | Tecnologia / dever | Fronteira de segurança |
|---|---|---|---|
| **Painel dos pais** | Conta Windows administradora | Python Tkinter, cadastro de fotos, limites, bônus, histórico 7 dias, PIN parental e programas | Restrito ao administrador; validação por SID/Token |
| **Auth Service (Named Pipe)** | Processo em segundo plano | Python + OpenCV YuNet/SFace + Named Pipe `\\.\pipe\FaceKidsAuthPipe` | Valida quotas no SQLite compartilhado, checa toque de recolher e responde com status tipado |
| **Credential Provider V2** | LogonUI / Winlogon (C++ COM) | `FaceKidsCredentialProvider.dll` registrado no COM | Filtragem estrita por SID (só é exibido para a conta `Filhos`); serializa credencial local após ALLOW |
| **Agente dos Filhos** | Sessão interativa `Filhos` | `filhos_agent.py` agendado no logon | Tela de boas-vindas, toasts aos 10/5/1 min, pausa no Win+L e chamada de `LockWorkStation` |

Arquitetura conceitual em operação:

```text
                      Conta ADMINISTRADOR
                   [Painel de gerenciamento]
                               │
                       Acesso Direto / SQLite
                               │
            Banco de Dados Compartilhado (criancas.sqlite3)
            - 3 crianças com quotas independentes (120 min)
            - Bônus diários acumuláveis
            - Toque de recolher configurável
                               │
                    [Face Auth Service]
                     YuNet -> SFace -> SQLite
                               │  Named Pipe \\.\pipe\FaceKidsAuthPipe
                               ▼
   [Conta FILHOS]        [LogonUI / Winlogon]
   Presence Agent ◄──────[Credential Provider FaceKids]
         │                            │
   monitora sessão            se rosto válido + saldo positivo
   e quota ativa              -> serializa credencial local Filhos
         │                    -> Windows autentica e destrava tela!
         ▼
    LockWorkStation (ao zerar)
```

## 3. Dois cenários de autenticação

### Cenário A — Desbloquear uma sessão existente após Win+L (P0) — FUNCIONAL
- Sessão da conta Filhos já está iniciada e bloqueada (Win+L).
- A criança senta na frente da webcam.
- O Face Kids Auth Service identifica o rosto, confirma saldo e envia ALLOW com status tipado.
- O Credential Provider recebe a autorização, dispara `NotifyAuthSuccess()` e o LogonUI efetua o autologon imediato.
- O agente da sessão Filhos identifica o evento, exibe as boas-vindas e inicia a contagem de tempo.

### Cenário B — Login manual por senha ou PIN convencional
- O usuário ou responsável pode a qualquer momento digitar a senha ou PIN.
- O sistema entra na sessão da conta Filhos em modo *UNIDENTIFIED*.
- Não é debitada quota de nenhuma criança aleatoriamente.
- Assim que uma criança for reconhecida diante da webcam, o agente assume a identidade correta e passa a contabilizar a quota daquela criança.
