"""Testes de regressao para eliminacao do loop do PowerShell e isolamento de fotos entre perfis."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request

import cv2
import numpy as np

from safepckids import app_server
from safepckids.app_server import SafePCKidsApiHandler
import safepckids.avatar_utils as avatar_utils
from safepckids.camera_service import CameraService
import safepckids.installer_engine as installer_engine
import safepckids.launcher as launcher
from safepckids.storage import Storage

ROOT = Path(__file__).resolve().parent.parent


class TestPowerShellLoopAndSubprocesses(unittest.TestCase):
    def test_painel_bat_has_elevated_guard_and_hidden_powershell(self):
        bat = (ROOT / "scripts" / "Painel-SafePCKids.bat").read_text(encoding="utf-8")
        self.assertIn("--elevated", bat)
        self.assertIn("-WindowStyle Hidden", bat)
        self.assertIn("--dashboard", bat)
        self.assertNotIn("Start-Process cmd", bat)

    def test_launcher_elevated_guard_prevents_recursive_relaunch(self):
        with patch.object(launcher.sys, "platform", "win32"), \
             patch.object(launcher.sys, "argv", ["launcher.py", "--dashboard", "--elevated"]), \
             patch.object(launcher, "is_admin", return_value=False), \
             patch("ctypes.windll", create=True) as mock_windll:
            launcher.ensure_admin_if_needed()
            mock_windll.shell32.ShellExecuteW.assert_not_called()

    def test_launcher_frozen_relaunch_does_not_pass_minus_m(self):
        with patch.object(launcher.sys, "platform", "win32"), \
             patch.object(launcher.sys, "frozen", True, create=True), \
             patch.object(launcher.sys, "executable", r"C:\SafePCKids\SafePCKids-Instalador.exe"), \
             patch.object(launcher.sys, "argv", [r"C:\SafePCKids\SafePCKids-Instalador.exe", "--dashboard"]), \
             patch.object(launcher, "is_admin", return_value=False), \
             patch("ctypes.windll", create=True) as mock_windll:
            mock_windll.shell32.ShellExecuteW.return_value = 42
            with self.assertRaises(SystemExit) as cm:
                launcher.ensure_admin_if_needed()
            self.assertEqual(cm.exception.code, 0)
            call_args = mock_windll.shell32.ShellExecuteW.call_args[0]
            self.assertEqual(call_args[1], "runas")
            self.assertEqual(call_args[2], r"C:\SafePCKids\SafePCKids-Instalador.exe")
            self.assertNotIn("-m", call_args[3])
            self.assertIn("--dashboard", call_args[3])
            self.assertIn("--elevated", call_args[3])
            self.assertEqual(call_args[5], 0)

    def test_installer_runner_parses_minus_m_and_avoids_loop(self):
        import importlib.util
        runner_path = ROOT / "packaging" / "installer_runner.py"
        spec = importlib.util.spec_from_file_location("installer_runner_mod", runner_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        module_name, clean = mod._parse_runner_args(["-E", "-s", "-m", "safepckids.launcher", "--dashboard", "--elevated"])
        self.assertEqual(module_name, "safepckids.launcher")
        self.assertEqual(clean, ["--dashboard"])

        with patch.object(mod, "ensure_admin_if_needed"), \
             patch.object(mod.safepckids.launcher, "main", return_value=0) as mock_launcher_main:
            rc = mod.main(["-E", "-s", "-m", "safepckids.launcher", "--dashboard"])
            self.assertEqual(rc, 0)
            mock_launcher_main.assert_called_once_with(["--dashboard", "--elevated"])

        with patch.object(mod.sys, "platform", "win32"), \
             patch.object(mod, "is_admin", return_value=False), \
             patch("ctypes.windll", create=True) as mock_windll:
            mod.ensure_admin_if_needed(["--dashboard", "--elevated"])
            mock_windll.shell32.ShellExecuteW.assert_not_called()

    def test_create_desktop_shortcuts_uses_pythonw_dashboard_and_windowstyle_7(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            fake_root = base / "SafePCKids"
            pyw = fake_root / ".venv" / "Scripts" / "pythonw.exe"
            pyw.parent.mkdir(parents=True)
            pyw.write_bytes(b"exe")
            desktop = base / "Desktop"
            desktop.mkdir()
            progdata = base / "ProgramData"
            start_menu = progdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "SafePCKids"
            start_menu.mkdir(parents=True)

            cmds = []

            def fake_run(cmd, timeout=5.0, capture=False):
                cmds.append(cmd)
                if len(cmd) >= 1 and cmd[0] == "powershell":
                    # Simula criacao dos dois .lnk esperados
                    (desktop / "SafePCKids - Painel dos Pais.lnk").write_bytes(b"lnk")
                    (start_menu / "SafePCKids - Painel dos Pais.lnk").write_bytes(b"lnk")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with patch.object(installer_engine.sys, "platform", "win32"), \
                 patch.object(installer_engine, "PROGRAMDATA_DIR", progdata), \
                 patch.dict(os.environ, {"USERPROFILE": str(base), "PROGRAMDATA": str(progdata)}), \
                 patch.object(installer_engine, "_run_win_cmd", side_effect=fake_run):
                installer_engine.create_desktop_shortcuts(fake_root)

            panel_cmds = [c for c in cmds if "SafePCKids - Painel dos Pais.lnk" in " ".join(c)]
            self.assertEqual(len(panel_cmds), 2)
            for cmd in panel_cmds:
                joined = " ".join(cmd)
                self.assertIn("-WindowStyle Hidden", joined)
                self.assertIn(str(pyw.resolve()), joined)
                self.assertIn("-m safepckids.launcher --dashboard", joined)
                self.assertIn("WindowStyle = 7", joined)
                self.assertNotIn("Painel-SafePCKids.bat", joined)

    def test_create_desktop_shortcuts_frozen_exe_does_not_pass_minus_m(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            fake_root = base / "AppRoot"
            fake_root.mkdir()
            frozen_exe = fake_root / "SafePCKids-Instalador.exe"
            frozen_exe.write_bytes(b"exe")
            desktop = base / "Desktop"
            desktop.mkdir()
            progdata = base / "ProgramData"
            start_menu = progdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "SafePCKids"
            start_menu.mkdir(parents=True)

            cmds = []

            def fake_run(cmd, timeout=5.0, capture=False):
                cmds.append(cmd)
                (desktop / "SafePCKids - Painel dos Pais.lnk").write_bytes(b"lnk")
                (start_menu / "SafePCKids - Painel dos Pais.lnk").write_bytes(b"lnk")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with patch.object(installer_engine.sys, "platform", "win32"), \
                 patch.object(installer_engine.sys, "frozen", True, create=True), \
                 patch.object(installer_engine.sys, "executable", str(frozen_exe)), \
                 patch.object(installer_engine, "PROGRAMDATA_DIR", progdata), \
                 patch.dict(os.environ, {"USERPROFILE": str(base), "PROGRAMDATA": str(progdata)}), \
                 patch.object(installer_engine, "_run_win_cmd", side_effect=fake_run):
                installer_engine.create_desktop_shortcuts(fake_root)

            joined = " ".join(cmds[0])
            self.assertIn(str(frozen_exe.resolve()), joined)
            self.assertIn("Arguments = '--dashboard'", joined)
            self.assertNotIn("-m safepckids.launcher", joined)
            self.assertIn("WindowStyle = 7", joined)

    def test_subprocess_popen_uses_create_no_window_on_windows(self):
        import safepckids.app_window as app_window
        import safepckids.filhos_agent as filhos_agent

        expected_flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        with patch.object(filhos_agent.os, "name", "nt"), \
             patch.object(filhos_agent.subprocess, "Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=1234, poll=MagicMock(return_value=None))
            filhos_agent._welcome_proc = None
            filhos_agent.trigger_welcome_screen()
            mock_popen.assert_called_once()
            self.assertEqual(mock_popen.call_args.kwargs.get("creationflags"), expected_flag)
            filhos_agent._welcome_proc = None

        fake_server = MagicMock()

        def stop_loop(_seconds):
            app_window.SafePCKidsApiHandler.shutdown_requested = True

        with patch.object(app_window, "run_app_server", return_value=(fake_server, 55555)), \
             patch.object(app_window, "find_edge_executable", return_value=r"C:\Edge\msedge.exe"), \
             patch.object(app_window.os, "name", "nt"), \
             patch.object(app_window.sys, "platform", "win32"), \
             patch.object(app_window.time, "sleep", side_effect=stop_loop), \
             patch.object(app_window.subprocess, "Popen") as mock_edge_popen:
            mock_edge_popen.return_value = MagicMock(poll=MagicMock(return_value=0))
            app_window.open_app_window(mode="dashboard", port=55555)
            mock_edge_popen.assert_called_once()
            self.assertEqual(mock_edge_popen.call_args.kwargs.get("creationflags"), expected_flag)


class TestPhotoAndAvatarIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), SafePCKidsApiHandler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path: str) -> tuple[int, bytes]:
        req = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def _post_json(self, path: str, payload: dict) -> tuple[int, dict]:
        raw = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=raw,
            headers={"Content-Type": "application/json", "Content-Length": str(len(raw))},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    @staticmethod
    def _make_jpeg_bytes(color_bgr: tuple[int, int, int]) -> bytes:
        img = np.zeros((80, 80, 3), dtype=np.uint8)
        img[:] = color_bgr
        ok, buf = cv2.imencode(".jpg", img)
        assert ok
        return buf.tobytes()

    def test_two_profiles_keep_strictly_isolated_photos_and_avatars(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            db_path = base / "criancas.sqlite3"
            fotos_dir = base / "fotos"
            store = Storage(db_path)
            id1 = store.add_person("Pai", 120)
            id2 = store.add_person("Miguel", 120)

            blue_jpg = self._make_jpeg_bytes((255, 0, 0))
            red_jpg = self._make_jpeg_bytes((0, 0, 255))
            green_jpg = self._make_jpeg_bytes((0, 255, 0))

            (fotos_dir / f"amostras_{id1}").mkdir(parents=True)
            (fotos_dir / f"amostras_{id2}").mkdir(parents=True)
            for i in range(1, 4):
                (fotos_dir / f"amostras_{id1}" / f"amostra_{i}.jpg").write_bytes(blue_jpg)
                store.add_profile_photo(id1, blue_jpg, select=(i == 1))
                sample2 = green_jpg if i == 2 else red_jpg
                (fotos_dir / f"amostras_{id2}" / f"amostra_{i}.jpg").write_bytes(sample2)
                store.add_profile_photo(id2, sample2, select=(i == 1))
            store.close()

            with patch.object(app_server, "PROGRAMDATA_DIR", base), \
                 patch.object(app_server, "DEFAULT_DB_FILE", db_path), \
                 patch.object(avatar_utils, "AVATAR_DIR", fotos_dir):
                # Seleciona foto 1 para perfil 1 e foto 2 para perfil 2
                st1, _ = self._post_json(f"/api/children/{id1}/photos/select", {"index": 1})
                st2, _ = self._post_json(f"/api/children/{id2}/photos/select", {"index": 2})
                self.assertEqual(st1, 200)
                self.assertEqual(st2, 200)

                _, list1_raw = self._get(f"/api/children/{id1}/photos")
                _, list2_raw = self._get(f"/api/children/{id2}/photos")
                list1 = json.loads(list1_raw.decode("utf-8"))
                list2 = json.loads(list2_raw.decode("utf-8"))

                self.assertTrue(all(f"/api/children/{id1}/photos/" in p["url"] for p in list1["photos"]))
                self.assertTrue(all(f"/api/children/{id2}/photos/" in p["url"] for p in list2["photos"]))
                self.assertTrue(list1["photos"][0]["selected"])
                self.assertTrue(list2["photos"][1]["selected"])

                s_a, bytes_a = self._get(f"/api/children/{id1}/photos/1")
                s_b, bytes_b = self._get(f"/api/children/{id2}/photos/2")
                self.assertEqual(s_a, 200)
                self.assertEqual(s_b, 200)
                self.assertEqual(bytes_a, blue_jpg)
                self.assertEqual(bytes_b, green_jpg)
                self.assertNotEqual(bytes_a, bytes_b)

                av1_status, av1_bytes = self._get(f"/api/child/{id1}/avatar")
                av2_status, av2_bytes = self._get(f"/api/child/{id2}/avatar")
                self.assertEqual(av1_status, 200)
                self.assertEqual(av2_status, 200)
                self.assertNotEqual(av1_bytes, av2_bytes)

                # Garante que selecionar foto nao duplica linhas em profile_photos
                chk = Storage(db_path)
                self.assertEqual(len(chk.profile_photos(id1)), 3)
                self.assertEqual(len(chk.profile_photos(id2)), 3)
                chk.close()

    def test_enroll_start_rejects_empty_target_instead_of_falling_back_to_id_1(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "criancas.sqlite3"
            store = Storage(db_path)
            store.add_person("Pai", 120)
            store.add_person("Miguel", 120)
            store.close()

            with patch.object(app_server, "DEFAULT_DB_FILE", db_path), \
                 patch.object(app_server.CameraService, "get_instance") as mock_cam:
                status, data = self._post_json("/api/camera/enroll/start", {"child_id": 0, "child_name": ""})
                self.assertEqual(status, 400)
                self.assertFalse(data.get("ok"))
                mock_cam.return_value.start_enrollment.assert_not_called()

                status_missing, data_missing = self._post_json("/api/camera/enroll/start", {"child_id": 999})
                self.assertEqual(status_missing, 404)
                self.assertFalse(data_missing.get("ok"))
                mock_cam.return_value.start_enrollment.assert_not_called()

    def test_enrollment_status_is_isolated_by_child_id(self):
        cam = CameraService()
        cam.enrollment_state = {
            "active": False,
            "child_id": 1,
            "samples_count": 12,
            "total_required": 12,
            "completed": True,
            "error": None,
            "message": "Cadastro concluido com sucesso!",
            "latest_avatar_b64": "data:image/png;base64,AAAA",
        }
        s1 = cam.get_enrollment_status(child_id=1)
        s2 = cam.get_enrollment_status(child_id=2)
        self.assertTrue(s1["completed"])
        self.assertEqual(s1["latest_avatar_b64"], "data:image/png;base64,AAAA")
        self.assertFalse(s2["completed"])
        self.assertIsNone(s2["latest_avatar_b64"])
        self.assertEqual(s2["child_id"], 2)

    def test_new_child_clears_any_stale_avatar_files_and_duplicate_name_returns_400(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            db_path = base / "criancas.sqlite3"
            fotos_dir = base / "fotos"
            (fotos_dir / "amostras_1").mkdir(parents=True)
            stale_avatar = fotos_dir / "crianca_1_avatar.png"
            stale_avatar.write_bytes(b"stale_png")
            stale_sample = fotos_dir / "amostras_1" / "amostra_1.jpg"
            stale_sample.write_bytes(b"stale_jpg")

            with patch.object(app_server, "DEFAULT_DB_FILE", db_path), \
                 patch.object(avatar_utils, "AVATAR_DIR", fotos_dir):
                st_ok, data_ok = self._post_json("/api/child/add", {"name": "Miguel", "daily_limit_hours": 2})
                self.assertEqual(st_ok, 200)
                self.assertTrue(data_ok["ok"])
                self.assertEqual(data_ok["id"], 1)
                self.assertFalse(stale_avatar.exists())
                self.assertFalse(stale_sample.exists())

                st_dup, data_dup = self._post_json("/api/child/add", {"name": "Miguel", "daily_limit_hours": 2})
                self.assertEqual(st_dup, 400)
                self.assertFalse(data_dup["ok"])

    def test_frontend_has_no_hardcoded_child_id_1_enrollment_and_clears_modal_state(self):
        app_html = (ROOT / "safepckids" / "ui_assets" / "app.html").read_text(encoding="utf-8")
        bridge_js = (ROOT / "safepckids" / "ui_assets" / "api_bridge.js").read_text(encoding="utf-8")
        self.assertNotIn("startEnrollment(1)", app_html)
        self.assertNotIn("startEnrollment(childId = 1", bridge_js)
        self.assertIn("activeGalleryChildId !== childId", app_html)
        self.assertIn("getEnrollmentStatus(childId)", app_html)
        self.assertIn("getEnrollmentStatus(targetChildId)", app_html)


if __name__ == "__main__":
    unittest.main()
