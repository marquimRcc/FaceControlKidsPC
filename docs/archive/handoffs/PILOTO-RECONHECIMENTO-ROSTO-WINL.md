# Diagnostico: rosto do responsavel durante Win+L

Ensaio opcional, com camera XWF-1080P e cadastro adulto previamente
feito em \`%LOCALAPPDATA%\FaceKids\piloto-responsavel\piloto.sqlite3\`.

- A webcam continua no processo do usuario quando a sessao e bloqueada
  (nao existe captura autenticada pela interface LogonUI)
- Consulta WTS antes e depois do frame, descarta transicoes de sessao
- So compara frames bloqueados contra os 12 vetores ja cadastrados
- Requer 3 correspondencias consecutivas em ate 5 segundos
- Na tela bloqueada, a pessoa deve estar diante da webcam por 40-60 s
- Nenhuma imagem, foto, video, novo embedding ou resultado persistente
  e armazenado; nenhum registro, login, servico ou senha muda

Saidas possiveis:
- MATCH_OBSERVED_DURING_WIN_L_DIAGNOSTIC_ONLY
- LOCKED_FRAMES_WITHOUT_MATCH
- NO_USABLE_LOCKED_FRAMES
- INCONCLUSIVE_NOT_ENOUGH_LOCKED_SAMPLES

**Importante**: Mesmo o primeiro resultado NAO comprova liveness,
Secure Desktop, autenticacao da identidade do processo, nem
capacidade de desbloquear o Windows. Falta um Credential Provider
realmente seguro, testado em VM recuperavel; nunca instalar
o provider experimental atual no computador real.
