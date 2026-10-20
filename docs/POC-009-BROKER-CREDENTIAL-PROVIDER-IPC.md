# P0-9: contrato de diagnostico entre Windows Broker e Credential Provider

**Status:** implementado no broker nativo e testado sem instalacao no
Windows. O Credential Provider nao consome o contrato ainda.

## Interface

Mensagem binaria de 16 bytes contendo magic=FKC1 (little endian),
versao 1, operacao 1=PRECHECK, session_id Windows e child_id 1..3.

A mensagem nao recebe SID, senha, saldo, tokens ou resultados faciais
do caller; os dados devem ser consultados no broker. Mensagens com
tamanho incorreto, versao invalida ou ids fora de faixa falham fechadas.

## Checagens feitas no broker

1. Pipe local com DACL restrita a SYSTEM e administradores.
2. Operacao PRECHECK autorizada apenas quando TokenUser de quem
   se conectou e exatamente S-1-5-18 (LocalSystem), validado apos
   ImpersonateNamedPipeClient. Administradores comuns nao podem.
3. SID de conta-alvo lido da configuracao administrativa em HKLM.
   Chave inexistente/invalida implica negar, sem fallback.
4. Consulta WTS + WTSQueryUserToken, sem confiar em nomes/SIDs enviados
   pelo cliente. Sessao deve estar bloqueada, e token vinculado a
   conta Filhos correta.
5. Consulta do SQLite protegido em ProgramData, saldo positivo do filho
   requisitado e data do relogio do servidor.

Resposta positiva: PRECHECK_ONLY. Ela significa apenas que
pre-condicoes de sessao e quota permitem uma futura **analise facial**.
Nao concede login, nao libera quota, nao contem credenciais e
nao substitui a checagem posterior do saldo no ato de autenticar.

## Lacunas de seguranca e entrega

Apenas validar o SID SYSTEM nao identifica especificamente o processo
LogonUI/um Credential Provider autorizado; todo processo LocalSystem
pode ser potencialmente privilegiado. Portanto nenhuma operacao
de credenciais ou tickets de desbloqueio esta exposta neste protocolo.

A opcao facial diagnostica do Credential Provider ainda responde
CPGSR_NO_CREDENTIAL_NOT_FINISHED. Ainda faltam:
- canal de consulta do Provider integrado, com garantia de identidade
- camera/trusted worker e antisspoof funcional na tela bloqueada
- conectores reais de quota/identidade e auditoria do servico
- instalacao e recuperacao apenas em VM primeiro

## Verificacao

O GitHub Actions compila o broker e executa --self-test (versoes,
comprimentos e valores de mensagens, ACL, quotas e WTS), alem de
um teste de cliente administrativo que deve receber DENIED ao pedir
PRECHECK sem executar como LocalSystem. Nao instala servicos.
