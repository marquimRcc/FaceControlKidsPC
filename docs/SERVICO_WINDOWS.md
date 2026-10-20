# Arquitetura para o serviço Windows protegido — 0.4

A versão 0.4 adiciona apenas a autoridade de regras e testes de autorização.
Ela NÃO instala nem disponibiliza um serviço privilegiado no sistema.

## Divisão

- Conta administradora: cadastra crianças, ajusta limites e bônus e autoriza cadastramento facial.
- Conta Filhos: executará o agente da webcam; não deve escrever no banco de regras.
- Futuro serviço LocalSystem: guardará o SQLite em ProgramData com ACL restrita a SYSTEM e administradores.
- A webcam precisa permanecer na sessão interativa Filhos; serviços Windows executam em Session 0.

## Protocolo pretendido

- Pai: ping, status, add, limit, bonus, enroll, cancel_enroll.
- Criança: ping, observe (vetor SFace de 128 valores), pause.
- Nome, ID e segundos não podem ser enviados pela criança como fonte confiável de quota.

## Requisitos antes de ativar de verdade

1. Named pipe com ACL e obtenção autenticada do SID via token de impersonation do Windows.
2. Configuração de SIDs, armazenamento SQLite em ProgramData e permissões NTFS protegidas.
3. Verificação do estado de sessão WTS no SERVIDOR, sem confiar em sinalização da criança.
4. Agente de webcam na sessão Filhos, watchdog de reinício e bloqueio por falha de monitoramento.
5. Painel dos pais integrado ao serviço via IPC e instalador que exija elevação.
6. Testes reais no Windows 10/11 de login, troca de usuário, câmera desconectada e suspensão.
7. Proteção biométrica (foto/replay), privacidade e procedimentos de recuperação parental.

Não exponha o Broker como HTTP local sem autenticação ou named pipe sem validação de SID.
A conta Filhos ainda pode encerrar o monitor legado, e o PIN atual não é uma barreira do Windows.
