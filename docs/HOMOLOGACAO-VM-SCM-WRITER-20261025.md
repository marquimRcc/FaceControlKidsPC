# FaceKids — homologação do serviço de quota e proteção SQLite (25/10/2026)

**Branch de trabalho:** `fix/facekids-ipc-security-hardening-20261024`  
**Revisão:** PR [#4](https://github.com/marquimRcc/FaceControlKidsPC/pull/4), rascunho. Não realizar merge nem implantação no computador familiar.

## Resultado implementado nesta rodada

A cobrança deixou de estar restrita a uma engine isolada: o projeto contém um **host SCM de execução** (`ServiceOwnedScmHost`) e uma classe de serviço pywin32 (`FaceKidsQuotaWriterVmService`) com escrita de quotas **exclusivamente em fixture sintética de VM**. Este serviço experimental é separado do serviço de consulta de saldo (somente leitura) e não substitui automaticamente o agente `Filhos`.

### Caminho de confiança

1. **SCM LocalSystem:** `SvcDoRun` compara o SID de processo com o SID SYSTEM (`S-1-5-18`) exigido por política HKLM isolada. Falha antes de ler o banco.
2. **Política restrita:** `HKLM\SOFTWARE\FaceControlKidsPC\QuotaWriterVmLab`; exige `VmLabOnly=1`, `WriterEnabled=1`, SID infantil obtido de token Windows, caminhos existentes `facekids-quota-lab` e nome obrigatório `writer-fixture.sqlite3`. Não existem comandos de instalação no aplicativo.
3. **Isolamento:** pasta e arquivos de banco/modelos são inspecionados por ACL para rejeitar escrita por usuários comuns. O banco também deve conter marcador `settings.quota_writer_vm_fixture=synthetic-acceptance-v1`. Caminhos sob `%ProgramData%\FaceKids` são recusados.
4. **Token da sessão:** `observe_console_from_system` usa WTS do Windows e `TOKEN_USER`, não o nome fornecido pelo aplicativo infantil. A sessão precisa estar conectada e apresentar o SID exato.
5. **Win+L:** somente o callback real do SCM (`SvcOtherEx`) informa lock/unlock. Ao receber *qualquer* evento, a identidade facial prévia é revogada. Um novo desbloqueio precisa de nova captura.
6. **Reconhecimento protegido:** `FaceAuthenticator.evaluate(persist_unlock_metadata=False)` roda internamente no serviço. O evento não aceita `child_id`, duração, estado WTS, recibo ou SID informados pelo cliente.
7. **Transação SQLite:** o serviço gera seus próprios ticks monotônicos; `charge_capped_once` insere débito e recibo idempotente na mesma transação. Se SID/WTS/face/horário não são comprovados, **não cobra**.

### Correção de concorrência Win+L / webcam

A captura facial pode levar vários segundos. Ela **não segura o lock de eventos do SCM**. O binder verifica a geração WTS antes/depois, e a verificação final + criação da identidade ficam serializadas com os eventos SCM. Um Win+L durante a captura invalida o resultado. A sessão anterior também é revogada antes de iniciar uma captura nova; um `ALLOW` atrasado não pode reativar o filho antigo.

## O que a automação consegue comprovar

- Unitários Windows/Ubuntu: três perfis fictícios, quotas independentes, recibos, negativa de `CHARGE` por IPC, câmera negada e com retentativa limitada, mudança de SID, Win+L concorrente, desbloqueio duplicado, stop/restart e políticas inválidas.
- SCM real num runner Windows **descartável**: registra temporariamente o `FaceKidsQuotaWriterVmOnly` como SYSTEM com SQLite fictício, HKLM e ACL dedicados. Testa início/parada, acesso proibido por token infantil real, recusa de alterações de política por esse usuário e **zero débitos sem desbloqueio/captura**. Remove serviço, registro, conta de teste e arquivos em `finally`.
- Migração sintética existente: cópia WAL segura, ACLs restritivas e rollback do banco protegido.
- Compile-only Credential Provider existente: mantém o login convencional disponível; **não registra DLL no Winlogon**.

**Limite da evidência:** um runner não reproduz webcam física, o LogonUI de uma estação doméstica, liveness contra foto/vídeo ou um snapshot externo restaurável. Consequentemente **não demonstra débito positivo por reconhecimento no Windows real**. Esse ensaio ainda exige VM interativa e uma câmera de testes.

## Portões obrigatórios numa VM restaurável antes de instalar na família

| Portão | Ação de homologação | Aceitação |
| --- | --- | --- |
| VM realmente recuperável | Snapshot **externo** antes de mudanças, restauração executada e login convencional testado | Restauração comprovada pelo operador |
| Windows admin preservado | Entrar por PIN/senha, simular falha de LoginUI, reiniciar e desinstalar CP de teste | Admin recupera a sessão sem reconhecimento |
| Câmera do serviço | Testar câmera USB/passthrough na Sessão 0 (SYSTEM), desligar webcam e simular falhas | Não há reconhecimento inventado; erro tem recuperação |
| Proveniência facial e liveness | Um filho presente, rosto não cadastrado, foto/vídeo de rosto e dois rostos | Negativas corretas; não usar como barreira antifraude até concluir |
| Sessões e quotas | Reconhecer Filho A, consumir tempo, Win+L, Filho B, mudar SID, desconectar/RDP, suspender, reiniciar | Cada criança gasta apenas sua quota sem contagem ao bloquear |
| Exclusividade de escrita | Parar qualquer escritor legado, proteger SQLite/WAL/SHM, teste com token real da conta `Filhos` | Somente serviço modifica banco; agent consulta por IPC |
| Falha de disco/rollback | Backup SQLite consistente + ACLs + templates antes da promoção; falha proposital; restauração | Exatamente os saldos e cadastros anteriores |
| Releitura completa pós-instalação | Revisar configurações da `main` e da branch de segurança, comparar perfis e instalação | Nenhum recurso do PC familiar instalado prematuramente |

### Auditoria de pré-condições sem instalação

Em uma cópia do repositório **dentro da VM**, execute:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Testar-Preflight-VM-FaceKids.ps1
python -m unittest discover -s tests -p 'test_quota_broker*.py' -v
```

O preflight **apenas lê o estado atual**: não aplica ACLs, não instala serviço e jamais marca automaticamente `ReadyForFamilyInstallation=true`.

### Bloqueadores para o corte produtivo

- O serviço `FaceKidsQuotaWriterVmOnly` **recusa a base instalada** por projeto. É um portão para ensaio, **não** o substituto de produção.
- O `filhos_agent.py` instalado ainda faz cobranças diretamente em SQLite. É preciso criar o leitor IPC do agente, interromper o escritor antigo e realizar a migração com proteção de arquivos; caso contrário há dupla escrita.
- A disponibilidade da webcam para SYSTEM Sessão 0 e detecção de presença viva **não estão homologadas**. Não ativar a cobrança exclusiva em hardware real.
- GitHub-hosted Windows é descartável, mas não substitui um snapshot restaurado de VM interativa com Winlogon.

**Nenhum comando dessa rodada modifica:** `main`, Credential Provider registrado, tarefas, `%ProgramData%\FaceKids`, PIN/senha Windows, banco ou fotos das crianças.
