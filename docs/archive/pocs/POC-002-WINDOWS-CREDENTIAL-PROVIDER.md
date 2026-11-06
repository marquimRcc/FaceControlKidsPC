# P0-2.1 — Tile diagnóstico nativo do Windows

**Status:** código C++ e contrato de teste isolado no GitHub. Não instalado
em LogonUI. A validação em Windows real exige uma máquina virtual com
snapshot e senha de recuperação.

## Por que é o passo seguinte

P0-1 comprovou a leitura de imagens com a sessão Filhos bloqueada
via OpenCV no computador de testes. Isso não prova que o processo
de reconhecimento poderá operar dentro da tela segura do Windows.

A estrutura COM anterior não oferecia nenhuma credencial/tile, e
consequentemente não exercitava métodos comuns da interface
ICredentialProviderCredential. Esta etapa adiciona um objeto real
de interface (somente de diagnóstico) e amplia o teste do host isolado.

## Comportamento permitido

- Oferece apenas título e texto de diagnóstico;
- GetCredentialCount=1 sem autologon e sem tile padrão;
- GetSerialization retorna NO_CREDENTIAL_NOT_FINISHED, sempre;
- Não conhece a conta Filhos e não abre webcam;
- Não acessa ou emite senha, PIN, token Windows nem ticket de quota;
- Não registra CLSID nem modifica registro, login ou sessão Windows.

## Critério para avançar

1. Workflow Windows deve compilar, carregar a DLL e validar o tile;
2. A política offline de quotas permanece separada até o IPC do serviço;
3. O teste no Windows principal deve utilizar somente o host COM;
4. Testes de registro real no LogonUI somente em VM com recuperação;
5. Qualquer provedor que autentique no futuro exige autorização por
   quota atual, identidade da conta Filhos e senha protegida sob controle
   do serviço de sistema.

## Notas

Um Credential Provider que mostra um tile não significa que ele
consiga autenticar. Mesmo em caso de reconhecimento correto, a API
só deve obter serialização real após a aprovação da identidade e
dos saldos individuais, usando uma trilha de comunicação confiável.

Não adicionar binários de modelos de terceiros até confirmar licenças.
