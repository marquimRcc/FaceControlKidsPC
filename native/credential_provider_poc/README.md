# P0-2 — Credential Provider COM mínimo (build-only)

Este diretório contém uma DLL **inofensiva e NÃO INSTALÁVEL** que implementa o
contrato ICredentialProvider para validar compilação com o Windows SDK.
Retorna sempre **0 credenciais**, não desenha um tile, não usa câmera, não
guarda senha, não registra DLL no Windows e não desbloqueia sessões.

A prova serve somente para validar o toolchain e o contrato COM básico. Sem
registro do CLSID no registro Windows, o LogonUI não carrega a DLL.

Para compilar no Windows com Visual Studio Build Tools e Windows SDK, em
Developer PowerShell for VS (arquitetura x64):

    cd native/credential_provider_poc
    cl /nologo /std:c++17 /EHsc /W4 /LD provider.cpp /link /OUT:FaceKidsEmptyProvider.dll Ole32.lib

Não execute regsvr32 nem cadastre o CLSID no sistema principal.
A próxima prova será construir um **host de testes isolado** para instanciar
a classe COM e verificar que GetCredentialCount retorna zero.
Somente depois será considerada uma instalação em VM com snapshot e
recuperação administrativa intacta.

Sobre produção: um CP é um componente COM carregado pelo LogonUI, e não
um processo Python. Evitar chamadas de reconhecimento facial pesadas no CP.
A implementação final exigirá broker/IPC autenticado, estratégia de câmera
no lock screen, credenciais da conta Filhos protegidas e políticas de recovery.
