# P0-34 — Preflight para testes de recuperacao Windows

Script: \`scripts/Conferir-Ambiente-Isolado.ps1\`.

A execucao e SOMENTE LEITURA: consulta Win32_ComputerSystem e
Win32_OperatingSystem, verifica indicios comuns de virtualizacao e
recusa continuar em maquinas que nao aparentem ser VMs.

Nos testes de ciclo SCM do GitHub Actions, a flag
\`-RequireGitHubHosted\` exige:
- ambiente de automacao do GitHub
- context \`runner.environment\` igual a \`github-hosted\`
- indicios de VM no hardware convidado

Nao registrar DLL, servico, Winlogon nem definir senha no PC real.
Essa verificacao e uma trava adicional, **nao garantia absoluta**:
propriedades WMI podem ser modificadas e nao provam snapshot.

## Checklist manual obrigatorio antes de testar uma DLL de login

1. VM Windows 10/11 isolada e atualizada, com pelo menos
   uma conta administrativa cuja senha seja conhecida pelo responsavel.
2. Criar snapshot/checkpoint e confirmar que pode ser revertido
   DESLIGANDO a VM. O script NAO consegue verificar esse snapshot.
3. Garantir console fora da VM pelo hypervisor, nao depender apenas
   de RDP, pois a tela de login pode falhar.
4. Testar restauracao do snapshot antes de instalar um Credential
   Provider. Confirmar retorno da conta administrativa.
5. Registrar hash/versao do artefato diagnostico, procedimento
   de desinstalacao e um meio alternativo de login.
6. Qualquer erro de login requer restauracao do snapshot;
   nao tentar 'corrigir' chaves Winlogon as cegas.
7. Nunca registrar o Credential Provider diagnostico atual
   como autenticador real: ele NAO gera credenciais.

O CI valida somente que pode executar o broker protegido,
que banco corrompido o impede de subir e que restaurar bytes
originalmente salvos recupera o servico. Nao valida autenticar
um usuario no Winlogon, camera segura ou liveness real.
