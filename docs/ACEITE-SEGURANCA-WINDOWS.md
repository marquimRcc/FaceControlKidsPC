# FaceControlKidsPC — aceite seguro de hardware / Windows

## Escopo
Branch exclusiva: `fix/facekids-ipc-security-hardening-20261024`.
Esta branch **nao** foi instalada no computador domestico. O proprietario
relatou que a baseline anterior desbloqueia Filhos; nao confundir este relato
com teste independente desta branch, prova anti-spoof ou identidade do pipe.

## Comandos somente leitura (nao instalar componentes)
Em PowerShell, na raiz do repositorio:

```powershell
.\scripts\Instalar-FaceKids-Nativo.ps1 -PreflightOnly
.\scripts\Desinstalar-FaceKids-Nativo.ps1 -AuditOnly
.\scripts\Auditar-Identidade-PipeFaceKids.ps1
```

- O primeiro inspeciona ACLs: DLL, scripts, logs, banco SQLite/WAL/SHM e fotos.
- O segundo inspeciona tarefas, COM e presença de DLL/DB sem desinstalar.
- O terceiro inspeciona a tarefa de auth e processos de auth por metadados,
  sem conectar ao pipe, invocar reconhecimento facial ou abrir a webcam.
- Os resultados podem mostrar nomes de contas/PIDs/caminhos locais. Revisar
  antes de compartilhar. Nao publicar logs de criancas, fotos ou credenciais.

## Portoes de aceite

1. **CI isolada:** Python Ubuntu/Windows, guard JSON C++17, build de CP real
   e host C++ passam na branch exata a ser instalada. Nenhum runner GitHub
   efetua registro de CP real ou login facial.
2. **VM restauravel:** snapshot testado *fora* da VM; conta administrativa
   tradicional funcionando; via de recuperacao alternativa; testar registros
   e remocoes somente na VM, preservando login convencional.
3. **Proveniencia do pipe:** medir SID/integridade do **servidor efetivo**
   visto pelo cliente nativo, com `GetNamedPipeServerProcessId` e token,
   testando o cliente autentico e o pipe de impostor. A auditoria passiva de
   processos *nao* fornece essa prova. Nao ativar endurecimento que derrube
   a instancia interativa sem esse ensaio.
4. **ACL dos dados:** o instalador legado concedeu Modify no diretorio
   ProgramData/FaceKids para Filhos. Separar executaveis/codigo de dados
   gravaveis e migrar SQLite/fotos com backup e rollback transacional em VM.
   *Nao* remover o Modify cegamente: o agente necessita gravar a quota.
5. **Teste voluntario com webcam real:** com login admin disponivel, verificar
   Win+L, trocar usuario, reiniciar, falta de camera, 3 perfis independentes,
   limite esgotado e horarios. Usar cadastros locais consentidos, nao CI.
6. **Spoofing/liveness:** testar foto, video/replay e duas faces. Os mocks nao
   demonstram resistencia real. Falha deve impedir alegar desbloqueio seguro.
7. **Liberacao:** instalar/atualizar CP no PC familiar somente apos W2-W6
   comprovados e plano de recuperacao verificado, nunca automaticamente.

## Bloqueios atuais
- Hardware Win+L/LogonUI e liveness desta branch: NAO TESTADOS.
- Identidade autenticada do servidor IPC: NAO IMPLEMENTADA no cliente real.
- Banco de quotas protegido contra alteracao pela conta Filhos: NAO CONCLUIDO.
- Rollback automatico de instalacao COM/Winlogon: NAO VALIDADO fisicamente.

Nenhuma dessas pendencias e resolvida por CI verde ou pelo modo de auditoria.
