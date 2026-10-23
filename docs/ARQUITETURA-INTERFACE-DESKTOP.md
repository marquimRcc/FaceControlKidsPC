# Arquitetura da interface desktop

## Objetivo

Oferecer um painel administrativo e uma tela infantil consistentes no Regata
OS e no Windows, com uma base que também possa originar uma PWA para celular.
A quantidade de crianças cadastradas é variável e pode ser apenas uma.

## Decisão

O monorepo usa React e TypeScript para as telas compartilhadas e Electron para
o aplicativo desktop. O serviço Python continua sendo a autoridade sobre
cadastros, biometria, quotas, horários e bloqueio da sessão.

```text
apps/desktop       Electron, preload e composição das telas
packages/admin     painel e fluxo de cadastro
packages/ui        componentes visuais compartilhados
packages/contracts contratos tipados e validação das mensagens
```

O mesmo executável aceita os papéis `admin` e `child`. No modo administrativo
ele mostra perfis, tempo disponível e o fluxo de cadastro. No modo infantil,
mostra boas-vindas, identidade reconhecida, saldo e próximo aviso.

## Limite de confiança

O renderer não recebe acesso ao Node.js, ao banco SQLite ou a comandos do
sistema. O Electron usa `contextIsolation`, `sandbox`, `nodeIntegration: false`,
política de conteúdo e um preload com API mínima. A integração seguinte deverá
ligar essa API a um cliente local autenticado:

- Linux: socket Unix do serviço privilegiado, com credenciais do processo e
  autorização por operação;
- Windows: named pipe com ACL restrita;
- PWA futura: API opt-in, autenticada e pareada pelo responsável.

O frontend nunca decide se deve desbloquear uma sessão nem altera quotas por
conta própria. Ele envia pedidos tipados e exibe o estado validado pelo serviço.
Dados faciais brutos não atravessam a interface: a câmera e a produção dos
vetores permanecem no componente local responsável pelo cadastro.

## Estado desta etapa

Esta entrega é um protótipo navegável com dados de demonstração. Ela valida a
estrutura, o layout responsivo, o painel, o cadastro em três etapas e a tela de
boas-vindas. O botão de captura simula amostras e o botão final ainda não grava
no serviço. A conexão com o backend será adicionada depois da definição dos
contratos de autorização e persistência.

## Próxima integração

1. Definir operações e erros do serviço no pacote `contracts`.
2. Implementar adaptadores IPC separados para Linux e Windows.
3. Substituir o snapshot de demonstração por leitura do estado real.
4. Ligar cadastro, ajustes de quota, bônus e horários ao serviço.
5. Testar permissões, reconexão, indisponibilidade do serviço e validação no
   hardware antes de tornar a interface operacional.

## Integração operacional no Linux

O serviço publica `/run/facekids/admin.sock` com modo `0660`, pertencente a
`root:wheel` por padrão. O diretório de runtime usa `0750`. Cada conexão é
validada por `SO_PEERCRED`; somente UID 0 ou uma conta realmente pertencente ao
grupo configurado pode prosseguir. A conta compartilhada `filhos` é removida de
grupos suplementares pelo instalador e não consegue atravessar esse limite.

O protocolo usa uma mensagem JSON por conexão, limitada a 4096 bytes. O painel
consulta snapshots reais e pode criar um perfil e iniciar seu cadastro em uma
única operação. Durante o cadastro, o mesmo processo root que já possui a
câmera coleta 12 vetores, publica apenas a contagem de progresso e substitui os
templates atomicamente. Quadros de câmera nunca atravessam o socket. Cancelar
um cadastro novo remove o perfil ainda vazio para não deixar o runtime travado
por um cadastro incompleto.

O Electron conecta ao socket apenas no processo principal. O preload oferece
quatro métodos estreitos ao renderer: contexto, estado, novo cadastro e
cancelamento. As respostas são novamente validadas com Zod no renderer.

O aplicativo do menu KDE é criado por
`scripts/Criar-Atalho-Painel-RegataOS.sh`. Ele abre o build local usando o
Electron fixado no workspace. A atualização do serviço instalado, preservando
o banco, é feita por `scripts/Atualizar-FaceKids-RegataOS.sh`.
