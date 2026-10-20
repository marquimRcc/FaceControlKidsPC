# P0-38 — Remocao administrativa de embeddings no broker Windows

Adicionada operacao IPC binaria kEraseTemplates=2, limitada ao pipe
local com DACL SYSTEM/Administradores. No servidor, o Windows fornece
o token real do cliente apos ImpersonateNamedPipeClient; a operacao
requer CallerRole::Administrator (grupo efetivamente habilitado).

- Mensagem tem 16 bytes, apenas child_id 1..3; session_id DEVE ser zero
- A operacao NAO aceita fotos, modelos ou caminhos enviados pelo cliente
- Apaga exclusivamente os templates armazenados daquele perfil no SQLite
  protegido do LocalSystem; nao mexe em quota, senha ou outros filhos
- Resposta ERASED sem transmitir dados biometricos nem contagens
- Clientes da conta Filhos nao conseguem abrir o pipe protegido
- O Credential Provider nunca envia operacao de exclusao, nem recebe senha
- A unica maneira de disparar a manutencao neste PoC e um admin elevado
  executar explicitamente FaceKidsBrokerPoc.exe --erase-templates 1..3

GitHub Actions valida em Windows runner descartavel:
- parser recusa child_id errado ou session_id incoerente
- servico LocalSystem aceita exclusao sem templates reais
- child-like token nao pode acessar pipe/banco
- id 4 rejeitado antes de abrir o canal

***Limites***: este teste nao comprova eliminacao definitiva
em SSD, backups, WAL antigos ou snapshots. PRAGMA secure_delete=ON
so reduz bytes residuais nas paginas SQLite. Ainda nao existe cadastro
facial real nem autorizacao para desbloquear Windows. O comando nao
deve ser utilizado no PC familiar ate haver instalacao segura em VM.
