# P0-8 - Quotas SQLite com ACL restrita no broker Windows

**Status:** modulo C++ compilado no Windows GitHub Actions. Nao existe
instalacao do servico no PC, acesso por criancas ou desbloqueio real.

## Implementado

- SQLite que vem no Windows 10/11 (WinSQLite). Nenhum driver/pacote instalado
- Tres perfis independentes preconfigurados com 7.200 segundos (120 min)
- Banco persistente planejado em ProgramData\FaceControlKidsPC\quota.sqlite3
- Pasta criada com DACL protegida, concedendo acesso exclusivamente
  a SYSTEM e ao grupo Administradores. Acesso por usuarios comuns nao e
  permitido. Se a pasta ja existe com DACL permissiva, o servico recusa
  inicializar em vez de confiar nela
- Arquivo SQLite existente tambem passa por validacao da DACL antes de abrir
- Junctions/symlinks no caminho do banco sao recusados
- Debito de tempo com transacao BEGIN IMMEDIATE e UPDATE condicionado:
  a quota nao pode ser ultrapassada na mesma transacao
- Saldos por dia, alteracao de limite e bonus. Os calculos usam inteiros
  de segundos, nao valores float da conta infantil
- Estado salvo e reaberto para demonstrar persistencia
- Execucao --self-test usa pasta temporaria privada, sem tocar ProgramData

## Integracao ao Windows Service

O caminho --service (ainda NAO instalado) agora exige que o banco de quotas
passe nos testes de ACL e integridade antes de passar a RUNNING ou expor o
pipe administrativo PING/PONG. Falha de permissao = SERVICE_STOPPED.

O pipe **nao expõe operações de quota**: precisa primeiro implementar
autenticacao por tipo de chamador e impedir que a conta Filhos possa
escrever a base. A comunicacao final com o Credential Provider exigira
um canal separado e autenticado e evidencias faciais confiaveis.

A API Storage C++ nao deve ser importada por um processo executado na
conta Filhos nem servir saldos a clientes sem autorizacao.

## Validacao CI

O GitHub Actions compila com MSVC, vincula winsqlite3.lib e roda
--self-test. A base temporaria simula as tres criancas, consumo maximo,
expiracao de saldo, bonus, redefinicao de limite, virada de data,
gravacao/reabertura e permissao DACL.

O banco criado pelo teste e isolado e apagado sem modificar o Windows.
Nao instalar ou executar --service no computador principal neste momento.

Referencia Microsoft:
https://learn.microsoft.com/en-us/windows/apps/develop/data-access/sqlite-data-access
