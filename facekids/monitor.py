"""Captura periódica, relógio de sessão e resposta à quota (protótipo)."""
from __future__ import annotations
import os
import time
from pathlib import Path

from .locker import lock_current_session
from .policy import Policy,Action
from .recognition import Recognizer
from .storage import Storage


def open_camera(index=0):
    import cv2
    cap=cv2.VideoCapture(index,cv2.CAP_DSHOW if os.name=="nt" else cv2.CAP_ANY)
    if not cap.isOpened():
        raise RuntimeError("Webcam não disponível. Verifique permissões e se outro app a utiliza.")
    return cap


def enroll(store: Storage, name: str, model_dir: Path, camera=0, samples=20):
    import cv2
    if not (person:=store.get_person(name)):
        raise KeyError(f"Criança não cadastrada: {name}")
    recognizer=Recognizer(model_dir)
    cap=open_camera(camera)
    saved=0
    print("Apenas uma pessoa diante da webcam. Pressione Q para cancelar.")
    try:
        while saved < samples:
            ok,frame=cap.read()
            if not ok:
                raise RuntimeError("Falha na leitura da webcam")
            faces=recognizer.faces(frame)
            if len(faces)==1:
                store.add_embedding(person[0],recognizer.features(frame,faces[0]))
                saved+=1
                print(f"Amostras capturadas: {saved}/{samples}",end="\r",flush=True)
            label=f"Cadastro {name}: {saved}/{samples}"
            cv2.putText(frame,label,(12,28),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2)
            cv2.imshow("FaceKids: cadastro (Q para cancelar)",frame)
            if (cv2.waitKey(1)&0xFF)==ord("q"):break
            time.sleep(0.35)
    finally:
        cap.release()
        cv2.destroyAllWindows()
    print(f"\nCadastro encerrado: {saved} amostras (os embeddings numéricos foram salvos).")


def monitor(store: Storage, model_dir: Path, camera=0, interval=5, enable_lock=False):
    if interval<=0 or interval>15:
        raise ValueError("Intervalo válido: até 15 s")
    recognizer=Recognizer(model_dir)
    samples=store.embeddings()
    if not samples:
        raise RuntimeError("Nenhum rosto cadastrado. Use primeiro o comando enroll.")
    policy=Policy(confirm_frames=2,uncertain_grace_sec=30)
    people={pid:(name,lim) for pid,name,lim in store.people()}
    cap=open_camera(camera)
    last_lock_at=float("-inf")
    print(f"Monitorando... bloqueio {'ATIVADO' if enable_lock else 'SIMULADO'} (Ctrl+C para sair).")
    print("A janela de terminal deve permanecer aberta neste protótipo.")
    try:
        while True:
            now=time.monotonic()
            ok,frame=cap.read()
            recognized=None
            if ok:
                faces=recognizer.faces(frame)
                if len(faces)==1:
                    recognized,_=recognizer.identify(recognizer.features(frame,faces[0]),samples)
            remain={pid:store.remaining(pid) for pid in people}
            decision=policy.step(now,recognized,remain)
            if decision.person_id is not None and decision.seconds_to_charge>0:
                store.charge(decision.person_id,decision.seconds_to_charge)
            who=people[decision.person_id][0] if decision.person_id in people else "desconhecido/ausente"
            balance=int(store.remaining(decision.person_id)) if decision.person_id in people else "—"
            print(f"{time.strftime('%H:%M:%S')} | {decision.action.value:15} | {who:20} | saldo {balance}s")
            if decision.action in (Action.LOCK_QUOTA,Action.LOCK_UNCERTAIN):
                if now-last_lock_at>=15:
                    if enable_lock:
                        print("Solicitando bloqueio do sistema operacional...")
                        lock_current_session()
                    else:
                        print("[SIMULAÇÃO] Neste ponto a sessão seria bloqueada.")
                    last_lock_at=now
            time.sleep(max(0.0,interval-(time.monotonic()-now)))
    except KeyboardInterrupt:
        print("\nMonitoramento encerrado.")
    finally:
        cap.release()
