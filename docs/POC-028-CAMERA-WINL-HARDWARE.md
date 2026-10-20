# P0-28 — Diagnostico seguro da webcam durante Win+L

Foi adicionado \`facekids/hardware_camera_probe.py\` para uma execucao
**opt-in** na conta Windows ja conectada.

Nao e instalacao de servico, Credential Provider ou desbloqueio de
Windows. O script usa OpenCV DirectShow para ler frames enquanto o
responsavel testa Win+L, coleta APENAS contadores em memoria e consulta
o estado WTS da propria sessao obtida via ProcessIdToSessionId. Nenhum
frame, nome de crianca, embedding ou foto e salvo/transmitido.

Requisitos antes do teste real:
- Windows 10/11 e webcam funcionando nessa conta
- Python 3.11 e dependencias de requirements.txt
- Procedimento manual de bloquear a sessao (Win+L) e aguardar
- Recomenda-se executar inicialmente pela conta administrativa,
  que ja possui o ambiente Python, sem cadastrar rosto infantil

Na conta principal, em um terminal com o projeto atualizado:

    .\.venv\Scripts\python.exe -m facekids.hardware_camera_probe --duration 120

O programa mostra numero de amostras WTS LOCKED, frames e leituras
nao uniformes. Resultado
FRAMES_DURING_WIN_L_PRELIMINARY_ONLY significa **evidencia inicial
naquela sessao**; nao comprova acesso a LogonUI ou captura de
uma fonte protegida contra um processo controlado pela conta Filhos.
A camera ainda nao e usada como identidade ou liveness.

No CI, testes inteiramente sinteticos validam que frames com sessao
UNLOCKED/INACTIVE/UNKNOWN nunca contam como evidencia de Win+L.
O CI nao tem a webcam fisica do usuario e nao executa o teste real.

O resultado da P0-28 em hardware permanece PENDENTE ate o usuario
executar o script voluntariamente. Nao requisitar fotos de menores.
