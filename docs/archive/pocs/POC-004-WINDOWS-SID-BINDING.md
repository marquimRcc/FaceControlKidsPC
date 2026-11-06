# P0-2.2 - Selecao do Credential Provider pelo SID

**Status:** compilado e validado com simulacao COM no GitHub Actions.
Nenhum componente foi instalado na tela de login.

A DLL implementa as interfaces ICredentialProviderSetUserArray e
ICredentialProviderCredential2, enumerando uma opcao somente quando
um SID da lista de contas do Windows coincide com o TargetUserSid
configurado em HKLM\SOFTWARE\FaceControlKidsPC\CredentialProvider.

Sem SID em HKLM, ou com SID invalido, o provider retorna zero tiles.
A DLL nao escreve no registro e nao faz autenticacao ou desbloqueio:
GetSerialization continua retornando NO_CREDENTIAL_NOT_FINISHED.

O build FACEKIDS_DIAGNOSTIC_HOST_TEST injeta um SID ficticio somente
no processo de teste COM; o binario normal nao contem esse recurso.
O CI testa lista so com administrador, lista com administrador e
crianca, e nova lista so com administrador (retirada imediata do tile).
Nenhuma conta real e criada e nenhuma senha e utilizada.

## Proximo teste no computador principal

Apos atualizar a branch e com o .venv configurado:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Testar-Integracao-Windows.ps1

O script consulta apenas informacoes publicas das contas Windows, le
a configuracao de SID se existir e roda os testes Python. Nao instala
Credential Provider e nao registra DLL em LogonUI.

## Riscos e passos futuros

O instalador definitivo devera confirmar que TargetUserSid corresponde
especificamente a conta local Filhos e que as ACLs do registro impedem
a alteracao por usuarios padrao. Integracao real em LogonUI requer
VM com snapshot e processo de recuperacao. Somente apos implementar
servico de quotas protegido e credenciais Windows seguras podera haver
desbloqueio facial real.

Documentacao Microsoft:
https://learn.microsoft.com/en-us/windows/win32/api/credentialprovider/nn-credentialprovider-icredentialprovidersetuserarray
https://learn.microsoft.com/en-us/windows/win32/api/credentialprovider/nn-credentialprovider-icredentialprovidercredential2
