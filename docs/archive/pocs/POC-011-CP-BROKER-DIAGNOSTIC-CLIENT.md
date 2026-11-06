# P0-11 - Cliente de diagnostico do Credential Provider

O pacote nativo CP inclui precheck_client.h, que serializa o contrato
binario P0-9, consulta o named pipe local do Windows Broker e so
reconhece a resposta PRECHECK_ONLY (nao e uma autorizacao de login).

Por seguranca, **a DLL normal nao usa esse cliente para efetuar
login**. O cliente e invocado por uma exportacao somente do build
FACEKIDS_DIAGNOSTIC_HOST_TEST, carregado em um processo COM isolado
de teste. A DLL de producao continua devolvendo
CPGSR_NO_CREDENTIAL_NOT_FINISHED, mesmo com rosto/quota positivos.

## Prova de interoperabilidade

O workflow Credential Provider compile and host checks:
1. Compila a DLL normal (sem exportacao de teste), a DLL isolada
   e o host COM.
2. Repete validacao de SID, cenarios e campos; nenhuma senha.
3. Compila o broker C++ com WinSQLite.
4. Inicia um named pipe de uma unica requisicao, SEM instalar servico.
5. O host COM consulta o pipe pela exportacao de diagnostico e,
   por estar sob token administrativo, deve receber DENIED.
6. Encerra ambos os executaveis e remove todos os handles.
7. Publica somente os artefatos diagnosticos.

O teste nao valida que LogonUI consiga conversar com o broker ou
que existam provas faciais confiaveis. Nao integra GetSerialization
ou recuperacao de credenciais, e nao registra DLL ou SCM no Windows.

## Seguranca futura

Nunca conceder login em resposta a PRECHECK_ONLY. O broker ainda
precisa de IPC autenticado para o chamador autorizado, vinculacao
segura a sessao e camera confiavel, quota revalidada e credencial
Windows protegida. Testes de registro devem ocorrer primeiro em VM.
