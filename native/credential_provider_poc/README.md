# Credential Provider — P0-2.1: interface diagnóstica (NÃO instalada)

**Objetivo:** validar, num host COM isolado, a estrutura de uma opção
de autenticação do Windows sem modificar o login real.

O provider agora fornece exatamente **um tile com dois textos estáticos**,
somente para testar os contratos COM. Ele nunca produz credenciais: toda
chamada de GetSerialization retorna CPGSR_NO_CREDENTIAL_NOT_FINISHED
com estrutura de autenticação vazia e sem autologon. Não abre câmera,
não lê banco, não executa reconhecimento e não conhece senha alguma.

**Não registrar a DLL no Windows** e não executar regsvr32. A DLL ainda não
tem procedimento de implantação/remoção apropriado, usuário associado
ou recuperação validada no LogonUI. Não é um aplicativo de desbloqueio.

## Testar na conta principal sem alterar o Windows

Abra a branch feature/windows-native-unlock-poc no GitHub. O workflow
"Credential Provider compile and host checks" compila ambos os executáveis
no Windows e publica, após aprovação, o artifact
FaceKidsCredentialProvider-DiagnosticHostOnly.

No seu PC, o host COM é seguro para executar sem instalar a DLL:

    FaceKidsProviderHost.exe FaceKidsDiagnosticProvider.dll

Ele apenas carrega a DLL com LoadLibrary, instancia ICredentialProvider,
consulta campos e chama GetSerialization, verificando que o resultado
**não autoriza login**. Fechou o programa, não há componente instalado.

Também é possível compilar manualmente em Developer PowerShell x64 do
Visual Studio (C++ Build Tools + Windows SDK), a partir da raiz do repo:

    cl /nologo /std:c++17 /EHsc /W4 /LD native\credential_provider_poc\provider.cpp /link /OUT:FaceKidsDiagnosticProvider.dll /EXPORT:DllGetClassObject=FaceKidsGetClassObject /EXPORT:DllCanUnloadNow=FaceKidsCanUnloadNow Ole32.lib
    cl /nologo /std:c++17 /EHsc /W4 native\credential_provider_poc\host.cpp /link /OUT:FaceKidsProviderHost.exe Ole32.lib
    .\FaceKidsProviderHost.exe .\FaceKidsDiagnosticProvider.dll

## Critérios de aprovação

- DLL carrega sem registro COM e devolve IClassFactory
- CPUS_LOGON e CPUS_UNLOCK_WORKSTATION oferecem 1 tile e 2 campos
- CPUS_CREDUI permanece desabilitado; nenhuma senha é solicitada
- Auto-logon sempre desabilitado e GetSerialization sem credential bytes
- Os campos são liberados corretamente e DLL pode ser descarregada
- Os provedores padrão do Windows nunca são modificados

## Próxima fase

Prova em VM: instalação temporária de um tile **não autenticante** com
recuperação auditada. Apenas depois estudar imagem, quota individual,
IPC protegido e autenticação real pela conta compartilhada Filhos.

Referência de arquitetura: WinFace (nyxri0f8/winface) e as APIs
do Credential Provider da Microsoft; nenhum código foi copiado do WinFace.
