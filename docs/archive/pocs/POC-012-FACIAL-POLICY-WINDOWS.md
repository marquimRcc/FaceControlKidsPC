# P0-12 — Politica interna de evidencias faciais e saldo

**Estado:** desenvolvimento em C++ completo para a maquina de estados
offline; CI Windows e SCM runner aprovados. **Nao e desbloqueio facial.**

O modulo native/windows_broker_poc/facial_policy.h combina uma
amostra facial **sintetica em teste** com a verificacao de:
- ID da crianca 1, 2 ou 3, vinculado a quota propria
- exatamente uma face e pelo menos tres confirmacoes
- camera saudavel e resultado positivo de liveness
- timestamp monotônico recente (ate 3 segundos)
- estado de sessao Windows bloqueada, token SID de Filhos
- quota em SQLite protegido >0

Uma primeira avaliacao bem-sucedida guarda apenas o identificador
de crianca, a sessao e o instante no processo do broker. A segunda
etapa consome e invalida esse estado de uso unico, rechecando
SID/WTS e quota. Expira apos 8 segundos. Mudanca de rosto,
camera inoperante, clock regressivo e qualquer observacao invalida
apagam a pendencia anterior.

## Seguranca da fronteira de confianca

O sinal de liveness do teste e um booleano SIMULADO, nao um
detector antisspoof. E a origem ProtectedWorker e um marcador
de interface, NAO uma identidade atestada criptograficamente.

Para garantir autenticacao de fato, a captura e o reconhecimento
precisam rodar em processo que o usuario Filhos nao controla,
ter integridade e origem verificaveis e ser associados ao
mesmo Session ID. Nao devemos aceitar identificacoes ou flags
"liveness" enviadas pela conta infantil via named pipe.

O metodo InternaFacePolicy e apenas uma camada de regras C++.
Nao esta disponivel como operacao IPC, nao gera ticket para o
Credential Provider, nao fornece senha e nao libera Windows.

## Provas automatizadas

--self-test cria e remove um banco SQLite protegido temporario,
testa confirmacao facial, trocas, expiracao, quota esgotada,
replay e revogacao. O workflow de ciclo SCM no runner Windows
tambem compila e executa esses testes antes de instalar o
servico efemero.

## Proximos passos reais

1. Especificar e testar a origem confiavel da captura (hoje ainda
   a webcam remota da conta Filhos foi testada apenas como video
   durante Win+L, nao em LogonUI)
2. Integrar identificacao biometrica e liveness verificaveis
3. Validar com tres criancas reais sob consentimento parental,
   dados armazenados e protegidos localmente
4. Segregar canal do Credential Provider de outros processos
   LocalSystem e implementar recuperacao segura
5. Prosseguir ao login real apenas apos ambiente VM validado

Verificar CI: .github/workflows/windows-broker-build.yml e
.github/workflows/windows-broker-scm-vm.yml
