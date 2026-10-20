# FaceControlKidsPC — MVP 0.1

**Projeto original:** [marquimRcc/FaceControlKidsPC](https://github.com/marquimRcc/FaceControlKidsPC)  
**Autor e mantenedor original:** Marcos Queiroz Gomes ([@marquimRcc](https://github.com/marquimRcc))  
**Licença:** [MIT](LICENSE) — software livre, inclusive para uso comercial, modificação e redistribuição.

Este é um protótipo local de **controle de tempo por reconhecimento facial** para uma conta compartilhada do Windows (`Filhos`). O objetivo é cadastrar três crianças e atribuir **120 minutos diários por criança**, reconhecendo periodicamente quem está utilizando o computador.

O reconhecimento usa **OpenCV YuNet + SFace**, com vetores faciais armazenados localmente em **SQLite**. Nenhuma imagem da webcam é transmitida pelo FaceControlKidsPC. O programa permite testar a lógica sem bloquear o computador; o bloqueio efetivo é opt-in (`--lock`).

> **Importante:** esta versão é uma prova de conceito, não um controle parental resistente a manipulação. Ainda não há interface gráfica, instalador, serviço Windows protegido ou reconhecimento antisspoof. Existe consulta periódica WTS para identificar sessão bloqueada/desbloqueada, mas falta validação em Windows real (uma fotografia pode enganar a câmera). Não foi testada com webcam real neste ambiente. A futura versão Linux/Regata OS é planejada, não validada.

## Instalação no Windows

Pré-requisito: Python 3.11 ou 3.12 e webcam com permissão de acesso. Execute no PowerShell, na pasta clonada:

```powershell
git clone https://github.com/marquimRcc/FaceControlKidsPC.git
cd FaceControlKidsPC
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m facekids.cli download-models
```

## Cadastrar três crianças

```powershell
.\.venv\Scripts\python.exe -m facekids.cli add "Filho 1" --minutes 120
.\.venv\Scripts\python.exe -m facekids.cli add "Filho 2" --minutes 120
.\.venv\Scripts\python.exe -m facekids.cli add "Filho 3" --minutes 120
.\.venv\Scripts\python.exe -m facekids.cli enroll "Filho 1"
.\.venv\Scripts\python.exe -m facekids.cli enroll "Filho 2"
.\.venv\Scripts\python.exe -m facekids.cli enroll "Filho 3"
.\.venv\Scripts\python.exe -m facekids.cli status
```

No cadastro, mantenha **somente a criança correspondente** diante da câmera. É possível apertar `Q` para cancelar.

## Executar (simulação segura)

```powershell
.\.venv\Scripts\python.exe -m facekids.cli monitor --interval 5
```

O monitor lê um rosto a cada 5 segundos, exige duas identificações consistentes e para a contagem quando não tem certeza de quem está presente. Na conta Windows bloqueada/desconectada, o monitor libera a câmera e pausa o cronômetro. Ao desbloquear, exige nova identificação. Se a criança não tem saldo ou não há identificação por 30 segundos, imprime **[SIMULAÇÃO]** em vez de bloquear. Cada criança tem saldo independente para cada data local.

### Habilitar bloqueio real, somente depois dos testes

```powershell
.\.venv\Scripts\python.exe -m facekids.cli monitor --interval 5 --lock
```

**Atenção:** rode este comando somente na conta Windows `Filhos` (ou indique `--monitored-user NOME_DA_CONTA`). O programa recusa o bloqueio quando o usuário atual não corresponde à conta monitorada. Esse comando chama `LockWorkStation` no Windows. A sessão pode ficar em um ciclo de bloqueio após desbloqueio. A webcam normalmente não funciona na tela bloqueada, e o protótipo ainda não escuta eventos nativos de sessão. Deixe um administrador responsável com acesso para interromper o protótipo.

## Estrutura

| Caminho | Função |
| --- | --- |
| `facekids/cli.py` | Comandos de cadastro, download de modelos e monitoramento |
| `facekids/recognition.py` | Identificação facial YuNet + SFace |
| `facekids/storage.py` | Pessoas, embeddings e consumo diário no SQLite |
| `facekids/policy.py` | Regras de saldo, confirmação facial e pausa da sessão |
| `facekids/monitor.py` | Captura da webcam, consulta da sessão e contagem periódica |
| `facekids/session.py` | Identificação de sessão ativa ou bloqueada pela API WTS no Windows |
| `facekids/locker.py` | Bloqueio nativo (Windows; Linux a validar) |
| `tests/` | Testes de regras e persistência |

Execute os 12 testes automatizados (incluem bloqueio/desbloqueio, suspensão lógica, troca de criança e reconhecimento simulado) sem webcam:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Próximas etapas

1. Validar reconhecimento dos três filhos no Windows, com diferentes condições de iluminação.
2. Validar a detecção periódica WTS em Windows 10/11 real e adicionar eventos nativos de sessão/suspensão (no protótipo a consulta ocorre a cada intervalo).
3. Proteger configuração e histórico em serviço com permissões administrativas; iniciar automaticamente na conta `Filhos`.
4. Criar interface gráfica para administração parental e instalador.
5. Validar o bloqueio do KDE/Regata OS, mantendo o reconhecimento e o SQLite comuns às plataformas.
6. Avaliar detecção de falsificação facial (liveness), segurança de dados biométricos e testes de câmera.

## Licença e créditos

Copyright © 2026 **Marcos Queiroz Gomes** ([@marquimRcc](https://github.com/marquimRcc)).

**MIT License:** você pode usar, copiar, modificar, publicar e distribuir o projeto livremente, inclusive comercialmente. A condição legal é **preservar o aviso de direitos autorais e o texto da licença MIT** em todas as cópias ou partes substanciais do software.

Ao redistribuir ou criar derivados, pedimos também que seja mantida uma referência ao **repositório original:** https://github.com/marquimRcc/FaceControlKidsPC. Esse link de origem é um **pedido de atribuição adicional**, não uma obrigação separada da licença MIT.

### Projetos e modelos de referência

A arquitetura de reconhecimento e bloqueio é **inspirada** em [CrySence](https://github.com/crymetr/crysence) (MIT) e [Desk Guard](https://github.com/Todilo/desk-guard) (MIT). O protótipo usa APIs públicas do OpenCV, **não** copia os códigos desses repositórios.

Os modelos ONNX YuNet/SFace são baixados explicitamente pelo comando `download-models` da distribuição de modelos utilizada pelo CrySence. **Os arquivos ONNX não são incluídos neste repositório.** Antes de redistribuir modelos ou empacotar instaladores, verifique as licenças específicas de cada modelo e das dependências, que podem ser diferentes da licença deste código.

Os dados biométricos de crianças nunca devem ser commitados; `.gitignore` exclui o banco local e os modelos baixados.

## Avanço do MVP 0.2 — sessão Windows e cronômetro

- Consulta periódica de bloqueio/desbloqueio pelo Windows Terminal Services (WTSInfoEx), conforme [documentação Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ns-wtsapi32-wtsinfoex_level1_w).
- Quando a sessão não está ativa ou seu estado é incerto, a captura da webcam é liberada e o cronômetro é pausado.
- Depois de desbloquear, exige-se nova identificação de dois quadros consecutivos; uma criança sem saldo continua bloqueada e outra com saldo pode usar a conta compartilhada.
- Proteção para evitar que a execução acidental do bloqueio real na conta do administrador bloqueie o próprio administrador.
- Modo de bloqueio real indisponível no Linux até validação no Regata OS; simulador continua disponível.
- O banco SQLite continua **na pasta do usuário atual**. Na versão 0.2, para teste, cadastre os perfis e inicie o programa na **mesma conta Windows** (idealmente a conta `Filhos`). A administração separada e protegida ainda será desenvolvida.

**Validação:** 12 testes de lógica e persistência executados em ambiente Linux; ainda pendente teste de webcam e consulta WTS em Windows real. **Não considere este MVP uma proteção parental definitiva.**
