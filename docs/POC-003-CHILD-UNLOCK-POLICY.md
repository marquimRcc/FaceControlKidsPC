# P0-3 — Política de autorização por criança (offline)

**Status:** código puro implementado/testado, sem IPC, sem serviço Windows e
sem conexão com a DLL do Credential Provider.

A investigação do WinFace revelou a vantagem de um veredito biométrico recente
e um token de autorização consumido uma única vez. Porém, no FaceControlKidsPC,
o desbloqueio só poderá ocorrer quando **a criança identificada** tiver saldo
positivo, mesmo que todas compartilhem o mesmo usuário Windows Filhos.

## O que existe agora

- facekids/unlock_policy.py: avaliação fail-closed de face única, identidade,
  3 confirmações, vivacidade, timestamp recente e saldo individual positivo.
- OneUseTicketRegistry: nonce aleatório que expira rapidamente, vinculado a
  uma sessão Windows e consumido uma única vez; saldo reconsultado no consumo.
- tests/test_unlock_policy.py: testes para três crianças, cotas distintas,
  fotos/reprovação de vivacidade, câmeras com erro, observações antigas,
  mudança de sessão, expiração, repetição e saldo revogado.

## O que NÃO existe

Não há serviços privilegiados, canal protegido com LogonUI, câmera atestada,
credential vault, tickets emitidos ao Windows ou desbloqueio de contas.
O token Python é uma referência de ciclo de vida, não uma credencial do SO.
Um processo da conta Filhos não deve poder chamar issue() e emitir seu
próprio ticket; o serviço confiável terá que decidir isso e autenticar o cliente.

A futura integração Windows precisará verificar a origem dos frames,
controlar o armazenamento do saldo fora do perfil Filhos, conceder acesso ao
Credential Provider em seu contexto apropriado e manter senha de recuperação.

## Próxima prova

1. Concluir testes reais de câmera pós-Win+L em OpenCV e Media Foundation.
2. Executar host do Credential Provider sem instalar no LogonUI.
3. Provar um tile não autenticante, somente em VM ou computador descartável.
4. Desenhar canal confiável entre decisão e Credential Provider.
5. Só depois utilizar credenciais reais da conta Filhos e efetuar unlock.
