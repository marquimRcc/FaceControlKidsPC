# P0-26 — Diagnostico de um frame Media Foundation em memoria

**Escopo:** apenas diagnostico opt-in, nao autenticacao nem liveness real.

- `native/windows_broker_poc/camera_frame_probe.h` abre uma camera por
  Media Foundation e tenta ler **um unico frame RGB32**.
- O frame permanece apenas em memoria. O codigo calcula uma medida
  simples de uniformidade e descarta a memoria COM, sem salvar foto ou
  modelo biometrico.
- O CLI `FaceKidsBrokerPoc.exe --frame-probe` so executa sob comando
  explicito; nao e chamado na inicializacao do SCM, por LogonUI
  nem pelo pipe da conta Filhos.
- `--self-test` exercita o processamento de bytes com frames artificiais.
  GitHub Actions valida compilacao e auto-testes sem precisar de camera.
- **Nao assumir** que camera ausente no runner equivale a falha na
  webcam real do computador familiar.
- **Nao inferir** identidade, vivacidade, resistencia a foto ou
  permissao de login por ter encontrado um frame.
- `capture_one_frame` usa leitura Media Foundation sincrona; uma camera
  defeituosa pode bloquear o diagnostico. Por isso nao e integrado
  automaticamente ao servico nem ao Secure Desktop.

## O que falta

Provar capturas fisicas no hardware alvo, avaliar isolamento da sessao
de usuario e implementar um worker protegido com canal autenticado.
Depois: reconhecimento com cadastro consentido de cada filho, liveness
real testado contra fotos/videos e seguro de recuperacao em VM.

Nao registrar o Credential Provider na maquina principal.
