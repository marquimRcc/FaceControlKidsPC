# ADR-003 — Executável único para instalação e distribuição por Releases

## Status

O protótipo Windows x64 é gerado por `scripts/Construir-FaceKids-Setup.ps1` em `dist/FaceKids-Instalador-Windows-x64.exe`. A homologação exige testar a execução do EXE, o primeiro logon de uma conta nova e o reaproveitamento de uma conta existente em uma máquina de teste.

## Decisão principal

No Windows, o usuário deverá baixar **um único arquivo**:

`FaceKids-Instalador-Windows-x64.exe`

Ao abrir esse arquivo, o próprio executável deverá:

1. solicitar elevação administrativa pelo UAC;
2. abrir diretamente o assistente visual do FaceKids;
3. mostrar a conta fixa `Filhos`, com a senha `1` preenchida por padrão e editável;
4. pedir o PIN dos pais, nome da criança e limite diário;
5. capturar as 12 amostras faciais;
6. instalar os componentes permanentes em `C:\Program Files\FaceKids`;
7. registrar o Credential Provider, as tarefas e os serviços necessários;
8. verificar a instalação completa;
9. criar os atalhos do Painel dos Pais;
10. abrir o Painel dos Pais somente após a verificação terminar com sucesso.

Não haverá um segundo instalador para abrir, baixar ou executar. O EXE entregue ao usuário será simultaneamente o programa que abre o assistente e o responsável por aplicar a instalação.

## Esclarecimento técnico

### Conta Filhos e primeiro acesso

- Se a conta local `Filhos` já existir, instalação, atualização e reparo preservam o SID, a senha, os grupos, o perfil e as preferências do Windows. Quando o FaceKids ainda não conhece a credencial, o assistente pode pedir a senha atual para vinculá-la sem redefini-la.
- Se a conta for nova, o instalador cria o perfil e aplica as recusas de privacidade antes do primeiro login, somente nesse perfil. O teste em Windows limpo deve confirmar que a edição e a versão testadas abrem a sessão sem telas de configuração, ofertas ou consentimento. Políticas do dispositivo e telas introduzidas por atualizações precisam ser avaliadas nessa validação.
- O EXE de instalação pede elevação uma vez, na sessão de quem instala. A tarefa de logon de `Filhos` inicia diretamente o agente com permissões limitadas. Ela nunca chama o assistente ou pede senha de administrador. O teste deve incluir primeiro login, novo login, reinicialização e atualização sobre conta existente.
- A primeira entrega cobre Windows x64. RPM e AppImage ficam para uma etapa posterior.

“Um único EXE para baixar” não significa que apenas um arquivo continuará existindo depois da instalação. O próprio EXE contém o pacote necessário e grava no computador os componentes permanentes exigidos pelo Windows, incluindo:

- o aplicativo e seu runtime;
- os modelos faciais;
- a DLL do Credential Provider;
- os arquivos de suporte dos serviços;
- os atalhos. O desinstalador independente continua como requisito para o pacote público.

A DLL do Credential Provider precisa existir separadamente em disco para ser registrada e carregada pelo Windows. Os dados, fotos e configurações também permanecem em `C:\ProgramData\FaceKids`. Essa extração é uma etapa interna e invisível; para o usuário, existe somente um EXE baixado e aberto.

## Estratégia de empacotamento

O executável autoextraível abre o assistente com a mesma elevação usada para copiar o runtime privado. Os executáveis instalados usam a identidade da tarefa que os inicia. O processo deve obedecer aos seguintes requisitos:

- não depender de Python previamente instalado;
- não depender do repositório ou de arquivos `.bat` na máquina do usuário;
- usar uma área temporária apenas durante a preparação;
- copiar o runtime definitivo para `C:\Program Files\FaceKids`;
- fazer tarefas e atalhos apontarem somente para a instalação permanente;
- não apontar serviços para a pasta temporária criada pelo empacotador;
- manter reparo e desinstalação disponíveis após o EXE original ser apagado da pasta Downloads;
- interromper a conclusão se conta, DLL, tarefas, canal de autenticação ou atalhos não forem verificados.

O EXE único pode funcionar em modos internos, por exemplo `--install`, `--admin`, `--auth-service`, `--filhos-agent`, `--repair` e `--uninstall`. Esses modos são detalhes internos e não exigem ações adicionais do usuário durante a primeira instalação.

## GitHub Releases

Cada versão estável deverá ser publicada por uma tag, por exemplo `v2.0.0`. A página de Release deverá oferecer os artefatos adequados a cada sistema:

- `FaceKids-Instalador-Windows-x64.exe` — instalação completa no Windows;
- `facekids-<versao>-1.x86_64.rpm` — instalação completa no Regata OS e sistemas RPM compatíveis após homologação;
- `FaceKids-Admin-<versao>-x86_64.AppImage` — painel Linux portátil, sem substituir a instalação privilegiada do RPM;
- `SHA256SUMS.txt` — hashes de integridade.

O processo de release deverá ser automatizado pelo GitHub Actions em ambientes Windows e Linux separados. A publicação só deverá ocorrer depois dos testes automatizados e dos testes práticos de instalação limpa, login, bloqueio e desinstalação.

## Assinatura e segurança

Para distribuição pública, o EXE e a DLL deverão ser assinados com certificado de assinatura de código. O RPM deverá ser assinado com chave GPG. Chaves e certificados deverão ser usados pelo fluxo de release por meio de segredos protegidos, sem serem armazenados no repositório.

Sem assinatura, o mesmo formato continua tecnicamente possível, mas o Windows pode exibir avisos do SmartScreen e do Smart App Control.

## Critério de aceitação

A experiência esperada é:

1. baixar um único EXE na página de Releases;
2. abrir o EXE;
3. confirmar o UAC;
4. concluir o assistente do FaceKids;
5. encontrar o Painel dos Pais instalado e a conta Filhos pronta.

O pacote não será considerado pronto enquanto essa sequência não funcionar numa instalação limpa, sem Python, sem o repositório e sem ferramentas de desenvolvimento.
