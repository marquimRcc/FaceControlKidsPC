# Piloto real do rosto do responsável — Windows 10/11

Branch: \`feature/parent-face-pilot\`, criada da main já integrada.

Este piloto **abre a webcam real**, captura doze representações
numéricas YuNet/SFace do rosto adulto, armazena-as em
\`%LOCALAPPDATA%\FaceKids\piloto-responsavel\piloto.sqlite3\`
e mostra o reconhecimento ao vivo por até 60 segundos.

Não grava fotografia ou vídeo, não envia dados biométricos pela rede,
não registra Credential Provider e **NÃO desbloqueia nem bloqueia o Windows**.
A instalação de dependências e modelos públicos pode acessar a Internet.

ATENÇÃO: os vetores faciais são dados biométricos sensíveis e o banco
de teste sob LOCALAPPDATA ainda não usa o armazenamento protegido
LocalSystem. Cadastre apenas um adulto que consinta; não use rostos de
menores neste piloto. Você pode apagar o banco e o diretório localmente
para descartar o cadastro. O teste de fotografia/vídeo continua inseguro;
identificação facial demonstra similaridade, não autenticidade/liveness.

## Executar a partir de PowerShell normal, na pasta clonada

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\Testar-Meu-Rosto.ps1"

Para recadastrar o adulto:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\Testar-Meu-Rosto.ps1" -ReEnroll

O script não atualiza o Git automaticamente; ele exige a branch
específica (a sequência de atualização é fornecida na conversa).
Na primeira execução, instala pacotes no \`.venv\` e baixa modelos
ONNX apenas se não estiverem disponíveis. Se o download falhar, o
programa para sem cadastrar vetores incompletos.

Durante o cadastro olhe para a webcam, fique sozinho no quadro e
mova lentamente a cabeça. Durante a verificação, saia da frente
da câmera, retorne e verifique se o estado alterna de
\`SEM_ROSTO\` para \`IDENTIFICADO_DEMO\`. A janela pode ser fechada
com ESC ou Q. O teste conclui o cadastro mesmo se a visualização
for interrompida na etapa de validação.

O reconhecimento ao vivo não é prova de resistência a fotos, replay
ou deepfake; nunca usar essa saída para conceder autenticação Windows.
