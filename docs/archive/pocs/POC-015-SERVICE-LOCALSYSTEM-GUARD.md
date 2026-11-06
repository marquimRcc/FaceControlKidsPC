# P0-15 - Exigir LocalSystem no broker Windows

O processo do serviço verifica o SID real do TokenUser ANTES de
abrir as quotas e expor o named pipe. Somente S-1-5-18
(NT AUTHORITY\SYSTEM / LocalSystem) pode inicializar o serviço.

Um administrador elevado nao e LocalSystem. Um servico SCM
configurado para outra conta deve recusar a inicializacao
com ERROR_ACCESS_DENIED, sem expor o broker.

O diagnostico --service-identity e somente leitura e
mostra SYSTEM, NOT_SYSTEM ou IDENTITY_UNAVAILABLE.
Ele nao altera permissoes, registro ou senhas.

Testes Windows GitHub Actions:
- IDs de SID conhecidos incluindo SYSTEM e Administradores
- CLI do runner elevado deve responder NOT_SYSTEM
- Serviço SCM criado em runner descartável como LocalSystem
  deve chegar a RUNNING, abrir o SQLite restrito e responder PING
- Testes continuam removendo o serviço e a pasta temporaria

Mesmo isso NAO prova a origem de frames da camera, identidade
facial, liveness ou capacidade de autenticar no LogonUI.
Nenhum componente e instalado no computador familiar.
