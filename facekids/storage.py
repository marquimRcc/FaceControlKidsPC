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
    # Keep every entry point on the same explicitly opted-in VM database.
    # In particular, gate_webcam_preview calls this function directly while
    # the parent dashboard uses children_pilot.child_pilot_database().
    from .vm_lab_paths import vm_lab_root

    vm_root = vm_lab_root()
    if vm_root is not None:
        return vm_root / "data" / "criancas.sqlite3"
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
        CREATE TABLE IF NOT EXISTS quota_refund_receipts (
            event_id TEXT PRIMARY KEY,
            session_epoch TEXT NOT NULL,
            person_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            requested_seconds REAL NOT NULL,
            refunded_seconds REAL NOT NULL,
            reason TEXT NOT NULL CHECK(reason IN ('inactivity')),
            UNIQUE(session_epoch, person_id, day)
        );
        CREATE TABLE IF NOT EXISTS quota_refund_charge_links (
            charge_event_id TEXT PRIMARY KEY,
            refund_event_id TEXT NOT NULL REFERENCES quota_refund_receipts(event_id)
        );
        CREATE TABLE IF NOT EXISTS profile_photos (
          id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL,
          jpeg BLOB NOT NULL CHECK(length(jpeg) BETWEEN 100 AND 100000),
          selected INTEGER NOT NULL DEFAULT 0 CHECK(selected IN (0, 1)),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE);
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

    def remove_unenrolled_person(self, person_id: int) -> bool:
        """Remove somente perfil novo sem biometria, uso ou bônus."""
        if type(person_id) is not int or person_id <= 0:
            raise ValueError("Identificador de criança inválido.")
        with self.db:
            counts = self.db.execute("""
                SELECT
                  (SELECT COUNT(*) FROM embeddings WHERE person_id=?),
                  (SELECT COUNT(*) FROM daily_usage WHERE person_id=?),
                  (SELECT COUNT(*) FROM daily_bonus WHERE person_id=?)
            """, (person_id, person_id, person_id)).fetchone()
            if counts is None or any(counts):
                return False
            removed = self.db.execute(
                "DELETE FROM people WHERE id=?", (person_id,)
            ).rowcount
        return removed == 1

    def delete_person(self, person_id: int) -> None:
        """Remove um perfil e todos os dados locais associados em uma transação."""
        if type(person_id) is not int or person_id <= 0:
            raise ValueError("Identificador de criança inválido.")
        with self.db:
            if self.db.execute(
                "SELECT 1 FROM people WHERE id=?", (person_id,)
            ).fetchone() is None:
                raise KeyError(person_id)
            for table in ("profile_photos", "embeddings", "daily_usage", "daily_bonus"):
                self.db.execute(f"DELETE FROM {table} WHERE person_id=?", (person_id,))
            removed = self.db.execute(
                "DELETE FROM people WHERE id=?", (person_id,)
            ).rowcount
            if removed != 1:
                raise KeyError(person_id)

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

    def replace_embeddings_and_add_photos(
        self, person_id: int, vectors: list[np.ndarray], photos: list[bytes]
    ) -> None:
        """Substitui biometria e acrescenta fotos de perfil na mesma transação."""
        payload = []
        for vector in vectors:
            value = np.asarray(vector, dtype=np.float32).reshape(-1)
            if value.size != 128 or not np.all(np.isfinite(value)):
                raise ValueError("Embedding facial inválido")
            payload.append((person_id, value.tobytes()))
        if len(payload) != 12 or not 1 <= len(photos) <= 3:
            raise ValueError("Cadastro facial ou fotos incompletos")
        if any(not isinstance(photo, bytes) or not 100 <= len(photo) <= 100000
               for photo in photos):
            raise ValueError("Foto de perfil inválida")
        with self.db:
            if self.db.execute(
                "SELECT 1 FROM people WHERE id=?", (person_id,)
            ).fetchone() is None:
                raise KeyError(person_id)
            already_selected = self.db.execute(
                "SELECT 1 FROM profile_photos WHERE person_id=? AND selected=1",
                (person_id,),
            ).fetchone() is not None
            self.db.execute("DELETE FROM embeddings WHERE person_id=?", (person_id,))
            self.db.executemany(
                "INSERT INTO embeddings(person_id,vector) VALUES (?,?)", payload
            )
            for index, photo in enumerate(photos):
                self.db.execute(
                    "INSERT INTO profile_photos(person_id,jpeg,selected) VALUES (?,?,?)",
                    (person_id, photo, int(not already_selected and index == 0)),
                )
            self.db.execute("""
                DELETE FROM profile_photos
                WHERE person_id=? AND selected=0 AND id IN (
                  SELECT id FROM profile_photos WHERE person_id=? AND selected=0
                  ORDER BY created_at DESC,id DESC LIMIT -1 OFFSET 15)
            """, (person_id, person_id))

    def clear_profile_photos(self, person_id: int) -> int:
        """Remove todas as fotos de perfil registradas para a crianca."""
        with self.db:
            return self.db.execute("DELETE FROM profile_photos WHERE person_id=?", (person_id,)).rowcount

    def profile_photos(self, person_id: int) -> list[tuple[int, bytes, bool]]:
        rows = self.db.execute(
            "SELECT id,jpeg,selected FROM profile_photos WHERE person_id=? "
            "ORDER BY id ASC LIMIT 24", (person_id,)
        ).fetchall()
        return [(int(photo_id), bytes(jpeg), bool(selected))
                for photo_id, jpeg, selected in rows]

    def selected_profile_photo(self, person_id: int) -> bytes | None:
        row = self.db.execute(
            "SELECT jpeg FROM profile_photos WHERE person_id=? AND selected=1 "
            "ORDER BY id DESC LIMIT 1", (person_id,)
        ).fetchone()
        return bytes(row[0]) if row else None

    def select_profile_photo(self, person_id: int, photo_id: int) -> None:
        if type(person_id) is not int or type(photo_id) is not int:
            raise ValueError("Foto ou criança inválida")
        with self.db:
            exists = self.db.execute(
                "SELECT 1 FROM profile_photos WHERE id=? AND person_id=?",
                (photo_id, person_id),
            ).fetchone()
            if exists is None:
                raise KeyError(photo_id)
            self.db.execute(
                "UPDATE profile_photos SET selected=0 WHERE person_id=?", (person_id,)
            )
            self.db.execute(
                "UPDATE profile_photos SET selected=1 WHERE id=? AND person_id=?",
                (photo_id, person_id),
            )

    def add_profile_photo(self, person_id: int, jpeg_bytes: bytes, select: bool = True) -> int:
        """Adiciona uma foto de perfil e a define como selecionada/ativa se select=True."""
        with self.db:
            if select:
                self.db.execute(
                    "UPDATE profile_photos SET selected=0 WHERE person_id=?", (person_id,)
                )
            cur = self.db.execute(
                "INSERT INTO profile_photos(person_id,jpeg,selected) VALUES (?,?,?)",
                (person_id, jpeg_bytes, int(select)),
            )
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

    def refund_capped_once(
        self, event_id: str, session_epoch: str, person_id: int,
        seconds: float, charge_event_ids: tuple[str, ...], day: Optional[str] = None,
    ) -> float:
        """VM service-only idempotent refund of *previously charged* receipts.

        event_id, session_epoch, and eligible charge receipts MUST originate
        from the privileged service, never a Filhos IPC payload. A tick can
        be refunded at most once, regardless of a new event_id. One inactivity
        refund per verified WTS unlock epoch. No access to a trusted input-idle
        sensor is inferred here: this storage primitive is not deployed.
        """
        def valid_hex(value: object) -> bool:
            return (type(value) is str and len(value) == 32
                    and all(ch in "0123456789abcdef" for ch in value))

        if not valid_hex(event_id) or not valid_hex(session_epoch):
            raise ValueError("Service-owned refund event and epoch required")
        if type(person_id) is not int or person_id <= 0:
            raise ValueError("Invalid child ID")
        if (type(seconds) not in (int, float) or not math.isfinite(seconds)
                or seconds < 0 or seconds > 120):
            raise ValueError("Refund must be finite and no more than 120 seconds")
        if (type(charge_event_ids) is not tuple or not charge_event_ids
                or len(charge_event_ids) > 128 or
                any(not valid_hex(x) for x in charge_event_ids) or
                len(set(charge_event_ids)) != len(charge_event_ids)):
            raise ValueError("Distinct service charge receipts required")
        day = date.today().isoformat() if day is None else day
        if type(day) is not str:
            raise ValueError("Invalid refund day")
        try:
            if len(day) != 10 or date.fromisoformat(day).isoformat() != day:
                raise ValueError("Invalid refund day")
        except (ValueError, TypeError):
            raise ValueError("Invalid refund day") from None

        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self._require_quota_writer(service_receipt=True)
            existing = self.db.execute(
                "SELECT session_epoch,person_id,day,requested_seconds "
                "FROM quota_refund_receipts WHERE event_id=?", (event_id,)
            ).fetchone()
            if existing is not None:
                if existing != (session_epoch, person_id, day, float(seconds)):
                    raise ValueError("Refund receipt reused with different payload")
                original_links = self.db.execute(
                    "SELECT charge_event_id FROM quota_refund_charge_links "
                    "WHERE refund_event_id=?", (event_id,)
                ).fetchall()
                if {row[0] for row in original_links} != set(charge_event_ids):
                    raise ValueError("Refund receipt replay with different charge window")
                return 0.0
            already_epoch = self.db.execute(
                "SELECT 1 FROM quota_refund_receipts "
                "WHERE session_epoch=? AND person_id=? AND day=?",
                (session_epoch, person_id, day),
            ).fetchone()
            if already_epoch:
                return 0.0
            eligible = 0.0
            for charge_event_id in charge_event_ids:
                charge = self.db.execute(
                    "SELECT person_id,day,charged_seconds FROM quota_tick_receipts "
                    "WHERE event_id=?", (charge_event_id,)
                ).fetchone()
                if (charge is None or charge[0] != person_id or charge[1] != day or
                        self.db.execute(
                            "SELECT 1 FROM quota_refund_charge_links "
                            "WHERE charge_event_id=?", (charge_event_id,)
                        ).fetchone()):
                    raise ValueError("Charge receipt missing, already refunded or belongs to another child")
                eligible += float(charge[2])
            used = self.db.execute(
                "SELECT seconds FROM daily_usage WHERE person_id=? AND day=?",
                (person_id, day),
            ).fetchone()
            actual = min(float(seconds), max(0.0, eligible),
                         max(0.0, float(used[0])) if used else 0.0)
            self.db.execute(
                "INSERT INTO quota_refund_receipts "
                "(event_id,session_epoch,person_id,day,requested_seconds,refunded_seconds,reason) "
                "VALUES (?,?,?,?,?,?,'inactivity')",
                (event_id, session_epoch, person_id, day, float(seconds), actual),
            )
            if actual > 0:
                self.db.execute(
                    "UPDATE daily_usage SET seconds=MAX(0,seconds-?) "
                    "WHERE person_id=? AND day=?",
                    (actual, person_id, day),
                )
            for charge_event_id in charge_event_ids:
                self.db.execute(
                    "INSERT INTO quota_refund_charge_links(charge_event_id,refund_event_id) "
                    "VALUES (?,?)", (charge_event_id, event_id),
                )
            return actual

    def refund(self, person_id: int, seconds: float, day: Optional[str] = None) -> float:
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Não é permitido reembolsar tempo negativo")
        day = day or date.today().isoformat()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self._require_quota_writer(service_receipt=False)
            self.db.execute("""
                UPDATE daily_usage SET seconds = MAX(0.0, seconds - ?)
                WHERE person_id=? AND day=?
            """, (float(seconds), person_id, day))
        return self.used(person_id, day)

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
        from datetime import datetime
        start = start.strip()
        end = end.strip()
        datetime.strptime(start, "%H:%M")
        datetime.strptime(end, "%H:%M")
        self.set_setting("curfew_enabled", "true" if enabled else "false")
        self.set_setting("curfew_start", start)
        self.set_setting("curfew_end", end)

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
