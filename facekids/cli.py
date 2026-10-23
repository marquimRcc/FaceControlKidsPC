"""Interface de linha de comando para validar o MVP antes de automatizar o bloqueio."""
import argparse
import hashlib
import os
import tempfile
from pathlib import Path
from urllib.request import urlretrieve

from .storage import Storage, default_data_path

MODEL_FILES={
  "face_detection_yunet_2023mar.onnx":(
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
  ),
  "face_recognition_sface_2021dec.onnx":(
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
  ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_models(model_dir: Path) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    for name, (url, expected_hash) in MODEL_FILES.items():
        target = model_dir / name
        if target.exists() and _sha256(target) == expected_hash:
            print(f"OK: {target}")
            continue
        with tempfile.NamedTemporaryFile(dir=model_dir, delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            print(f"Baixando e verificando {name} ...")
            urlretrieve(url, temporary_path)
            actual_hash = _sha256(temporary_path)
            if actual_hash != expected_hash:
                raise RuntimeError(
                    f"SHA-256 inesperado para {name}: {actual_hash}"
                )
            temporary_path.replace(target)
            target.chmod(0o644)
        finally:
            temporary_path.unlink(missing_ok=True)
        print(f"OK: {target}")


def main():
    p=argparse.ArgumentParser(description="FaceKids — prova de conceito local")
    p.add_argument("--database",type=Path,default=default_data_path())
    p.add_argument("--models",type=Path,default=Path(__file__).resolve().parent.parent/"models")
    sub=p.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("add",help="Cadastrar pessoa (sem rosto ainda)")
    a.add_argument("name");a.add_argument("--minutes",type=int,default=120)
    e=sub.add_parser("enroll",help="Capturar amostras faciais")
    e.add_argument("name");e.add_argument("--camera",type=int,default=0);e.add_argument("--samples",type=int,default=20)
    m=sub.add_parser("monitor",help="Identificar e simular bloqueios")
    m.add_argument("--camera",type=int,default=0);m.add_argument("--interval",type=float,default=5)
    m.add_argument("--lock",action="store_true",help="Habilitar bloqueio REAL do Windows")
    m.add_argument("--monitored-user",default="Filhos",help="Conta Windows monitorada (padrão: Filhos)")
    sub.add_parser("status",help="Ver saldo diário")
    sub.add_parser("download-models",help="Baixar modelos do repositório do CrySence")
    args=p.parse_args()
    if args.cmd == "monitor" and args.lock and os.name != "nt":
        p.error("Bloqueio real disponível apenas no Windows 10/11 nesta versão")
    if args.cmd=="download-models":
        download_models(args.models)
        return
    from .monitor import enroll, monitor
    store=Storage(args.database)
    try:
        if args.cmd=="add":
            print("ID cadastrado:",store.add_person(args.name,args.minutes))
        elif args.cmd=="enroll":
            enroll(store,args.name,args.models,args.camera,args.samples)
        elif args.cmd=="monitor":
            monitor(store,args.models,args.camera,args.interval,args.lock,args.monitored_user)
        elif args.cmd=="status":
            for pid,name,limit in store.people():
                print(f"{name}: {int(store.remaining(pid))//60} min restantes de {limit//60} min/dia")
    finally:
        store.close()

if __name__=="__main__":
    main()
