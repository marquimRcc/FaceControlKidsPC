"""Persistência local. MVP: permissões da base ainda não são antiviolação."""
from __future__ import annotations

import os
import math
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
        self.db.execute("PRAGMA secure_delete = ON")
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
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS daily_bonus (
          person_id INTEGER NOT NULL, day TEXT NOT NULL,
          seconds INTEGER NOT NULL DEFAULT 0 CHECK(seconds >= 0),
          PRIMARY KEY(person_id, day),
          FOREIGN KEY(person_id) REFERENCES people(id));
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def add_person(self, name: str, limit_minutes: int) -> int:
        if not name.strip() or len(name.strip()) > 80 or not 1 <= limit_minutes <= 1440:
            raise ValueError("Nome e limite de minutos devem ser positivos.")
        with self.db:
            cur = self.db.execute(
                "INSERT INTO people(name, daily_limit_seconds) VALUES (?,?)",
                (name.strip(), int(limit_minutes * 60)))
        return int(cur.lastrowid)

    def set_daily_limit(self, person_id: int, minutes: int):
        if not 1 <= minutes <= 1440:
            raise ValueError("Limite permitido: 1 a 1440 minutos.")
        with self.db:
            cur = self.db.execute("UPDATE people SET daily_limit_seconds=? WHERE id=?",
                                  (minutes * 60, person_id))
            if cur.rowcount != 1: raise KeyError(person_id)

    def update_person_name(self, person_id: int, new_name: str):
        cleaned = new_name.strip()
        if not cleaned or len(cleaned) > 80:
            raise ValueError("Nome de pessoa inválido.")
        with self.db:
            cur = self.db.execute("UPDATE people SET name=? WHERE id=?", (cleaned, person_id))
            if cur.rowcount != 1: raise KeyError(person_id)

    def add_bonus(self, person_id: int, minutes: int, day: Optional[str] = None):
        if type(minutes) is not int or not 1 <= minutes <= 480:
            raise ValueError("Bônus permitido: 1 a 480 minutos.")
        day = date.today().isoformat() if day is None else day
        if (not isinstance(day, str) or len(day) != 10
                or date.fromisoformat(day).isoformat() != day):
            raise ValueError("Dia inválido; informe YYYY-MM-DD.")
        if self.db.execute("SELECT 1 FROM people WHERE id=?", (person_id,)).fetchone() is None:
            raise KeyError(person_id)
        with self.db:
            changed = self.db.execute("""
                INSERT INTO daily_bonus(person_id, day, seconds) VALUES (?, ?, ?)
                ON CONFLICT(person_id, day) DO UPDATE SET seconds=seconds+excluded.seconds
                WHERE daily_bonus.seconds <= 28800 - excluded.seconds
            """, (person_id, day, minutes * 60)).rowcount
            if changed != 1:
                raise ValueError("O bônus acumulado não pode ultrapassar 480 minutos por dia.")

    def remove_embeddings(self, person_id: int) -> int:
        """Remove locally stored SFace templates for one child only.

        PRAGMA secure_delete reduces residual bytes in SQLite pages; it is
        not a guarantee of secure erasure from SSDs, journals or backups.
        """
        if type(person_id) is not int or person_id <= 0:
            raise ValueError("Identificador de criança inválido.")
        with self.db:
            exists = self.db.execute(
                "SELECT 1 FROM people WHERE id=?", (person_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(person_id)
            removed = self.db.execute(
                "DELETE FROM embeddings WHERE person_id=?", (person_id,)
            ).rowcount
        return int(removed)

    def enrollment_count(self, person_id: int) -> int:
        row=self.db.execute("SELECT COUNT(*) FROM embeddings WHERE person_id=?", (person_id,)).fetchone()
        return int(row[0])

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

    def _require_quota_writer(self, *, service_receipt: bool) -> None:
        """Defense in depth for the VM cutover, checked inside BEGIN IMMEDIATE.

        This is NOT a credential boundary: only NTFS preventing a child from
        editing SQLite/WAL/SHM can provide that security. This gate prevents
        accidentally running the two application writers after cutover.
        """
        row = self.db.execute(
            "SELECT value FROM settings WHERE key='quota_writer_owner'"
        ).fetchone()
        value = row[0] if row is not None else None
        if value is not None and value != "vm-service-only":
            raise PermissionError("Unknown quota writer owner; fail closed")
        if value == "vm-service-only" and not service_receipt:
            raise PermissionError("Legacy debit forbidden: SCM owns VM ledger")

    def charge(self, person_id: int, seconds: float, day: Optional[str] = None) -> float:
        # Never persist NaN/Inf, strings or negative clock differences in the ledger.
        # This guard does not authenticate the caller or make local SQLite tamperproof.
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Tempo debitado deve ser um número finito não negativo")
        day = date.today().isoformat() if day is None else day
        if not isinstance(day, str):
            raise ValueError("Dia inválido")
        try:
            if len(day) != 10 or date.fromisoformat(day).isoformat() != day:
                raise ValueError("Dia inválido")
        except (TypeError, ValueError):
            raise ValueError("Dia inválido") from None
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self._require_quota_writer(service_receipt=False)
            self.db.execute("""
                INSERT INTO daily_usage(person_id,day,seconds) VALUES (?,?,?)
                ON CONFLICT(person_id,day) DO UPDATE SET seconds = seconds + excluded.seconds
            """, (person_id,day,float(seconds)))
        return self.used(person_id,day)

    def charge_up_to_available(self, person_id: int, seconds: float,
                               day: Optional[str] = None) -> float:
        """Atomically debit no more than available seconds for a trusted caller.

        BEGIN IMMEDIATE serializes read/modify/write across SQLite connections;
        it is NOT a Windows privilege or authorization boundary. The Filhos
        account can still tamper with the unprotected legacy database.
        Returns the actual seconds debited.
        """
        if type(person_id) is not int or person_id <= 0:
            raise ValueError("Identificador invalido")
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Debito deve ser finito e nao negativo")
        day = date.today().isoformat() if day is None else day
        if not isinstance(day, str):
            raise ValueError("Dia invalido")
        try:
            if len(day) != 10 or date.fromisoformat(day).isoformat() != day:
                raise ValueError("Dia invalido")
        except (TypeError, ValueError):
            raise ValueError("Dia invalido") from None

        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self._require_quota_writer(service_receipt=False)
            row = self.db.execute(
                "SELECT daily_limit_seconds FROM people WHERE id=?", (person_id,)
            ).fetchone()
            if row is None:
                raise KeyError(person_id)
            bonus_row = self.db.execute(
                "SELECT seconds FROM daily_bonus WHERE person_id=? AND day=?",
                (person_id, day),
            ).fetchone()
            usage_row = self.db.execute(
                "SELECT seconds FROM daily_usage WHERE person_id=? AND day=?",
                (person_id, day),
            ).fetchone()
            allowed = max(0.0, float(row[0]) +
                          (float(bonus_row[0]) if bonus_row else 0.0) -
                          (float(usage_row[0]) if usage_row else 0.0))
            debit = min(float(seconds), allowed)
            if debit > 0:
                self.db.execute("""
                    INSERT INTO daily_usage(person_id,day,seconds) VALUES (?,?,?)
                    ON CONFLICT(person_id,day)
                    DO UPDATE SET seconds = seconds + excluded.seconds
                """, (person_id, day, debit))
            return debit

    def charge_capped_once(self, event_id: str, person_id: int, seconds: float,
                           day: Optional[str] = None) -> float:
        """Prototype durable replay protection for service-issued tick IDs.

        event_id MUST be generated by the future trusted service and never
        accepted from the Filhos account. Returns newly debited seconds, or
        zero for an exact replay. This is not yet called in production.
        """
        if (not isinstance(event_id, str) or len(event_id) != 32 or
                any(ch not in "0123456789abcdef" for ch in event_id)):
            raise ValueError("Invalid service-generated tick identifier")
        if type(person_id) is not int or person_id <= 0:
            raise ValueError("Invalid child ID")
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Invalid quota debit")
        day = date.today().isoformat() if day is None else day
        if not isinstance(day, str):
            raise ValueError("Invalid day")
        try:
            if len(day) != 10 or date.fromisoformat(day).isoformat() != day:
                raise ValueError("Invalid day")
        except (TypeError, ValueError):
            raise ValueError("Invalid day") from None

        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self._require_quota_writer(service_receipt=True)
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS quota_tick_receipts (
                    event_id TEXT PRIMARY KEY,
                    person_id INTEGER NOT NULL,
                    day TEXT NOT NULL,
                    requested_seconds REAL NOT NULL,
                    charged_seconds REAL NOT NULL
                )
            """)
            receipt = self.db.execute(
                "SELECT person_id, day, requested_seconds FROM quota_tick_receipts WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if receipt is not None:
                if (receipt[0] != person_id or receipt[1] != day or
                        float(receipt[2]) != float(seconds)):
                    raise ValueError("Service tick identifier reused with different payload")
                return 0.0

            person = self.db.execute(
                "SELECT daily_limit_seconds FROM people WHERE id=?", (person_id,)
            ).fetchone()
            if person is None:
                raise KeyError(person_id)
            bonus = self.db.execute(
                "SELECT seconds FROM daily_bonus WHERE person_id=? AND day=?",
                (person_id, day),
            ).fetchone()
            used = self.db.execute(
                "SELECT seconds FROM daily_usage WHERE person_id=? AND day=?",
                (person_id, day),
            ).fetchone()
            remaining = max(0.0, float(person[0]) +
                            (float(bonus[0]) if bonus else 0.0) -
                            (float(used[0]) if used else 0.0))
            charged = min(float(seconds), remaining)
            if charged > 0:
                self.db.execute("""
                    INSERT INTO daily_usage(person_id,day,seconds) VALUES (?,?,?)
                    ON CONFLICT(person_id,day)
                    DO UPDATE SET seconds=seconds+excluded.seconds
                """, (person_id, day, charged))
            self.db.execute(
                "INSERT INTO quota_tick_receipts(event_id,person_id,day,requested_seconds,charged_seconds)"
                " VALUES (?,?,?,?,?)",
                (event_id, person_id, day, float(seconds), charged),
            )
            return charged

    def bonus(self, person_id: int, day: Optional[str] = None) -> int:
        row=self.db.execute("SELECT seconds FROM daily_bonus WHERE person_id=? AND day=?",
                            (person_id, day or date.today().isoformat())).fetchone()
        return int(row[0]) if row else 0

    def remaining(self, person_id: int, day: Optional[str] = None) -> float:
        row = self.db.execute("SELECT daily_limit_seconds FROM people WHERE id=?",(person_id,)).fetchone()
        if row is None: raise KeyError(person_id)
        return max(0.0,float(row[0])+self.bonus(person_id,day)-self.used(person_id,day))

    def get_setting(self, key: str) -> str | None:
        row=self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str):
        with self.db:
            self.db.execute("""
              INSERT INTO settings(key,value) VALUES (?,?)
              ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,(key,value))

    def get_history(self, person_id: int, num_days: int = 7) -> list[tuple[str, float]]:
        """Retorna historico de uso dos ultimos N dias ordenados do mais antigo ao mais recente."""
        from datetime import timedelta
        today = date.today()
        days = [(today - timedelta(days=i)).isoformat() for i in reversed(range(num_days))]
        return [(d, self.used(person_id, d)) for d in days]

    def get_curfew_config(self) -> tuple[bool, str, str]:
        """Retorna (habilitado, hora_inicio, hora_fim). Padrao: (False, '08:00', '20:00')."""
        enabled = self.get_setting("curfew_enabled") == "true"
        start = self.get_setting("curfew_start") or "08:00"
        end = self.get_setting("curfew_end") or "20:00"
        return enabled, start, end

    def set_curfew_config(self, enabled: bool, start: str, end: str):
        """Salva a configuracao de horario permitido."""
        self.set_setting("curfew_enabled", "true" if enabled else "false")
        self.set_setting("curfew_start", start.strip())
        self.set_setting("curfew_end", end.strip())

    def is_curfew_active(self, current_time_str: Optional[str] = None) -> tuple[bool, str]:
        """Verifica se o momento atual esta fora do horario permitido.

        Retorna (bloqueado, mensagem). Se bloqueado == True, o acesso deve ser negado.
        """
        enabled, start_str, end_str = self.get_curfew_config()
        if not enabled:
            return False, "Horário permitido desativado."

        from datetime import datetime
        now_time = datetime.now().time() if current_time_str is None else datetime.strptime(current_time_str, "%H:%M").time()
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()

        if start_time <= end_time:
            within = start_time <= now_time <= end_time
        else:
            within = now_time >= start_time or now_time <= end_time

        if not within:
            return True, f"Fora do horário permitido ({start_str} às {end_str})."
        return False, f"Dentro do horário permitido ({start_str} às {end_str})."

    def get_parent_pin(self) -> Optional[str]:
        """Retorna o hash do PIN parental cadastrado ou None se nao houver PIN."""
        return self.get_setting("parent_pin_hash")

    def set_parent_pin(self, pin: Optional[str]):
        """Define ou remove o PIN do painel dos pais."""
        if pin is None or not pin.strip():
            with self.db:
                self.db.execute("DELETE FROM settings WHERE key='parent_pin_hash'")
        else:
            from .admin_auth import hash_pin
            self.set_setting("parent_pin_hash", hash_pin(pin.strip()))

    def verify_parent_pin(self, pin: str) -> bool:
        """Verifica se o PIN fornecido confere com o configurado."""
        stored = self.get_parent_pin()
        if stored is None:
            return True
        from .admin_auth import verify_pin
        return verify_pin(pin.strip(), stored)
