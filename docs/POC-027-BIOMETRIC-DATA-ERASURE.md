# P0-27 — Remocao local de modelos faciais pelo responsavel

O armazenamento Python da demonstracao agora oferece a operacao de
administrador `remove_faces` com o ID do perfil. Remove **somente**
embeddings SFace daquele filho, cancela cadastro pendente daquele perfil
e pausa a politica de acesso visual. A conta Filhos nao pode executar
esta operacao pelo broker Python.

A inicializacao do SQLite da demonstracao habilita
`PRAGMA secure_delete=ON`, para reduzir bytes residuais em paginas.
**Nao garante exclusao forense** de SSD, snapshots, backups ou WAL
anteriores. Nao foram exportadas, enviadas ou processadas imagens
de menores no CI: os testes usam vetores artificiais.

Os registros de quota e outros filhos permanecem intactos, confirmado
em testes. O SQLite da demonstracao em LOCALAPPDATA permanece
**sem protecao contra adulteracao pela conta**; o futuro servico deve
armazenar as caracteristicas biometricas em diretorio ACL protegido
sob LocalSystem antes de ser considerado seguro.

Nao instalar Credential Provider nem afirmar que houve autenticao
facial real.
