# Parecer Tecnico e Diretrizes de Implementacao

## 1. Warm-up V4L2
Descartar os primeiros 15 frames apos abrir /dev/video0 para evitar quadros pretos por falta de autoexposicao.

**Aplicado.** Runtime, diagnóstico e cadastro agora aquecem a câmera. No teste
real posterior, os 31 quadros medidos ficaram utilizáveis, com brilho médio
90,74; nenhum rosto estava diante da câmera durante o teste.

## 2. Desbloqueio sem PAM
Usar diretamente loginctl unlock-session quando LockedHint for True e rosto valido for detectado.

**Aplicado com controles adicionais.** O serviço exige três confirmações do
mesmo rosto na mesma sessão bloqueada, revalida quota e horário imediatamente
antes do comando e limita pedidos repetidos. A opção `--no-auto-unlock` permite
desativar o mecanismo para diagnóstico e recuperação.

## 3. Notificacoes
Adicionar notify-send 15 segundos antes de bloquear a sessao.

**Pendente.** Um serviço root não deve presumir o barramento D-Bus da sessão.
A notificação será implementada apenas depois de validar um canal dirigido à
sessão `filhos`, sem permitir que a conta compartilhada influencie decisões do
controlador.
