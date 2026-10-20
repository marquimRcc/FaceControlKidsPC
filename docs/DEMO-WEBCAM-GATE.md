## Modo webcam real (opt-in, branch experimental)

Além da demonstracao manual, agora e possivel abrir uma janela independente
de TESTE COM WEBCAM. Ela nao controla a sessao do Windows e nao desconta
o tempo real. Tudo e processado localmente, sem salvar videos.

### Primeiro uso no Windows (na conta Filhos)

Instale Python 3.11 com Tkinter, execute na pasta do projeto:

    py -3.11 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv\Scripts\python.exe -m facekids.cli download-models
    .\.venv\Scripts\python.exe -m facekids.gui

No painel, cadastre os filhos e cadastre os rostos separadamente. Feche
o cadastro antes de iniciar a leitura. Em seguida:

    .\.venv\Scripts\python.exe -m facekids.gate_webcam_preview

Ou execute testar-webcam-gate.bat. Opcoes para diferentes dispositivos:

    .\.venv\Scripts\python.exe -m facekids.gate_webcam_preview --camera-index 1 --interval 2

A primeira leitura identificada mostra verificacao; a segunda leitura
consecutiva confirma e mostra liberacao visual. Uma pessoa ausente pausa
a contagem demonstrativa. Duas pessoas ou rosto desconhecido restringem
a autorizacao visual. Falha/desconexao da camera tambem restringe.

O programa consulta o SQLite em modo somente leitura; amostras de rosto
ja cadastradas devem estar na mesma conta do Windows. A demonstracao
copia os saldos remanescentes de hoje e altera somente os valores em RAM.

Importante: sem liveness/antifraude por foto; nenhuma seguranca nativa
do Windows foi implementada. Pressione Esc para sair a qualquer momento.

Para o modo totalmente simulado sem webcam, continue usando:

    py -3.11 -m facekids.gate_preview
