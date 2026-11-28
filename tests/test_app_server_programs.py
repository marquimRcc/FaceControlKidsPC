"""Testes dos endpoints e integracao UI de controle de programas por perfil no painel web."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from safepckids.app_server import SafePCKidsApiHandler
from safepckids.storage import Storage


class TestAppServerPrograms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), SafePCKidsApiHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def _post_json(self, path: str, payload_dict: dict) -> tuple[int, dict]:
        data = json.dumps(payload_dict).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(data)),
                "X-SafePCKids-Token": SafePCKidsApiHandler.session_token,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def _get_json(self, path: str) -> tuple[int, dict]:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={"X-SafePCKids-Token": SafePCKidsApiHandler.session_token},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_child_programs_crud_and_per_profile_isolation(self):
        with tempfile.TemporaryDirectory() as td:
            progdata = Path(td)
            db_path = progdata / "criancas.sqlite3"
            store = Storage(db_path)
            c1 = store.add_person("Miguel", 60)
            c2 = store.add_person("Elena", 120)
            store.close()

            with patch("safepckids.app_server.PROGRAMDATA_DIR", progdata), \
                 patch("safepckids.app_server.DEFAULT_DB_FILE", db_path):
                # 1. Lista inicial (cria arquivo padrao com Brave)
                status, data = self._get_json(f"/api/children/{c1}/programs")
                self.assertEqual(status, 200)
                self.assertTrue(data["ok"])
                self.assertEqual(len(data["programs"]), 1)
                self.assertEqual(data["programs"][0]["name"], "Brave")
                self.assertTrue(data["programs"][0]["allowed"])

                # 2. Adiciona novo programa
                status, add_res = self._post_json("/api/programs/add", {
                    "name": "Roblox",
                    "executable": r"C:\Games\RobloxPlayerBeta.exe",
                })
                self.assertEqual(status, 200)
                self.assertTrue(add_res["ok"])

                # 3. Duplicado retorna 409
                status, dup_res = self._post_json("/api/programs/add", {
                    "name": "Roblox",
                    "executable": "other.exe",
                })
                self.assertEqual(status, 409)
                self.assertFalse(dup_res["ok"])

                # 4. Bloqueia Roblox apenas para c1
                status, save_res = self._post_json(f"/api/children/{c1}/programs", {
                    "permissions": [
                        {"index": 0, "allowed": True},
                        {"index": 1, "allowed": False},
                    ]
                })
                self.assertEqual(status, 200)
                self.assertTrue(save_res["ok"])

                # 5. Verifica isolamento: c1 tem Roblox bloqueado, c2 continua liberado
                _, res_c1 = self._get_json(f"/api/children/{c1}/programs")
                _, res_c2 = self._get_json(f"/api/children/{c2}/programs")
                self.assertFalse(res_c1["programs"][1]["allowed"])
                self.assertTrue(res_c2["programs"][1]["allowed"])

                # 6. Dashboard reflete contagem por perfil
                _, dash = self._get_json("/api/dashboard")
                by_id = {c["id"]: c for c in dash["children"]}
                self.assertEqual(by_id[c1]["programs_allowed_count"], 1)
                self.assertEqual(by_id[c1]["programs_total_count"], 2)
                self.assertEqual(by_id[c2]["programs_allowed_count"], 2)
                self.assertEqual(by_id[c2]["programs_total_count"], 2)

                # 7. Remove Roblox do catalogo
                status, del_res = self._post_json("/api/programs/delete", {"index": 1})
                self.assertEqual(status, 200)
                self.assertTrue(del_res["ok"])

                _, res_after = self._get_json(f"/api/children/{c1}/programs")
                self.assertEqual(len(res_after["programs"]), 1)

    def test_programs_detect_deduplicates_existing(self):
        with tempfile.TemporaryDirectory() as td:
            progdata = Path(td)
            discovered = [
                {
                    "name": "Brave",
                    "executable": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                    "arguments": "",
                    "enabled": True,
                    "blocked_child_ids": [],
                },
                {
                    "name": "Minecraft Launcher",
                    "executable": r"C:\Program Files (x86)\Minecraft Launcher\MinecraftLauncher.exe",
                    "arguments": "",
                    "enabled": True,
                    "blocked_child_ids": [],
                },
            ]
            with patch("safepckids.app_server.PROGRAMDATA_DIR", progdata), \
                 patch("safepckids.app_server.discover_installed_programs", return_value=discovered):
                status, res = self._post_json("/api/programs/detect", {})
                self.assertEqual(status, 200)
                self.assertTrue(res["ok"])
                self.assertEqual(res["added_count"], 1)
                self.assertEqual(res["added_names"], ["Minecraft Launcher"])
                self.assertEqual(res["total"], 2)

    def test_validation_errors(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("safepckids.app_server.PROGRAMDATA_DIR", Path(td)):
                st1, _ = self._get_json("/api/children/abc/programs")
                self.assertEqual(st1, 400)

                st2, _ = self._post_json("/api/programs/add", {"name": "", "executable": "x.exe"})
                self.assertEqual(st2, 400)

                st3, _ = self._post_json("/api/programs/add", {"name": "App", "executable": ""})
                self.assertEqual(st3, 400)

                st4, _ = self._post_json("/api/programs/delete", {"index": 99})
                self.assertEqual(st4, 404)

    def test_web_ui_assets_expose_program_controls(self):
        ui_dir = Path(__file__).resolve().parent.parent / "safepckids" / "ui_assets"
        app_html = (ui_dir / "app.html").read_text(encoding="utf-8")
        api_bridge = (ui_dir / "api_bridge.js").read_text(encoding="utf-8")

        for token in ("programsModal", "openProgramsModal", "submitAddProgram", "deleteCatalogProgram", "saveChildProgramsModal"):
            self.assertIn(token, app_html)
        for method in ("getChildPrograms", "saveChildPrograms", "addProgram", "deleteProgram", "detectPrograms"):
            self.assertIn(method, api_bridge)
