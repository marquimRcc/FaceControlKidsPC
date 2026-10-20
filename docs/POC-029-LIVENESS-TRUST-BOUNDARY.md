# P0-29 — Liveness simulado nao e prova de identidade

**Estado:** protecao fail-closed em codigo C++. Nao ha detector
de liveness real; nao ha autorizacao de login Windows.

A classe `InternalFacePolicy` agora nega observacoes por padrao.
Mesmo que a estrutura de teste contenha:
- origin=ProtectedWorker
- liveness_passed=true
- camera_healthy=true
- child_id valido e amostra recente

...o fluxo de producao retorna DeniedUntrustedOrigin, porque nenhuma
dessas flags prova sua origem ou autenticidade.

Para manter regressao automatizada, os auto-testes sinteticos usam
explicitamente `InternalFacePolicy::for_synthetic_self_test()`.
Este factory e *somente uma configuracao de teste* e nunca deve ser
exposto via API publica, pipe, UI ou dados da conta Filhos. O caminho
padrao permanece negado ate existir worker confiavel com captura,
liveness genuino, ligacao a WTS SID e quota protegida.

A P0-29 nao resolve ataques com foto/video: testes de apresentacao
reais permanecem pendentes em hardware com autorizacao dos pais.

Provas: Workflow Windows broker build e SCM lifecycle executam
`--self-test` incluindo default deny + operacoes sinteticas.
