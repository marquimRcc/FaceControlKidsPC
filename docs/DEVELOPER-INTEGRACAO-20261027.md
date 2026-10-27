# Integração `developer`: main funcional + segurança isolada

**Data:** 27/10/2026. **Alvo:** branch `developer`, originada
diretamente do commit `4f2ec165c79835f04d64bad1bedab242910edcee`
da `main`. Nenhum merge ou push na `main`.

## Critério principal

Preservar a experiência doméstica atual como *baseline funcional*:
- prioridade ao jogador atualmente usando teclado/mouse, janela de 15 s;
- detecção de vários rostos e não alternar quando um irmão passa atrás;
- troca somente quando condições de sessão permitirem e após atividade cessar;
- tolerância inicial de 120 s após desbloqueio (não rebloquear imediatamente);
- bloqueio por inatividade, reembolso de até 120 s, saldo e curfew;
- fotos oficiais e tela de boas-vindas, 3 temas do painel;
- fallback administrativo; não instalar nem reconfigurar LogonUI aqui;
- um ou mais perfis infantis, sem quantidade fixa de três.

## O que foi incorporado

| Componente | Operação | Resultado |
|---|---|---|
| 93 arquivos novos de segurança | Importação de blobs, sem substituir caminhos já existentes na main | Broker SCM/VM, protocolos IPC, validação de SID, migração, rollback, leitores, testes e documentação disponíveis em paralelo |
| `facekids/storage.py` | Portadas validação de débitos, transação `BEGIN IMMEDIATE`, owner `vm-service-only`, cobrança limitada e recibos idempotentes | Métodos de fotos, remoção, bônus, reembolso e schema existentes mantidos |
| `facekids/filhos_agent.py` | Leitura estrita do JSON e metadados de unlock, confirmação de rosto e adapter explícito `LegacyLedgerQuota` | Mantidas as condições da main; serviço novo **não assume** cobrança doméstica |
| `facekids/auth_service.py` | Rejeição de clientes remotos no pipe; framing ASCII estrito; falha segura se DACL explícita indisponível | `FaceAuthenticator.evaluate` multi-face e fallback de câmera da main preservados |
| Credential Provider C++ | JSON delimitado, sem chaves duplicadas, saldo positivo e SID do servidor por política opcional | Preservados testes e código de repetição automática da main; **sem registrar DLL** |
| `build.ps1` e workflow nativo | Testes JSON/SID sintéticos adicionados aos testes existentes | Nenhum instalador ou serviço de usuário executado |
| `tests/test_boot_auth.py`, `TestCredentialRetry.cpp` | Fixtures corrigidas para simular DACL e saldo consistente com a nova regra | Não foi enfraquecida a validação de produção |
| `tests/test_developer_integration.py` | Regressões de regras, foto/reembolso e serviço escritor | Dados inteiramente fictícios |

## Testes já concluídos na rodada

- [`bb993052` Windows/Ubuntu unitários](https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40495102640): **success** nas duas plataformas; [integração Linux](https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40495102773): **success**.
- [`af426dcd` Credential Provider/host](https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40494994283): **success** nos jobs de compilação e host.
- Último commit de código com regressões integradas `c6d2eb71`: [Windows e Ubuntu](https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40495237694) **success, 439 testes descobertos por plataforma**, além de [Linux](https://github.com/marquimRcc/FaceControlKidsPC/actions/runs/40495237800) **success**. Não são testes de webcam ou Winlogon. O commit documental subsequente não altera código.

## Não integrado / próximo passo

1. **O novo escritor SCM está isolado.** O agente doméstico continua usando `LegacyLedgerQuota`: migrar apenas com VM interativa restaurável, backup do banco real sob ACL e confronto de recibos/reembolso. Nunca apontar scripts VM-only à instalação familiar.
2. **Dualidade do contador:** o sistema da main reembolsa períodos ociosos; o protótipo SCM soma somente tempo ativo e não compartilha a mesma semântica de reembolso. É necessário definir invariantes antes do cutover.
3. **Autenticação nativa:** o servidor principal ainda publica credencial estática de fallback para o Provider. `last_unlock.json` é metadado não assinado; a verificação do SID do pipe no Provider é opcional por política HKLM, não está habilitada em produção.
4. **Faltam ensaios físicos:** webcam USB, Session 0, WTS real, Win+L, LogonUI, câmera indisponível, face múltipla real, ausência do pai/crianças e restauração da VM. CI não certifica isso.
5. **Não há instalação, registro de Credential Provider, atualização do PC familiar ou merge na main.** Qualquer promoção exige autorização expressa e homologação.

**Decisão:** não fazer merge cego do PR #4. A branch `developer` é o ponto
de reconciliação; preservar main acima de qualquer incremento de segurança.
