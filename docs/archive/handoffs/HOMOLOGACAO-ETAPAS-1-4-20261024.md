# FaceControlKidsPC — homologação incremental das etapas 1–4

**Data:** 24/10/2026. **Branch:** `fix/facekids-ipc-security-hardening-20261024`. **PR:** #4 (draft, base handoff).

## 1. Vínculo facial confiável no serviço — integração em código, não homologação física

- `PrivilegedLocalFaceBinder` solicita a captura por callback **do próprio processo**, sem comando infantil que forneça `child_id`, duração ou prova de identidade.
- `ServiceOwnedQuotaRuntime.from_service_authenticator` utiliza a classe real `FaceAuthenticator.evaluate(persist_unlock_metadata=False)`.
- O fluxo privilegiado não grava `last_unlock.json` nem atualiza avatar. O comportamento do desbloqueio legado permanece como padrão.
- A geração de eventos WTS é conferida antes/depois da captura: lock/unlock ou troca de usuário durante a leitura revoga a autorização.
- Testes negativos recusam SID estranho, id infantil inexistente/booleano, erro na webcam, DENY facial, status falso, corrida de Win+L, perfil anterior e revogação.
- **Não chamar isso de anti-spoof:** o reconhecimento atual não fornece atestado de liveness/anti-replay nem prova de que a webcam estará disponível para serviço em Session 0. Um componente dentro do processo SYSTEM precisa ser protegido por ACLs.

## 2. Quotas pelo broker — engine integrado, corte operacional NÃO aplicado

- `ServiceOwnedQuotaRuntime` coordena captura, WTS/SCM, sessão facial vigente, relógio monotônico e `ServiceOwnedQuotaBroker`.
- `Storage.charge_capped_once` grava débito e recibo exclusivo no mesmo commit SQLite. O filho não pode determinar `seconds`, `child_id`, `event_id`, `day` ou o estado WTS pelo protocolo de leitura.
- Bloqueio, desconexão, sessão diferente, stop SCM e erros de identidade revogam o lease; mesmo após novo desbloqueio é necessária nova captura.
- **Atenção:** o serviço SCM de laboratório continua com canal Named Pipe somente de leitura. O agente Filhos instalado ainda escreve diretamente no SQLite legado. Um SCM exclusivo de cobrança com origem facial protegida e ACLs aplicadas ainda não foi ativado.

## 3. Migração e rollback — prova reversível real com objetos SINTÉTICOS

- `quota_migration_lab.py` aceita somente diretórios `facekids-quota-lab` não vinculados por symlink. Snapshot consistente usa a API `sqlite3.Connection.backup`; nova cópia é preparada e promovida por `os.replace`.
- Falha injetada não promove o arquivo; o backup permanece íntegro. Restauração substitui somente o destino de laboratório, sem alterar a base legado.
- `ci_quota_migration_windows.py` utiliza conta local infantil temporária no runner GitHub-hosted Windows, ACLs reais NTFS e banco de três perfis fictícios. Confere que o token infantil **não consegue abrir, gravar ou substituir** banco e snapshot protegidos, mas escreve no cache.
- Serviço/admin debita o arquivo sintético; rollback restaura as três quotas originais. A conta e a pasta temporárias são removidas com `finally`.
- **Não foi migrado o banco familiar**, nem alteradas ACLs do PC. Cutover real requer parar escritores legados, backup seguro de fotos/SQLite/WAL/SHM e restauração sob token Filhos real, tudo em VM antes da família.

## 4. Homologação Windows/VM — alcance exato

- GitHub Actions Windows Server descartável executa: SCM real de laboratório sob SYSTEM, comparação de SIDs, Named Pipe de laboratório, token infantil sintético, ACL NTFS, integração do banco, rollback e compilação real do CP em host sem registrá-lo no Winlogon.
- `Testar-Preflight-VM-FaceKids.ps1` é **somente leitura**, relata características do host e mantém `ReadyForFamilyInstallation=false`, independentemente de o modelo parecer uma VM.
- **Não há evidência ainda de snapshot externo restaurado, recuperação real do Winlogon, registro do CP numa VM com interface de login, nem webcam/liveness/Win+L físicos**. Um runner descartável não substitui essa VM restaurável.

## Decisão / portões para implantação

| Portão | Resultado |
| --- | --- |
| Componentes e testes sintéticos de identidade facial/quotas | Implementados |
| Banco e ACL com conta infantil sintética, backup/rollback | Ensaio automatizado em runner Windows |
| Instância SCM produtiva de cobrança exclusiva | **Bloqueada** |
| Origem facial robusta, liveness e câmera acessível pelo serviço | **Bloqueada** |
| Snapshot VM e recuperação do login convencional testados | **Bloqueada** |
| Atualização da instalação doméstica e merge na main | **Não realizados** |

Até liberar todos os portões, não modificar `main`, registro COM/HKLM do Credential Provider, credenciais Windows, tarefas, `ProgramData\FaceKids` ou banco/fotos reais.
