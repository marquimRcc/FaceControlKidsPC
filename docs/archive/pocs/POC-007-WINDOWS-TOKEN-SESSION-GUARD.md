# P0-7 — Verificacao server-side de identidade por token Windows

**Status:** guard nativo C++ integrado ao comando --self-test do broker,
sem instalacao de servico, alteracao do login ou acesso a credenciais.

## Decisao

Para liberar qualquer autorizacao facial no futuro, o broker Windows
precisara confirmar que a sessao em questao continua bloqueada e
pertence exatamente a conta Filhos.

O nome "Filhos" lido em WTS e somente diagnostico: nao comprova
identidade. Em contexto confiavel LocalSystem, o broker le o token
da sessao Windows por WTSQueryUserToken e obtem seu TokenUser. Um
SID incompleto, inexistente, de conta diferente ou indisponivel
faz o processo negar a precondicao.

Uma funcao de decisao pura, check_snapshot, executa validacoes:
- Session ID integro e valido (nao zero, nem corrente generico)
- TargetUserSid no formato de conta local Windows
- Estado WTS = LOCKED (nao UNLOCKED, INACTIVE ou UNKNOWN)
- SID da sessao proveniente de token autentico do SO
- SID exato da sessao corresponde ao SID da conta-alvo
- Nenhuma informacao aceita diretamente de request ou conta infantil

O retorno READY_FOR_POLICY_ONLY **nao significa que a crianca pode
desbloquear o Windows**. Apenas indica que podemos, futuramente, fazer
a checagem separada de rosto, antisspoof, saldo e autorizacao de uso
unico. O Broker C++ atual nao tem token facial nem banco de quotas.

## Provas automatizadas

O --self-test do executavel verifica varios estados simulados,
incluindo administrador com SID diferente, estado de sessao desconhecido
e falta de permissao ao token. O GitHub Actions compila e executa
o teste no Windows, alem de validar o pipe administrativo PING/PONG.

## Proximos bloqueadores

1. Servico real instalado no SCM e rodando sob LocalSystem — somente
   em VM com snapshot e procedimento seguro de rollback.
2. Verificar que a conta configurada e mesmo a conta local Filhos,
   proteger a configuracao e as ACLs de arquivos/SQLite em ProgramData.
3. Estabelecer origem confiavel da camera e IPC segregado com o CP.
4. Verificar quota e expedir autorizacao com validade curta;
   a credencial de Windows permanece inacessivel ao usuario infantil.
5. Nunca instalar um Credential Provider experimental diretamente no
   computador principal antes de exercitar o processo de recuperacao.
