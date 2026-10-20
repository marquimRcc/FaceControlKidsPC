# P0-5 - Servico Windows e pipe protegido (sem instalacao)

Esta etapa adiciona o executavel C++ FaceKidsBrokerPoc.exe que possui
estrutura de Windows Service Control Manager (SCM) e um named pipe
de diagnostico em contexto local.

**NAO E O SERVICO FINAL.** Nao consulta quota ou banco, nao recebe rosto,
nao produz credenciais e nao acessa o Credential Provider. Nao existe
comando de instalacao/desinstalacao, e a conta Filhos nao deve executa-lo.

## Segurança aplicada

- SDDL de acesso a pipe: SYSTEM e grupo Administradores, sem Everyone
- Pipe rejeita clientes remotos com PIPE_REJECT_REMOTE_CLIENTS
- Depois da leitura, o servidor impersona o cliente e valida
  pertencimento habilitado a SYSTEM ou Administradores
- Protocolo de tamanho limitado, exclusivamente PING => PONG
- Nenhum JSON, token de login, senha, rosto ou quota trafega no pipe
- Falha de autenticacao, sintaxe ou tempo excedido nega acesso
- --console-once nao instala o SCM e encerra apos uma solicitacao
- O servico tem inicio/parada/STOP via SCM; esse caminho ainda NAO foi
  testado como servico instalado, apenas compilado

## GitHub Actions

O workflow Windows broker SCM and protected IPC PoC compila com MSVC,
verifica a DACL e executa um servidor de uma requisicao. Um cliente
separado conecta ao pipe e verifica PONG. O teste nao altera registro
ou instalacao do Windows.

O executavel aprovado e publicado no artifact FaceKidsBrokerPoc-HostOnly.

## PC principal - diagnostico sem servico

Para validar localmente, ainda prefira o script
scripts/Testar-Integracao-Windows.ps1 com os testes Python de politica.

O executavel C++ usa uma DACL que exige token elevado de administrador
ou SYSTEM. Na conta MarcosMiniPC sem elevacao UAC, --ping deve ser
negado por desenho. Nao e necessario instalacao nem elevacao no PC agora.

## Proximos passos

1. Confirmar CI e casos de falha do pipe (cliente nao autorizado,
   comando invalido, tamanho excedido e encerramento).
2. Implementar SCM installer/rollback verificado em VM.
3. Adicionar leitura WTS protegida, saldos em ProgramData com ACL,
   e autenticar o canal do Credential Provider.
4. Integrar o coordenador offline apenas depois de estabelecer a origem
   confiavel das amostras faciais; nunca receber FacialEvidence de processos
   controlados pela conta Filhos e considera-la verificada.
