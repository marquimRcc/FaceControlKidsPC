#define WIN32_LEAN_AND_MEAN
#include "FaceKidsPipeClient.h"
#include <iostream>

int main() {
    std::wcout << L"[FaceKids Pipe Test] Solicitando autenticacao via \\\\.\\pipe\\FaceKidsAuthPipe...\n";
    AuthResult res = FaceKidsPipeClient::RequestAuthentication();
    std::wcout << L"[Resultado] Sucesso: " << (res.success ? L"SIM" : L"NAO") << L"\n";
    std::wcout << L"[Mensagem] " << res.message << L"\n";
    if (res.success) {
        std::wcout << L"[Usuario]  " << res.user << L"\n";
        std::wcout << L"[Filho]    " << res.childName << L"\n";
    }
    return 0;
}
