# P0-42 — Tempo por criança medido no lado do serviço

O header \`native/windows_broker_poc/usage_meter.h\` define uma
máquina de estados nativa para contabilização baseada em tempo
monotônico (milissegundos) e débito transacional no WinSQLite.

Testes simulam:
- quota de 120 minutos independente para cada filho
- arredondamento para segundos inteiros, sem perder frações
- sessão Windows bloqueada, desconectada ou identidade divergente
- troca do Session ID e do SID consultado pelo sistema
- relógio monotônico retrocedendo ou dia civil mudando
- consumo prolongado que zera quota sem saldo negativo
- cancelamento de medição e necessidade de reiniciar confirmação

**FRONTEIRA CRÍTICA:** o construtor normal do medidor NÃO permite
iniciar uma sessão; somente o autoteste privado consegue simular
atribuição de uma criança. Não existe ainda uma fonte confiável de
identificação facial nem integração com desbloqueio do Windows.
Não expor operações do medidor no IPC ou permitir que o processo
Filhos informe seu próprio ID, tempo consumido ou sinais de liveness.

O medidor não bloqueia Windows automaticamente e não deve ser
tratado como controle parental à prova de manipulação. Também exige
decisão adicional sobre como dividir tempo de uso na virada do dia
e como recuperar tempo de uso após reinício/desligamento inesperado.
O runtime está intencionalmente fail-closed.
