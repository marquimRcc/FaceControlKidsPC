import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from facekids.agent_watchdog import (
    AgentWatchdog,
    WatchdogAction,
    read_agent_heartbeat,
    write_agent_heartbeat,
)
from facekids.session import SessionState


class TestAgentWatchdog(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.hb_file = Path(self.temp_dir.name) / "agent_heartbeat.json"
        self.recovery_mock = MagicMock(return_value=True)
        self.lock_mock = MagicMock(return_value=True)
        self.current_time = 1000.0

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_watchdog(
        self,
        *,
        active_user="Filhos",
        session_state=SessionState.ACTIVE,
        session_id=1,
        startup_grace=0.0,
    ):
        return AgentWatchdog(
            heartbeat_max_age=45.0,
            startup_grace_period=startup_grace,
            target_user="Filhos",
            heartbeat_file=self.hb_file,
            task_name="FaceKidsFilhosAgent",
            session_state_fn=lambda sid: session_state,
            session_user_fn=lambda sid: active_user,
            console_session_fn=lambda: session_id,
            recovery_fn=self.recovery_mock,
            lock_fn=self.lock_mock,
            time_fn=lambda: self.current_time,
        )

    def test_heartbeat_write_and_read(self):
        self.assertTrue(write_agent_heartbeat(self.hb_file))
        self.assertTrue(self.hb_file.exists())
        ts, pid = read_agent_heartbeat(self.hb_file)
        self.assertIsNotNone(ts)
        self.assertAlmostEqual(ts, time.time(), delta=3.0)
        self.assertIsInstance(pid, int)

    def test_watchdog_no_action_for_admin_user(self):
        wd = self._create_watchdog(active_user="MarcosMiniPC")
        action = wd.check_once()
        self.assertEqual(action, WatchdogAction.NO_ACTION)
        self.recovery_mock.assert_not_called()
        self.lock_mock.assert_not_called()

    def test_watchdog_no_action_when_filhos_session_locked(self):
        wd = self._create_watchdog(
            active_user="Filhos", session_state=SessionState.LOCKED
        )
        action = wd.check_once()
        self.assertEqual(action, WatchdogAction.NO_ACTION)
        self.recovery_mock.assert_not_called()
        self.lock_mock.assert_not_called()

    def test_watchdog_grace_period(self):
        wd = self._create_watchdog(active_user="Filhos", startup_grace=60.0)
        # No startup, com carência ativa, não deve disparar recuperação
        action = wd.check_once()
        self.assertEqual(action, WatchdogAction.GRACE_PERIOD)
        self.recovery_mock.assert_not_called()
        self.lock_mock.assert_not_called()

    def test_watchdog_heartbeat_ok_when_recent(self):
        # Grava heartbeat recente (10s atras)
        self.hb_file.write_text(
            json.dumps({"timestamp": self.current_time - 10.0, "pid": 1234}),
            encoding="utf-8",
        )
        wd = self._create_watchdog(active_user="Filhos", startup_grace=0.0)
        action = wd.check_once()
        self.assertEqual(action, WatchdogAction.HEARTBEAT_OK)
        self.recovery_mock.assert_not_called()
        self.lock_mock.assert_not_called()

    def test_watchdog_triggers_recovery_on_first_expired_heartbeat(self):
        # Heartbeat expirado (> 45s)
        self.hb_file.write_text(
            json.dumps({"timestamp": self.current_time - 50.0, "pid": 1234}),
            encoding="utf-8",
        )
        wd = self._create_watchdog(active_user="Filhos", startup_grace=0.0)
        action = wd.check_once()
        self.assertEqual(action, WatchdogAction.RECOVERY_TRIGGERED)
        self.recovery_mock.assert_called_once()
        self.lock_mock.assert_not_called()

    def test_watchdog_triggers_preventive_lock_on_consecutive_failures(self):
        # Sem heartbeat (arquivo ausente)
        wd = self._create_watchdog(active_user="Filhos", startup_grace=0.0)

        # Falha 1: Tenta recuperar
        action1 = wd.check_once()
        self.assertEqual(action1, WatchdogAction.RECOVERY_TRIGGERED)
        self.recovery_mock.assert_called_once()
        self.lock_mock.assert_not_called()

        # Falha 2: Mais 15s se passaram e o heartbeat continua ausente -> Bloqueio Preventivo
        self.current_time += 15.0
        action2 = wd.check_once()
        self.assertEqual(action2, WatchdogAction.PREVENTIVE_LOCK)
        self.lock_mock.assert_called_once_with(1)

    def test_watchdog_notify_allow_extends_grace(self):
        wd = self._create_watchdog(active_user="Filhos", startup_grace=0.0)
        wd.notify_allow()
        action = wd.check_once()
        self.assertEqual(action, WatchdogAction.GRACE_PERIOD)
        self.recovery_mock.assert_not_called()
        self.lock_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
