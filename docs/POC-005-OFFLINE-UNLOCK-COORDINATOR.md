# P0-4 - Coordenador offline entre reconhecimento, quota e login Windows

**Estado:** modulo Python puro com testes; NAO e um servico Windows,
nao possui IPC autenticado e nao desbloqueia o computador.

## Fluxo simulado

1. O responsavel configura SIDs locais distintos para administrador e Filhos.
2. Um futuro worker de camera confiavel entrega evidencias faciais recentes.
3. O leitor WTS do futuro servico informa o SID real da sessao, seu ID e
   se permanece bloqueada. Essas informacoes nao podem vir do usuario Filhos.
4. O coordenador verifica identificacao, vivacidade, confirmacoes e quota.
5. Uma autorizacao curta (8 segundos) fica dentro do coordenador, sem
   expor o token a um processo usuario.
6. Na solicitacao posterior do LogonUI, o coordenador verifica sessao
   bloqueada e quota novamente. O token so pode ser consumido uma vez.
7. GRANTED representa permissao de politica, NAO uma credencial Windows.

## Regras de seguranca testadas

- Quota de cada uma das tres criancas e independente.
- Sessao administrativa, outras contas ou sessao divergente nao autorizam.
- Sessao desbloqueada nao permite criar ou consumir token.
- Face desconhecida, varias faces, liveness negativo, camera com erro
  ou amostra antiga impedem o desbloqueio.
- Alteracao de identidade revoga imediatamente o token anterior.
- Saldo esgotado depois do reconhecimento impede a autorizacao.
- Falha de WTS/consulta de saldo impede a autorizacao.
- Token expira, e de uso unico e pode ser invalidado por watchdog.

## O que ainda nao esta pronto

Este modulo aceita objetos Python; ele nao confirma por si so que a
camera, a consulta WTS ou a cota vieram de fontes confiaveis. O
future servidor privilegiado deve manter os objetos inacessiveis a
processos da conta Filhos, autenticar o chamador LogonUI, verificar
impersonation/ACL do named pipe e obter as evidencias de uma origem
que a conta infantil nao consiga falsificar.

A integracao com Windows exige ainda implementacao de SCM service,
banco protegido em ProgramData, credencial Filhos protegida e teste de
registro COM em VM com snapshot e recuperacao.

Nenhuma senha, imagem facial ou SID real e gravado no repositorio.

## Executar os testes

Na conta principal, dentro da branch feature/windows-native-unlock-poc:

    .\.venv\Scripts\python.exe -m unittest discover -s tests -v

Ou use o script Testar-Integracao-Windows.ps1 que ja chama toda a suite.
