"""Interface de linha de comando para validar o MVP antes de automatizar o bloqueio."""
import argparse
import os
from pathlib import Path
from urllib.request import urlretrieve

from .storage import Storage, default_data_path

MODEL_FILES={
  "face_detection_yunet_2023mar.onnx":"https://raw.githubusercontent.com/crymetr/crysence/main/crysence/data/face_detection_yunet_2023mar.onnx",
  "face_recognition_sface_2021dec.onnx":"https://raw.githubusercontent.com/crymetr/crysence/main/crysence/data/face_recognition_sface_2021dec.onnx",
}


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
        args.models.mkdir(parents=True,exist_ok=True)
        for name,url in MODEL_FILES.items():
            target=args.models/name
            if not target.exists():
                print(f"Baixando {name} (~{37 if 'sface' in name else .3} MB) ...")
                urlretrieve(url,target)
            print(f"OK: {target}")
        return
    from .monitor import enroll,monitor
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
