"""Persistência local. MVP: permissões da base ainda não são antiviolação."""
from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np


def default_data_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else os.environ.get("XDG_DATA_HOME")
    if not base:
        base = str(Path.home() / ("AppData/Local" if os.name == "nt" else ".local/share"))
    return Path(base) / "FaceKids" / "facekids.sqlite3"


class Storage:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or default_data_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=10)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            daily_limit_seconds INTEGER NOT NULL CHECK(daily_limit_seconds > 0));
          CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL,
            vector BLOB NOT NULL,
            FOREIGN KEY(person_id) REFERENCES people(id));
          CREATE TABLE IF NOT EXISTS daily_usage (
            person_id INTEGER NOT NULL, day TEXT NOT NULL,
            seconds REAL NOT NULL DEFAULT 0 CHECK(seconds >= 0),
            PRIMARY KEY(person_id, day),
            FOREIGN KEY(person_id) REFERENCES people(id));
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def add_person(self, name: str, limit_minutes: int) -> int:
        if not name.strip() or limit_minutes <= 0:
            raise ValueError("Nome e limite de minutos devem ser positivos.")
        with self.db:
            cur = self.db.execute(
                "INSERT INTO people(name, daily_limit_seconds) VALUES (?,?)",
                (name.strip(), int(limit_minutes * 60)))
        return int(cur.lastrowid)

    def get_person(self, name: str):
        return self.db.execute("SELECT id,name,daily_limit_seconds FROM people WHERE name=?", (name,)).fetchone()

    def people(self):
        return self.db.execute("SELECT id,name,daily_limit_seconds FROM people ORDER BY id").fetchall()

    def add_embedding(self, person_id: int, vector: np.ndarray):
        v = np.asarray(vector, dtype=np.float32).reshape(-1)
        if v.size < 32 or not np.all(np.isfinite(v)):
            raise ValueError("Embedding facial inválido")
        with self.db:
            self.db.execute("INSERT INTO embeddings(person_id,vector) VALUES (?,?)", (person_id, v.tobytes()))

    def embeddings(self):
        rows = self.db.execute("SELECT person_id,vector FROM embeddings").fetchall()
        return [(int(pid), np.frombuffer(blob, dtype=np.float32).copy()) for pid,blob in rows]

    def used(self, person_id: int, day: Optional[str] = None) -> float:
        day = day or date.today().isoformat()
        row = self.db.execute("SELECT seconds FROM daily_usage WHERE person_id=? AND day=?", (person_id,day)).fetchone()
        return float(row[0]) if row else 0.0

    def charge(self, person_id: int, seconds: float, day: Optional[str] = None) -> float:
        if seconds < 0:
            raise ValueError("Não é permitido descontar tempo negativo")
        day = day or date.today().isoformat()
        with self.db:
            self.db.execute("""
                INSERT INTO daily_usage(person_id,day,seconds) VALUES (?,?,?)
                ON CONFLICT(person_id,day) DO UPDATE SET seconds = seconds + excluded.seconds
            """, (person_id,day,float(seconds)))
        return self.used(person_id,day)

    def remaining(self, person_id: int, day: Optional[str] = None) -> float:
        row = self.db.execute("SELECT daily_limit_seconds FROM people WHERE id=?",(person_id,)).fetchone()
        if row is None: raise KeyError(person_id)
        return max(0.0,float(row[0])-self.used(person_id,day))
