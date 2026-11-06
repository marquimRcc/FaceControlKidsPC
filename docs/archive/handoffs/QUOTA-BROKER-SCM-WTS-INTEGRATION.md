# FaceKids — integração da identidade do pipe e quota privilegiada (24/10/2026)

**Escopo:** apenas a branch de segurança / PR #4 em rascunho. Nenhuma instalação, alteração do registro, ACL da família ou merge foi executado.

## Credential Provider: identidade do servidor
- O cliente C++ chama `FaceKidsPipePeerIdentity::AuthorizeIfConfigured(hPipe)` após conectar, **antes** de enviar `AUTH_QUERY`.
- Política opt-in protegida por HKLM: `SOFTWARE\FaceControlKidsPC\CredentialProvider`, `EnforceAuthServiceSid` (REG_DWORD=1) e `AuthServiceSid` (REG_SZ).
- A consulta usa PID do servidor conectado e SID de `TOKEN_USER`; erro, SID inesperado ou configuração inválida quando habilitada **nega** a autorização.
- **Sem a política habilitada, a compatibilidade legada é mantida.** Portanto, não alegar que a instalação familiar já está protegida. SID sozinho não atesta a integridade do executável nem protege contra outro processo com a mesma identidade. Só habilitar após testes Winlogon em VM e auditoria das ACLs HKLM/NTFS.

## Broker: o que esta rodada implementou
- O motor `ServiceOwnedQuotaBroker` agora chama `Storage.charge_capped_once` com recibo de tick de 128 bits emitido pelo **serviço**, inserido atomicamente com o débito. Repetições idênticas cobram zero; IDs reutilizados para carga diferente falham fechados.
- `VerifiedWtsQuotaWorker` vincula o lease de quota ao SID do token Windows de sessão, ao ID WTS observado, ao sinal de console conectado e aos eventos de travamento/destravamento recebidos do SCM.
- `quota_broker_wts_win.observe_console_from_system` consulta `WTSGetActiveConsoleSessionId`, `WTSQuerySessionInformationW` e `WTSQueryUserToken`; a última requer contexto privilegiado adequado. Falha não se converte em autorização e não recorre ao nome da conta.
- `FaceKidsQuotaLabService` aceita `SERVICE_ACCEPT_SESSIONCHANGE`, recebe `SvcOtherEx` e encaminha o evento ao `WtsLockTracker`. Estado inicialmente desconhecido **não debita**; lock/disconnect/logoff suspende a cobrança; reconexão exige novo unlock.
- Todos os testes de débito usam bancos **sintéticos**, sem imagem, Windows logon nem serviço doméstico.

## Importante: limites operacionais ainda abertos
1. O SCM de laboratório continua com transporte **read-only**; a ponte WTS e motor de débito foram integrados **em código e testes**, não como cobrador ativo do Windows familiar.
2. Ainda é necessário alimentar `start_trusted_face_binding` por reconhecimento facial cuja origem seja autenticada pelo próprio processo privilegiado; nem IPC infantil nem `last_unlock.json` podem conceder o vínculo.
3. Migração segura do SQLite legado para diretório de posse do serviço, revisão das ACLs de binários/scripts e proteção das entradas HKLM ainda exigem ensaio real de token Filhos em VM restaurável.
4. Para aceitar a instalação, simular Win+L, logoff, reboot, troca rápida, quota de três crianças, derrota de spoofing e rollback do CP nativo, mantendo login administrativo alternativo.

**Não ativar `EnforceAuthServiceSid` na instalação familiar nem mudar o escritor SQLite enquanto estes portões estiverem abertos.**
