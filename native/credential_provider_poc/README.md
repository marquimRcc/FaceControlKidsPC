# P0-2 — Credential Provider COM mínimo (build + host test)

Esta DLL C++ é build-only: não foi instalada e não é registrada. Implementa
ICredentialProvider, com **ZERO credenciais**. Não desbloqueia, não abre câmera,
não guarda senha e não exibe tile.

## Build e teste local no Developer PowerShell x64 do Visual Studio

Execute na raiz do repositório:

    cl /nologo /std:c++17 /EHsc /W4 /LD native\credential_provider_poc\provider.cpp /link /OUT:FaceKidsEmptyProvider.dll /EXPORT:DllGetClassObject=FaceKidsGetClassObject /EXPORT:DllCanUnloadNow=FaceKidsCanUnloadNow Ole32.lib
    cl /nologo /std:c++17 /EHsc /W4 native\credential_provider_poc\host.cpp /link /OUT:FaceKidsProviderHost.exe Ole32.lib
    .\FaceKidsProviderHost.exe .\FaceKidsEmptyProvider.dll

O host independente usa LoadLibrary, DllGetClassObject, IClassFactory,
ICredentialProvider, CPUS_LOGON e CPUS_UNLOCK_WORKSTATION. Garante que
o provider não anuncia credenciais, não aceita CredUI e descarrega limpo.
O workflow credential-provider-build.yml faz a mesma verificação no CI Windows.

**Não executar regsvr32 nem registrar este CLSID no seu Windows.**
O provider ainda não tem um caminho de recuperação e autenticação validado.

## Próxima prova técnica

Estudar nyxri0f8/winface (cp/provider.cpp, cp/credential.cpp, cp/scanner.cpp)
como referência: primeiro, um tile diagnóstico em VM sem senha. Só depois
de validar webcam em Win+L, adicionar autorizador por quota de criança,
credenciais protegidas e recuperação com login administrativo.

Um rosto identificado não basta: cada desbloqueio deverá exigir uma
autorização **recente, de uso único**, do serviço que guarda os saldos
individuais. A sessão Windows é compartilhada, mas cada criança terá ID próprio.

Esta etapa não prova webcam em lock screen nem desbloqueio real.
