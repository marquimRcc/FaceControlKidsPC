# FaceControlKidsPC — Windows Native Unlock PoC (branch experimental)

> **Branch ativa:** `feature/windows-native-unlock-poc`. A `main` continua com o MVP anterior. O bloqueio/desbloqueio por rosto ainda **não está implementado**; a autenticação nativa nunca deve ser modificada enquanto os componentes estão em prova de conceito.

## Estado técnico — Windows (20/10/2026)

- **Webcam durante Win+L:** diagnóstico na conta Filhos confirmou leitura de frames durante bloqueio do Windows. Isto não comprova execução dentro do LogonUI.
- **Política individual:** 74 testes Python aprovados (face, sessão, 3 quotas, expiração e autorização de uso único).
- **Credential Provider:** DLL COM diagnóstica compilada; enumera tile somente para SID autorizado, mas não serializa nenhuma credencial.
- **Broker Windows P0-5:** estrutura SCM C++ compilada com named pipe local que admite apenas SYSTEM/administradores elevados e responde somente PING. Testado no GitHub Actions sem instalar serviço.
- **Quotas nativas P0-8:** WinSQLite protegido por DACL SYSTEM/administradores em ProgramData (somente quando o serviço SCM for instalado em VM); testes offline com 3 saldos, débitos atômicos, virada de dia, persistência e rejeição de ACLs permissivas. O broker combina validação de SID/WTS com saldo antes de considerar uma solicitação para análise facial.
- **Ainda faltam:** validação do SCM/LocalSystem em VM, IPC autenticado do Credential Provider, evidência facial confiável, mapeamento entre rosto e saldo, cofre seguro da credencial Filhos, instalação/rollback em VM e teste efetivo de LogonUI. SQLite/ACL e verificação WTS foram implementados como componentes nativos, mas ainda sem serviço instalado.

### Repositório local da conta principal

O clone fica em `C:\Users\MarcosMiniPC\Documents\git\FaceControlKidsPC`.

Para atualizar e testar sem alterar o login:

```powershell
$p="C:\Users\MarcosMiniPC\Documents\git\FaceControlKidsPC"; git -C $p pull --ff-only; if($LASTEXITCODE -ne 0){throw "Falha ao atualizar"}; powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$p\scripts\Testar-Integracao-Windows.ps1"
```

Os binários C++ de diagnóstico são compilados e testados automaticamente no GitHub Actions. **Não registrar manualmente Credential Provider ou instalar o serviço experimental no PC.**

Veja [Arquitetura nativa](docs/ADR-003-WINDOWS-REAL-FACE-UNLOCK.md), [associação de SID](docs/POC-004-WINDOWS-SID-BINDING.md), [autorização por quota](docs/POC-005-OFFLINE-UNLOCK-COORDINATOR.md) e [broker C++](native/windows_broker_poc/README.md).

---


## Testar a identificacao facial pela webcam (novo)

Com OpenCV, modelos baixados e os rostos cadastrados na conta Filhos, rode:

    .\.venv\Scripts\python.exe -m facekids.gate_webcam_preview

Ou abra testar-webcam-gate.bat. A tela reconhece rostos por YuNet/SFace,
mostra estados e saldos, mas nao altera SQLite nem bloqueia o Windows.
Pressione Esc para sair. Consulte docs/DEMO-WEBCAM-GATE.md.

## Testar a tela de acesso facial sem webcam

Use Python 3.11+ no Windows. Com a branch selecionada, execute:

    py -3.11 -m facekids.gate_preview

Ou abra **demonstrar-gate.bat** com dois cliques. Os botões simulam reconhecimentos e falhas. Não precisa cadastrar rostos nem instalar dependências externas. **Esc fecha a janela imediatamente.** Leia a documentação em [docs/DEMO-FACE-GATE.md](docs/DEMO-FACE-GATE.md).

---

**Projeto original:** [marquimRcc/FaceControlKidsPC](https://github.com/marquimRcc/FaceControlKidsPC)  
**Autor e mantenedor original:** Marcos Queiroz Gomes ([@marquimRcc](https://github.com/marquimRcc))  
**Licença:** [MIT](LICENSE) — software livre, inclusive para uso comercial, modificação e redistribuição.

Este é um protótipo local de **controle de tempo por reconhecimento facial** para uma conta compartilhada do Windows (`Filhos`). O objetivo é cadastrar três crianças e atribuir **120 minutos diários por criança**, reconhecendo periodicamente quem está utilizando o computador.

O reconhecimento usa **OpenCV YuNet + SFace**, com vetores faciais armazenados localmente em **SQLite**. Nenhuma imagem da webcam é transmitida pelo FaceControlKidsPC. O programa permite testar a lógica sem bloquear o computador; o bloqueio efetivo é opt-in (`--lock`).

> **Importante:** esta versão é uma prova de conceito, não um controle parental resistente a manipulação. Já existe painel gráfico experimental; ainda não há instalador nem serviço Windows protegido ou reconhecimento antisspoof. Existe consulta periódica WTS para identificar sessão bloqueada/desbloqueada, mas falta validação em Windows real (uma fotografia pode enganar a câmera). Não foi testada com webcam real neste ambiente. A futura versão Linux/Regata OS é planejada, não validada.

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
4. Aprimorar a interface gráfica e criar instalador.
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


## MVP 0.3 — Painel dos pais

A interface Tkinter permite cadastrar filhos, registrar seus rostos, configurar limite diário, dar **+15 minutos apenas no dia atual**, visualizar saldos e iniciar/parar a simulação do reconhecimento. Ela exige um PIN local para acesso às opções. O banco de dados mantém todas as informações da versão anterior.

### Executar no Windows

Instale as dependências seguindo as instruções acima. Na **conta Windows Filhos**, abra `abrir-facekids.bat` com dois cliques ou use:

```powershell
.\.venv\Scripts\python.exe -m facekids.gui
```

No primeiro acesso crie seu PIN de 4–12 dígitos e guarde-o: esta versão ainda não possui recuperação de PIN na interface. Clique em **Baixar modelos**, cadastre três crianças, use **Cadastrar rosto** individualmente e depois **Iniciar simulação**. A opção gráfica não chama `--lock`, portanto nunca executa bloqueio real; esse modo ainda só existe na CLI para testes supervisionados.

**Atenção de segurança:** este painel deve ser executado na mesma conta onde o monitor opera (normalmente `Filhos`). O SQLite fica em `%LOCALAPPDATA%\FaceKids` desse usuário, não no seu perfil administrador. O PIN dificulta uso casual da interface, mas **não protege o banco contra alterações por alguém usando a conta Filhos**. Para impor restrições de verdade será necessário instalar um serviço com permissões adequadas. Também falta testar a webcam no Windows real.

O workflow em `.github/workflows/tests.yml` executará os testes lógicos no Linux e Windows, sem câmera.


## MVP 0.4 — Separação de permissões (fundação)

O módulo **facekids/broker.py** foi adicionado com regras de acesso para os SIDs da conta administradora e da conta Filhos. Somente o papel de pai pode alterar limites, conceder bônus ou autorizar cadastro facial. O papel da criança pode enviar embeddings de rosto, mas o tempo é computado pelo relógio do Broker (não por segundos declarados pela criança). Testes adicionais foram adicionados em **tests/test_broker.py**.

**Importante:** este módulo ainda não tem transporte seguro nem serviço Windows instalado. Ele só ficará isolado das contas quando implementarmos o IPC autenticado e o banco protegido em ProgramData. Não utilize a versão 0.4 para impor bloqueio ou para substituir um controle parental consolidado. Veja [Arquitetura do Serviço Windows](docs/SERVICO_WINDOWS.md).
