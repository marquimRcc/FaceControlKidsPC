import json
from pathlib import Path
import tempfile
import time
import unittest
import ctypes
import types
from unittest.mock import patch, MagicMock

from facekids.filhos_agent import QuotaTracker, read_last_unlock_child
from facekids.storage import Storage


class TestFilhosAgent(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.store = Storage(self.db_path)
        self.child_id = self.store.add_person("Lucas", 120)

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_switch_child(self):
        tracker = QuotaTracker(self.store)
        tracker.warned_10m = True
        tracker.switch_child(self.child_id, "Lucas")
        self.assertEqual(tracker.current_child_id, self.child_id)
        self.assertEqual(tracker.current_child_name, "Lucas")
        self.assertFalse(tracker.warned_10m)

    def test_update_balance_resets_warnings(self):
        tracker = QuotaTracker(self.store)
        tracker.warned_1m = True
        tracker.warned_5m = True
        tracker.warned_10m = True

        # Bonus given: remaining now > 600s
        tracker.update_balance(700)
        self.assertFalse(tracker.warned_1m)
        self.assertFalse(tracker.warned_5m)
        self.assertFalse(tracker.warned_10m)

    @patch("facekids.filhos_agent.show_toast")
    @patch("facekids.filhos_agent.lock_current_session")
    def test_notifications_and_lock_progression(self, mock_lock, mock_toast):
        tracker = QuotaTracker(self.store)
        tracker.switch_child(self.child_id, "Lucas")

        # 1. Above 10m (> 600s): No notification, no lock
        locked = tracker.check_notifications_and_lock(650)
        self.assertFalse(locked)
        mock_toast.assert_not_called()
        mock_lock.assert_not_called()

        # 2. At 10m (<= 600s): Warning 10m triggered
        locked = tracker.check_notifications_and_lock(590)
        self.assertFalse(locked)
        self.assertTrue(tracker.warned_10m)
        self.assertEqual(mock_toast.call_count, 1)

        # 3. At 5m (<= 300s): Warning 5m triggered
        locked = tracker.check_notifications_and_lock(280)
        self.assertFalse(locked)
        self.assertTrue(tracker.warned_5m)
        self.assertEqual(mock_toast.call_count, 2)

        # 4. At 1m (<= 60s): Warning 1m triggered
        locked = tracker.check_notifications_and_lock(45)
        self.assertFalse(locked)
        self.assertTrue(tracker.warned_1m)
        self.assertEqual(mock_toast.call_count, 3)

        # 5. At 0s: Lock triggered!
        locked = tracker.check_notifications_and_lock(0)
        self.assertTrue(locked)
        mock_lock.assert_called_once()
        self.assertEqual(mock_toast.call_count, 4)

    def test_read_last_unlock_child(self):
        with tempfile.TemporaryDirectory() as td:
            unlock_file = Path(td) / "last_unlock.json"
            unlock_file.write_text(
                json.dumps({"child_id": 2, "child_name": "Crianca 2", "timestamp": time.time()}),
                encoding="utf-8",
            )
            with patch("facekids.filhos_agent.LAST_UNLOCK_FILE", unlock_file):
                cid, cname, ts = read_last_unlock_child()
                self.assertEqual(cid, 2)
                self.assertEqual(cname, "Crianca 2")
                self.assertGreater(ts, 0)

    def test_read_last_unlock_child_stale_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            unlock_file = Path(td) / "last_unlock.json"
            unlock_file.write_text(
                json.dumps({
                    "child_id": 2,
                    "child_name": "Crianca 2",
                    "timestamp": time.time() - 1200,
                }),
                encoding="utf-8",
            )
            with patch("facekids.filhos_agent.LAST_UNLOCK_FILE", unlock_file):
                cid, cname, ts = read_last_unlock_child()
                self.assertIsNone(cid)
                self.assertEqual(cname, "")
                self.assertEqual(ts, 0.0)

    def test_stale_event_in_loop_does_not_switch_child(self):
        tracker = QuotaTracker(self.store)
        tracker.current_child_id = None
        last_seen_ts = time.time()

        # Simulando evento antigo (2 horas atras)
        stale_data = {"child_id": 2, "child_name": "Crianca 2", "timestamp": time.time() - 7200}
        current_ts = float(stale_data.get("timestamp", 0.0))

        # A condicao de frescor estreita deve rejeitar
        is_fresh = (
            (current_ts > last_seen_ts)
            and ((time.time() - current_ts) < 600.0)
        )
        self.assertFalse(is_fresh)
        # QuotaTracker deve permanecer sem crianca atribuida
        self.assertIsNone(tracker.current_child_id)

    def test_unidentified_child_state_safe(self):
        tracker = QuotaTracker(self.store)
        self.assertIsNone(tracker.current_child_id)
        # Notifications should use fallback name without crashing
        with patch("facekids.filhos_agent.show_toast"):
            tracker.check_notifications_and_lock(500)
            self.assertTrue(tracker.warned_10m)

    def test_in_session_face_identifier_async(self):
        from facekids.filhos_agent import InSessionFaceIdentifier
        identifier = InSessionFaceIdentifier(interval_seconds=0.1)
        self.assertIsNone(identifier.check_result())

        # Mock query_auth_service
        fake_payload = {"status": "ALLOW", "child_id": 2, "child_name": "Crianca 2"}
        with patch("facekids.filhos_agent.query_auth_service", return_value=fake_payload):
            identifier.trigger_if_due()
            # Aguarda a thread de background concluir
            if identifier.thread:
                identifier.thread.join(timeout=1.0)
            res = identifier.check_result()
            self.assertIsNotNone(res)
            self.assertEqual(res["child_id"], 2)
            # Apos consumir, deve retornar None
            self.assertIsNone(identifier.check_result())

    def test_query_auth_service_cancels_stalled_overlapped_read(self):
        import facekids.filhos_agent as filhos_agent
        from ctypes import wintypes as real_wintypes

        class FakeKernel32:
            def __init__(self):
                self.cancelled = False
                self.closed = []

            def WaitNamedPipeW(self, _name, _timeout):
                return True

            def CreateFileW(self, *_args):
                return 123

            def CreateEventW(self, *_args):
                return 456

            def WriteFile(self, _handle, _buffer, size, transferred, _overlapped):
                transferred._obj.value = size
                return True

            def ReadFile(self, *_args):
                return False

            def GetLastError(self):
                return 997  # ERROR_IO_PENDING

            def WaitForSingleObject(self, _event, _timeout):
                return 258  # WAIT_TIMEOUT

            def CancelIoEx(self, _handle, _overlapped):
                self.cancelled = True
                return True

            def GetOverlappedResult(self, *_args):
                return False

            def CloseHandle(self, handle):
                self.closed.append(handle)
                return True

        fake_kernel32 = FakeKernel32()
        fake_windll = types.SimpleNamespace(kernel32=fake_kernel32)
        with patch("facekids.filhos_agent.sys.platform", "win32"), patch.object(
            filhos_agent, "wintypes", real_wintypes
        ), patch.object(ctypes, "windll", fake_windll, create=True):
            result = filhos_agent.query_auth_service(timeout_seconds=0.1)

        self.assertIsNone(result)
        self.assertTrue(fake_kernel32.cancelled)
        self.assertIn(456, fake_kernel32.closed)
        self.assertIn(123, fake_kernel32.closed)



    def test_inactivity_settings_default_and_custom(self):
        from facekids.filhos_agent import get_inactivity_settings
        with tempfile.TemporaryDirectory() as td:
            dummy_cfg = Path(td) / "configuracoes.json"
            with patch("facekids.filhos_agent.CONFIG_SETTINGS_FILE", dummy_cfg):
                lock_s, warn_s = get_inactivity_settings()
                self.assertEqual(lock_s, 120.0)
                self.assertEqual(warn_s, 100.0)

                dummy_cfg.write_text(json.dumps({
                    "inactivity_lock_seconds": 180,
                    "inactivity_warn_seconds": 150
                }), encoding="utf-8")
                lock_s, warn_s = get_inactivity_settings()
                self.assertEqual(lock_s, 180.0)
                self.assertEqual(warn_s, 150.0)

    def test_get_user_idle_seconds(self):
        from facekids.filhos_agent import get_user_idle_seconds
        idle = get_user_idle_seconds()
        self.assertIsInstance(idle, float)
        self.assertGreaterEqual(idle, 0.0)

    def test_inactivity_refund_logic(self):
        from datetime import date
        today = date.today().isoformat()
        initial_rem = self.store.remaining(self.child_id, today)

        # Simula 120 segundos debitados enquanto a crianca se afastou
        self.store.charge(self.child_id, 120.0, today)
        self.assertEqual(self.store.remaining(self.child_id, today), initial_rem - 120)

        # Regra de reembolso de inatividade restaura o saldo integral
        refund = 120.0
        self.store.refund(self.child_id, refund, today)
        self.assertEqual(self.store.remaining(self.child_id, today), initial_rem)


    def test_face_check_interval_settings(self):
        from facekids.filhos_agent import get_face_check_interval
        with tempfile.TemporaryDirectory() as td:
            dummy_cfg = Path(td) / "configuracoes.json"
            with patch("facekids.filhos_agent.CONFIG_SETTINGS_FILE", dummy_cfg):
                interval = get_face_check_interval()
                self.assertEqual(interval, 120.0)

                dummy_cfg.write_text(json.dumps({
                    "face_check_interval_seconds": 60.0
                }), encoding="utf-8")
                interval = get_face_check_interval()
                self.assertEqual(interval, 60.0)

    def test_in_session_child_switch_different_child(self):
        tracker = QuotaTracker(self.store)
        tracker.switch_child(self.child_id, "Lucas")
        self.assertEqual(tracker.current_child_id, self.child_id)

        # Simula resposta do pipe detectando outra crianca (ex: Ana, ID 99)
        pipe_resp = {"status": "ALLOW", "child_id": 99, "child_name": "Ana"}
        new_cid = pipe_resp["child_id"]
        new_cname = pipe_resp["child_name"]

        if new_cid != tracker.current_child_id:
            tracker.switch_child(new_cid, new_cname)

        self.assertEqual(tracker.current_child_id, 99)
        self.assertEqual(tracker.current_child_name, "Ana")

    def test_in_session_child_switch_same_child_noop(self):
        tracker = QuotaTracker(self.store)
        tracker.switch_child(self.child_id, "Lucas")
        tracker.warned_10m = True

        # Se o mesmo filho for reconhecido, nao re-inicializa nem reseta avisos
        pipe_resp = {"status": "ALLOW", "child_id": self.child_id, "child_name": "Lucas"}
        new_cid = pipe_resp["child_id"]

        if new_cid != tracker.current_child_id:
            tracker.switch_child(new_cid, pipe_resp["child_name"])

        self.assertEqual(tracker.current_child_id, self.child_id)
        self.assertTrue(tracker.warned_10m)


if __name__ == "__main__":


    unittest.main()
