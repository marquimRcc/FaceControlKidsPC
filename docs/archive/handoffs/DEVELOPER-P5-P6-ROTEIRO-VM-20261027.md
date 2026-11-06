# FaceKids developer — P5/P6: roteiro de homologação em VM

**Data:** 2026-10-27  
**Ambiente:** Windows 11 em VM descartável; não executar primeiro no PC familiar.  
**Base:** branch `developer`.  
**Regra principal:** uma ou mais crianças, usando inicialmente o rosto consentido do pai como perfil fictício da conta `Filhos`.

## O que está preparado

**P5** — o agente possui observador opt-in `VmBoundShadow`, desligado por padrão. O agente continua com `LegacyLedgerQuota` como escritor. O observador apenas consulta o pipe somente leitura do serviço registrado na VM e registra eventos `matched`, `diverged`, `unbound`, `unavailable`, `different-face-lease` ou `incomparable-sample`. Ele nunca troca perfis, altera quota, bloqueia Windows ou inicia webcam.

**P6** — `scripts/Testar-P5-P6-VM-FaceKids.ps1` examina de forma não destrutiva o ambiente convidado, os vestígios do provedor de credenciais e os serviços existentes. As opções `-RunUnitTests` e `-CameraProbe` executam testes sintéticos ou somente abertura temporária da câmera da sessão interativa; nenhum arquivo de imagem é salvo. O script não configura login nem instala serviços.

## Antes de rodar o P6

1. Criar VM Windows descartável com senha administrativa convencional conhecida.
2. Criar snapshot/checkpoint externo pelo hipervisor.
3. Comprovar que a restauração do snapshot funciona e que o login administrativo é recuperado.
4. Passar webcam via USB ou recurso compatível, conforme o hipervisor.
5. Clonar `developer` dentro da VM, sem apontar scripts para banco familiar.
6. Ter Python 3.11 e dependências do projeto para os testes opcionais.

## Execução no PowerShell da VM, a partir da pasta da developer

Preflight (somente leitura):
```powershell
.\scripts\Testar-P5-P6-VM-FaceKids.ps1
```

Suíte automatizada (fixtures de laboratório):
```powershell
.\scripts\Testar-P5-P6-VM-FaceKids.ps1 -RunUnitTests
```

Teste opcional da webcam interativa (não é Session 0):
```powershell
.\scripts\Testar-P5-P6-VM-FaceKids.ps1 -CameraProbe -CameraIndex 0
```

O modo sombra exige VM com serviço SCM de laboratório **previamente homologado**. Para habilitar apenas no processo interativo de teste, usar as duas variáveis de ambiente documentadas em `facekids/quota_vm_shadow_integration.py`; desativado por padrão. Não confundir os saldos de bancos sintéticos distintos com uma validação definitiva de cobrança.

## Checklist manual obrigatório

| Evidência | Estado inicial |
| --- | --- |
| Snapshot externo restaurado com sucesso | NÃO TESTADO |
| Login administrativo convencional após recuperação | NÃO TESTADO |
| Webcam interativa e em SYSTEM/Session 0 | NÃO TESTADO |
| Reconhecimento de rosto adulto, ausência e duas faces | NÃO TESTADO |
| Win+L, login, reinicialização e serviço indisponível | NÃO TESTADO |
| Troca após 15s, prioridade do jogador e fundo multirrostos | NÃO TESTADO |
| Quota, bloqueio por ausência, horários e reembolso | NÃO TESTADO |
| Comparação P5 sem qualquer efeito sobre bloqueio ou débito | NÃO TESTADO |
| Credential Provider e recuperação em VM | NÃO TESTADO |
| Conta Filhos sem escrita no SQLite/WAL/SHM protegido | NÃO TESTADO |

## Limitações e portões

O script não certifica recuperação de snapshot ou desbloqueio no LogonUI. Uma câmera funcionando na sessão interativa não comprova captura em SYSTEM. O writer SCM continua confinado a fixture sintética de VM e não pode coexistir escrevendo o mesmo banco legado. A fonte confiável dos períodos ociosos necessários ao reembolso protegido ainda exige homologação.

**Nenhum resultado do CI sozinho autoriza promover `developer` à `main` ou instalar o writer no PC familiar.**
