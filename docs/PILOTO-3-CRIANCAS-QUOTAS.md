# Piloto infantil — reconhecimento + 120 minutos (P0-56..61, etapa inicial)

Branch: \`feature/filhos-face-quota-pilot\` (iniciada depois da
demonstracao bem-sucedida do rosto do responsavel em Win+L).

## Escopo concordado

- Conta administrativa \`MarcosMiniPC\`: **fora** do desbloqueio facial
  e da politica de bloqueio; PIN/senha do Windows intactos.
- Conta compartilhada \`Filhos\`: tres perfis faciais distintos
  (\`Crianca 1\`, \`Crianca 2\`, \`Crianca 3\`), com 120 minutos/dia.
- Bloqueio simples \`Win+L\` por quota: etapa a validar NA conta Filhos
  somente; PIN/senha tradicional continua funcionando.
- Sem firewall nem filtragem de conteudo neste marco.
- Nenhum Credential Provider instalado, nenhuma tarefa de inicio
  automatico, nenhuma alteracao de Windows LogonUI.

## Primeira rodada: conta do responsavel, sem bloqueio real

Abra o PowerShell normal no projeto, atualize a branch e execute
\`scripts/Iniciar-Piloto-Filhos.ps1\`. O menu permite cadastrar os
perfis um a um, visualizar saldo, executar 90s de identificacao
facial e cronometro **em simulacao sem Win+L**, e apagar templates.
No monitor, um rosto so pode ser identificado se tres observacoes
consecutivas confirmarem o mesmo perfil; troca, camera desconhecida,
sessao bloqueada ou virada de dia pausam a cobranca de tempo.

As amostras sao feitas com 12 frames por perfil, com coleta completa
antes de qualquer gravacao no SQLite; cancelamento nao substitui
cadastro anterior. As fotos/video nunca vao para disco. Vetores
SFace **sao dados biometricos sensiveis** e ficam apenas no
\`%LOCALAPPDATA%\FaceKids\piloto-filhos\criancas.sqlite3\` do
usuario Windows que executou o menu.

NAO enviar o SQLite ao GitHub, nem capturas da webcam ou material
das criancas para a conversa. Compartilhar apenas contagens e
estados, sem nomes, imagens ou embeddings.

## Limitacoes do piloto — importante

A base SQLite e por usuario e **nao protegida por LocalSystem**.
Um usuario pode modificar seus saldos ou templates. Se cadastrar
os rostos em \`MarcosMiniPC\`, a conta \`Filhos\` nao tera acesso
a essa base. A primeira rodada e APENAS para testar reconhecimento
e cronometro na webcam. Depois, com os resultados, definiremos
armazenamento protegido e transferencias seguras sem copiar bases
biometricas entre perfis manualmente.

\`python -m facekids.children_pilot monitor --real-lock --confirm-real-lock\`
so solicita Win+L no Windows quando o token Windows e da conta
\`Filhos\`. Sem os dois argumentos, bloqueio e **apenas simulado**.
Nao executar a opcao real antes dos testes de identidade, WTS e
recuperacao no PC alvo. Este bloqueio nao proibe que a crianca
desbloqueie com PIN/senha (aceito no escopo atual).

Sem rosto identificado, o piloto pausa a cobranca e nao bloqueia
por rosto desconhecido; isto ainda nao constitui um mecanismo
seguro de imposicao de tempo.

A etapa seguinte deve integrar o ledger de quota do servico
Windows protegido, tolerar encerramento do processo, mudancas
de data/clock e oferecer recuperacao sem bloquear o administrador.
