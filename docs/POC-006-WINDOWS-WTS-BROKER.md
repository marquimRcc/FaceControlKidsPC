# P0-6 - Leitura nativa do estado de sessoes Windows

**Status:** diagnostico no executavel do broker P0-5, sem instalar servico
ou alterar a configuracao de login.

O novo comando FaceKidsBrokerPoc.exe --sessions usa as APIs oficiais do
Windows Terminal Services:

- WTSEnumerateSessionsW descobre as sessoes locais
- WTSQuerySessionInformationW / WTSSessionInfoEx coleta estado de
  conexao e flags de bloqueio
- A funcao interpret() retorna LOCKED somente para sessao ativa com
  WTS_SESSIONSTATE_LOCK; desconexao ou flags desconhecidas resultam em
  INACTIVE/UNKNOWN, nunca liberacao automatica
- WTSQueryUserToken e GetTokenInformation(TokenUser) consultam o SID
  real do token **somente se o sistema permitir**, geralmente sob
  LocalSystem com SeTcbPrivilege
- Execucao normal como usuario ou administrador deve exibir SID
  UNKNOWN quando nao houver privilegio; nao inferir SID a partir do
  nome de usuario ou aceita-lo como entrada JSON

O codigo inclui auto-testes dos estados LOCKED, UNLOCKED,
UNKNOWN e INACTIVE. O GitHub Actions executa esse teste, enumera
sessoes no runner Windows, testa o pipe privilegiado PING-only e
publica o executavel.

## Seguranca / limitacoes

Esta funcao ainda e apenas diagnostica, nao e um endpoint de autorizacao.
A sessao exibida nao e comparada a uma quota real ou processo facial.
O futuro servico LocalSystem deve exigir SID autentico da sessao e
revalidar sessao/saldo quando o Credential Provider requisitar
desbloqueio. Consulta WTS pode falhar: a politica deve negar, nunca
supor que a sessao esta bloqueada.

Windows 7 e Windows Server 2008 R2 possuem flags de bloqueio
invertidos; o projeto foca Windows 10/11.

Nenhuma credencial, fotografia, biometria ou saldo circula neste teste.

Documentacao Microsoft:
https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ns-wtsapi32-wtsinfoex_level1_w
https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/nf-wtsapi32-wtsquerysessioninformationw
