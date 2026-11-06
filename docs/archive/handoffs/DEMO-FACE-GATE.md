# Demonstração visual do Face Access Gate

**Branch:** feature/face-access-gate  
**Status:** Experiência visual e máquina de estados em memória (sem autenticação ou bloqueio do Windows).

## Executar no Windows

Na branch feature/face-access-gate, com Python 3.11 ou 3.12:

    py -3.11 -m facekids.gate_preview

Ou dê dois cliques no arquivo demonstrar-gate.bat. Para esta demonstração, não precisa de OpenCV, downloads de modelos ou webcam; usa somente Tkinter, da biblioteca padrão do Python.

## Cenários para experimentar

1. Clique em **Simular reconhecimento** do Filho 1: duas amostras simuladas, autorização visual.
2. Observe o tempo individual desse filho diminuir; os outros saldos não mudam.
3. Clique no Filho 2: a tela restringe enquanto verifica a troca; depois libera o Filho 2.
4. Clique em **Sem rosto**: o cronômetro pausa e a tela fica restrita após 15 segundos. Se o mesmo rosto voltar antes, a autorização é mantida.
5. Clique em **Desconhecido** ou **Dois rostos**: o gate se restringe imediatamente.
6. Clique em **Erro na câmera** ou **Erro no serviço**: demonstra falha segura na tela visual.
7. Use **Avançar 15 min** várias vezes com um filho autorizado até esgotar o saldo. Ele não consegue ser liberado novamente; outro filho ainda pode.
8. **Reiniciar teste** repõe somente dados fictícios. Use **Sair** ou Esc para fechar sem risco de travar a sessão.

## Importante: modelo de ameaça

Esta janela é deliberadamente normal: não é tela cheia, não é sempre no topo e não captura atalhos do Windows. A opção A ainda não garante proteção contra alguém que encerre a janela, interrompa o agente ou acesse o Gerenciador de Tarefas.

A demonstração **não grava no SQLite, não acessa a webcam, não instala serviços, não chama LockWorkStation nem desbloqueia o Windows**. A autorização é somente visual, para analisar o fluxo e o layout.

Na próxima etapa técnica poderemos conectar observações reais do YuNet/SFace, mantendo um modo de simulação selecionável e o botão de emergência do pai. Somente depois devem ser considerados IPC seguro, watchdog e eventual tela de restrição persistente.

Código principal: facekids/gate_model.py (testável sem interface) e facekids/gate_preview.py (Tkinter).
