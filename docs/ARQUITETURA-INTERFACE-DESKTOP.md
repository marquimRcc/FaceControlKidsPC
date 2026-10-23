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
Frames e vídeo da câmera não atravessam a interface: a câmera e a produção dos
vetores permanecem no componente local responsável pelo cadastro. Somente os
retratos JPEG recortados e guardados para o perfil são entregues ao painel
administrativo pelo socket protegido.

## Estado desta etapa

O painel Linux lê o estado real e executa o cadastro pela câmera do serviço.
Cada cadastro produz 12 vetores para o reconhecimento e até três retratos
locais para a galeria. O responsável pode repetir a captura, manter até seis
retratos e escolher a imagem exibida no painel e na tela infantil.

## Integração operacional no Linux

O serviço publica `/run/facekids/admin.sock` com modo `0660`, pertencente a
`root:wheel` por padrão. O diretório de runtime usa `0750`. Cada conexão é
validada por `SO_PEERCRED`; somente UID 0 ou uma conta realmente pertencente ao
grupo configurado pode prosseguir. A conta compartilhada `filhos` é removida de
grupos suplementares pelo instalador e não consegue atravessar esse limite.

O protocolo usa uma mensagem JSON por conexão, limitada a 4096 bytes. O painel
consulta snapshots reais e pode criar um perfil e iniciar seu cadastro em uma
única operação. Durante o cadastro, o mesmo processo root que já possui a
câmera coleta 12 vetores, publica a contagem de progresso e salva até três retratos recortados
junto dos templates, na mesma transação. Quadros e vídeo da câmera nunca
atravessam o socket; a galeria atravessa somente o socket administrativo.
Cancelar
um cadastro novo remove o perfil ainda vazio para não deixar o runtime travado
por um cadastro incompleto.

O Electron conecta ao socket apenas no processo principal. O preload oferece
métodos estreitos para contexto, estado, cadastro e galeria de fotos. As
respostas são novamente validadas com Zod no renderer.

O aplicativo do menu KDE é criado por
`scripts/Criar-Atalho-Painel-RegataOS.sh`. Ele abre o build local usando o
Electron fixado no workspace. A atualização do serviço instalado, preservando
o banco, é feita por `scripts/Atualizar-FaceKids-RegataOS.sh`.
