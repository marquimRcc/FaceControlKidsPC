# Implementação FaceKids no Regata OS

## Estado

A branch implementa a base Linux testável sem alterar PAM. O serviço protegido
abre a webcam, identifica uma das crianças configuradas, contabiliza somente durante uma
sessão KDE ativa e desbloqueada e solicita o bloqueio nativo pelo logind quando
a quota termina, o horário permitido acaba ou a identidade deixa de ser
confirmada por 30 segundos.

Ao abrir a câmera, o processo descarta 15 quadros para permitir a estabilização
da autoexposição. Durante o bloqueio, três confirmações consecutivas do mesmo
rosto, com quota e horário revalidados, solicitam o desbloqueio da sessão pelo
logind. Esse caminho pode ser desativado com `--no-auto-unlock` para diagnóstico.
O mesmo ticket permanece disponível por até dez segundos para o helper PAM
caso o KScreenLocker não aceite o pedido direto; o primeiro consumo o invalida.

O banco e os vetores ficam em `/var/lib/facekids`, pertencem a root e não são
graváveis pela conta compartilhada. O processo que reconhece também decide e
contabiliza; portanto a criança não envia `child_id` por um IPC modificável.
A conta compartilhada não conserva grupos suplementares permanentes (incluindo
`wheel`, `docker`, `libvirt` ou `video`); somente o serviço root, limitado pela
unidade systemd, e os comandos administrativos acessam a webcam.
O runtime não recebe famílias de socket de rede nem capacidades Linux extras;
a unidade aceita somente `AF_UNIX` e nega tráfego IP.
Existe uma integração opt-in com `pam_exec` para consumir um ticket facial
fresco e de uso único no desbloqueio KDE. Ela não é habilitada pelo instalador
e não produz login inicial sem interação no SDDM.

## Componentes

- `facekids/linux_runtime.py`: captura V4L2, reconhecimento e aplicação de quota.
- `facekids/session.py`: leitura conservadora de `Active`, `State` e
  `LockedHint` do systemd-logind.
- `facekids/linux_admin.py`: cadastro de um ou mais perfis, limites, bônus, horário
  e apagamento de biometria.
- `packaging/facekids-linux.service`: isolamento do serviço e acesso restrito a
  `/dev/video0` e `/var/lib/facekids`.
- `facekids/linux_auth.py`: três confirmações faciais e ticket de uso único,
  ligado à sessão e com validade de dez segundos.
- `facekids/linux_pam_helper.py`: cliente mínimo aceito apenas pelo socket root.
- `scripts/Instalar-FaceKids-RegataOS.sh`: instalação explícita pelo responsável.
- `scripts/Desinstalar-FaceKids-RegataOS.sh`: remove programa e serviço,
  preservando os dados até apagamento deliberado.

## Instalação preparada

Na raiz do repositório, com a conta compartilhada Linux já criada como
`filhos`:

```bash
sudo bash scripts/Criar-Conta-Filhos-RegataOS.sh filhos
sudo bash scripts/Instalar-FaceKids-RegataOS.sh filhos 1
```

O segundo argumento é a quantidade de crianças (de 1 a 20). Use, por exemplo,
`filhos 4` para quatro perfis. Quando omitido, o instalador cria um perfil.

O instalador copia e prepara o serviço, mas não o habilita nem inicia sem
perfis. Com cada criança presente e consentimento do responsável:

```bash
facekids-linux-probe --camera 0 --seconds 5
sudo -E facekids-admin enroll 1
# repita com 2, 3... até o total configurado
sudo facekids-admin status
sudo systemctl enable --now facekids-linux
```

O runtime também recusa iniciar se qualquer perfil configurado tiver menos de
três amostras válidas, evitando operar silenciosamente com cadastro parcial.
Durante a execução, alterações nos vetores são recarregadas em até dois
segundos. Apagar um cadastro revoga tickets e evidência em memória e força o
bloqueio até que todos os perfis configurados voltem a estar completos.

Depois de comprovar o reconhecimento, o bloqueio, a conta administrativa e a
recuperação por senha, a autenticação facial no desbloqueio KDE pode ser
habilitada explicitamente:

```bash
sudo bash scripts/Ativar-PAM-FaceKids-RegataOS.sh
```

Para retirar a integração PAM usando os backups guardados:

```bash
sudo bash scripts/Desativar-PAM-FaceKids-RegataOS.sh
```

Exemplos administrativos:

```bash
sudo facekids-admin set-limit 1 120
sudo facekids-admin bonus 1 30
sudo facekids-admin curfew 08:00 20:00
sudo facekids-admin disable-curfew
sudo facekids-admin erase-face 1
```

## Recuperação

O serviço não modifica PAM nem remove senha. Em caso de problema, entre na conta
do responsável e execute:

```bash
sudo systemctl disable --now facekids-linux
```

Para remover o programa e preservar quotas/cadastros:

```bash
sudo bash scripts/Desinstalar-FaceKids-RegataOS.sh
```

## Limites ainda existentes

O desbloqueio sem clique agora é solicitado por `loginctl unlock-session`, mas
a aceitação efetiva desse pedido ainda precisa ser comprovada no KScreenLocker
do notebook. O helper PAM continua disponível como integração opcional durante
uma conversa de autenticação já iniciada. Login inicial no SDDM pode exigir uma
integração gráfica própria. A senha convencional permanece como fallback.

O primeiro teste local de 22/10/2026 recebeu quadros quase pretos. Depois de
adicionar o aquecimento V4L2, um novo probe recebeu 31 de 31 quadros utilizáveis,
com brilho médio 90,74 e 6,11 fps. Não havia rosto no quadro; detecção e
desbloqueio físico ainda precisam ser validados com o responsável presente.
