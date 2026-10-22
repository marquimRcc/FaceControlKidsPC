# Implementação FaceKids no Regata OS

## Estado

A branch implementa a base Linux testável sem alterar PAM. O serviço protegido
abre a webcam, identifica uma das três crianças, contabiliza somente durante uma
sessão KDE ativa e desbloqueada e solicita o bloqueio nativo pelo logind quando
a quota termina, o horário permitido acaba ou a identidade deixa de ser
confirmada por 30 segundos.

O banco e os vetores ficam em `/var/lib/facekids`, pertencem a root e não são
graváveis pela conta compartilhada. O processo que reconhece também decide e
contabiliza; portanto a criança não envia `child_id` por um IPC modificável.
Existe uma integração opt-in com `pam_exec` para consumir um ticket facial
fresco e de uso único no desbloqueio KDE. Ela não é habilitada pelo instalador
e não produz login inicial sem interação no SDDM.

## Componentes

- `facekids/linux_runtime.py`: captura V4L2, reconhecimento e aplicação de quota.
- `facekids/session.py`: leitura conservadora de `Active`, `State` e
  `LockedHint` do systemd-logind.
- `facekids/linux_admin.py`: cadastro dos três perfis, limites, bônus, horário
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
sudo bash scripts/Instalar-FaceKids-RegataOS.sh filhos
```

O instalador habilita o serviço, mas não o inicia sem perfis. Com cada criança
presente e consentimento do responsável:

```bash
facekids-linux-probe --camera 0 --seconds 5
sudo -E facekids-admin enroll 1
sudo -E facekids-admin enroll 2
sudo -E facekids-admin enroll 3
sudo facekids-admin status
sudo systemctl start facekids-linux
```

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

O helper PAM pode aceitar um rosto com saldo durante uma conversa de
autenticação já iniciada. Ele ainda não aciona sozinho a interface gráfica; o
login inicial e o desbloqueio realmente sem clique exigem integração própria
com SDDM/KScreenLocker. Uma senha conhecida pela conta compartilhada continua
podendo abrir a sessão pelo fallback; o serviço voltará a exigir rosto e
bloquear quando a identidade não for confirmada.

O teste local de 22/10/2026 confirmou `/dev/video0`, mas recebeu quadros quase
pretos. O software recusa esses quadros; cadastro e calibração dependem de a
câmera fornecer imagem utilizável.
