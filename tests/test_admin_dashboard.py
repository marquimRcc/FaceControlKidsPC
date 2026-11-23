import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from safepckids.admin_dashboard import AdminDashboard, is_admin_account, time_format_hm
from safepckids.avatar_utils import PhotoUpdateResult, set_child_photo_from_file, remove_child_avatar_files, get_child_avatar_path
from safepckids.storage import Storage


class TestAdminDashboard(unittest.TestCase):
    def test_is_admin_account(self):
        # On MarcosMiniPC, account check must return True
        self.assertTrue(is_admin_account())

    def test_is_admin_account_denied_for_filhos(self):
        with patch.dict(os.environ, {"USERNAME": "Filhos"}):
            with patch("safepckids.admin_dashboard.windows_token_user", return_value="Filhos"):
                self.assertFalse(is_admin_account())

    def test_time_format_hm(self):
        self.assertEqual(time_format_hm(0), "0 min")
        self.assertEqual(time_format_hm(59), "0 min")
        self.assertEqual(time_format_hm(60), "1 min")
        self.assertEqual(time_format_hm(1500), "25 min")
        self.assertEqual(time_format_hm(3600), "1h 00min")
        self.assertEqual(time_format_hm(5400), "1h 30min")
        self.assertEqual(time_format_hm(7200), "2h 00min")
        self.assertEqual(time_format_hm(-100), "0 min")

    def test_photo_update_result_bool_and_unpacking(self):
        res_ok = PhotoUpdateResult(True, "Sucesso", Path("avatar.png"))
        self.assertTrue(res_ok)
        self.assertEqual(res_ok.message, "Sucesso")
        ok, msg = res_ok
        self.assertTrue(ok)
        self.assertEqual(msg, "Sucesso")

        res_fail = PhotoUpdateResult(False, "Falhou", None)
        self.assertFalse(res_fail)
        self.assertEqual(res_fail.message, "Falhou")
        ok2, msg2 = res_fail
        self.assertFalse(ok2)
        self.assertEqual(msg2, "Falhou")

    def test_set_child_photo_invalid_file(self):
        res = set_child_photo_from_file(999, "arquivo_inexistente_12345.jpg")
        self.assertFalse(res)
        self.assertIn("Não foi possível carregar", res.message)

    def test_welcome_photo_does_not_change_biometrics(self):
        dashboard = MagicMock()
        dashboard.store = MagicMock()
        dashboard.status_text = MagicMock()
        result = PhotoUpdateResult(True, "Foto atualizada", Path("avatar.png"))
        with patch("safepckids.admin_dashboard.filedialog.askopenfilename", return_value="foto.png"), \
             patch("safepckids.admin_dashboard.set_child_photo_from_file", return_value=result) as update, \
             patch("safepckids.admin_dashboard.messagebox.showinfo"):
            AdminDashboard._pick_photo_file(dashboard, 2)

        self.assertFalse(update.call_args.kwargs["update_biometrics"])
        dashboard.refresh.assert_called_once_with()

    def test_storage_curfew_policy_flow(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test.sqlite3"
            store = Storage(db_path)
            # Default
            self.assertFalse(store.get_curfew_config()[0])
            # Enable
            store.set_curfew_config(True, "08:00", "20:00")
            en, s, e = store.get_curfew_config()
            self.assertTrue(en)
            self.assertEqual(s, "08:00")
            self.assertEqual(e, "20:00")
            store.close()

    def test_storage_parent_pin_flow(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test.sqlite3"
            store = Storage(db_path)
            # No PIN
            self.assertIsNone(store.get_parent_pin())
            self.assertTrue(store.verify_parent_pin("any"))
            # Set PIN
            store.set_parent_pin("1234")
            self.assertIsNotNone(store.get_parent_pin())
            self.assertTrue(store.verify_parent_pin("1234"))
            self.assertFalse(store.verify_parent_pin("9999"))
            # Remove PIN
            store.set_parent_pin(None)
            self.assertIsNone(store.get_parent_pin())
            store.close()

    def test_get_child_avatar_path_converts_jpg_to_png(self):
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as td:
            avatar_dir = Path(td) / "fotos"
            avatar_dir.mkdir(parents=True, exist_ok=True)
            jpg_file = avatar_dir / "crianca_9.jpg"
            dummy = np.zeros((100, 100, 3), dtype=np.uint8)
            cv2.imwrite(str(jpg_file), dummy)

            with patch("safepckids.avatar_utils.AVATAR_DIR", avatar_dir):
                res = get_child_avatar_path(9)
                self.assertIsNotNone(res)
                self.assertTrue(res.name.endswith(".png"))
                self.assertTrue(res.exists())

    def test_sample_photos_gallery_and_selection(self):
        import cv2
        import numpy as np
        from safepckids.avatar_utils import get_child_sample_photos, select_child_sample_photo
        with tempfile.TemporaryDirectory() as td:
            avatar_dir = Path(td) / "fotos"
            samples_dir = avatar_dir / "amostras_7"
            samples_dir.mkdir(parents=True, exist_ok=True)

            # Cria 12 amostras ficticias
            for i in range(1, 13):
                img = np.zeros((80, 80, 3), dtype=np.uint8)
                img[:] = (i * 20 % 255, 100, 150)
                cv2.imwrite(str(samples_dir / f"amostra_{i}.jpg"), img)

            with patch("safepckids.avatar_utils.AVATAR_DIR", avatar_dir):
                samples = get_child_sample_photos(7)
                self.assertEqual(len(samples), 12)
                self.assertTrue(samples[0]["selected"])

                # Seleciona a amostra 5
                ok = select_child_sample_photo(7, samples[4]["path"], sample_index=5)
                self.assertTrue(ok)
                self.assertTrue((avatar_dir / "crianca_7.jpg").exists())
                self.assertTrue((avatar_dir / "crianca_7_avatar.png").exists())
                self.assertEqual((samples_dir / "selecionada.txt").read_text().strip(), "5")

                # Verifica que apos a selecao, a foto 5 esta marcada como selected=True
                samples_updated = get_child_sample_photos(7)
                self.assertFalse(samples_updated[0]["selected"])
                self.assertTrue(samples_updated[4]["selected"])

    def test_child_programs_dialog_toggle_and_save(self):
        import tkinter as tk
        from safepckids.admin_dashboard import ChildProgramsDialog
        from safepckids.program_policy import load_programs_config, set_program_allowed_for_child

        temp_dir = tempfile.TemporaryDirectory()
        cfg_file = Path(temp_dir.name) / "programas.json"
        cfg_file.write_text(json.dumps({
            "enabled": True,
            "programs": [
                {"name": "Roblox", "executable": "RobloxPlayerBeta.exe", "enabled": True, "blocked_child_ids": []},
                {"name": "Brave", "executable": "brave.exe", "enabled": True, "blocked_child_ids": []},
            ]
        }), encoding="utf-8")

        root = tk.Tk()
        root.withdraw()
        try:
            with patch("safepckids.admin_dashboard.PROGRAMS_FILE", cfg_file), \
                 patch("safepckids.program_policy.PROGRAMS_FILE", cfg_file), \
                 patch("safepckids.admin_dashboard.messagebox.showinfo"):
                dialog = ChildProgramsDialog(root, child_id=1, child_name="Miguel")

                prog_roblox = dialog.config_data["programs"][0]
                set_program_allowed_for_child(prog_roblox, 1, False)

                dialog._save()

                saved_cfg = load_programs_config(cfg_file)
                self.assertEqual(saved_cfg["programs"][0]["blocked_child_ids"], [1])
                self.assertEqual(saved_cfg["programs"][1]["blocked_child_ids"], [])
                dialog.destroy()
        finally:
            root.destroy()
            temp_dir.cleanup()

    def test_add_program_dialog_and_auto_detect(self):
        import tkinter as tk
        from safepckids.admin_dashboard import AddProgramDialog, ProgramsConfigDialog

        root = tk.Tk()
        root.withdraw()
        try:
            cfg = {"enabled": True, "programs": []}
            added = []
            with patch("safepckids.admin_dashboard.tk.Toplevel.grab_set"), \
                 patch("safepckids.admin_dashboard.discover_installed_programs", return_value=[
                    {"name": "Roblox", "executable": r"C:\Roblox\RobloxPlayerBeta.exe", "arguments": "", "enabled": True, "blocked_child_ids": []},
                    {"name": "Minecraft", "executable": r"C:\Minecraft\launcher.exe", "arguments": "", "enabled": True, "blocked_child_ids": []},
                 ]):
                dlg = AddProgramDialog(root, cfg, on_added=lambda: added.append(True))
                dlg.name_var.set("Roblox")
                dlg.exe_var.set(r"C:\Roblox\RobloxPlayerBeta.exe")
                dlg._confirm()

                self.assertEqual(len(cfg["programs"]), 1)
                self.assertEqual(cfg["programs"][0]["name"], "Roblox")
                self.assertEqual(len(added), 1)

                root.store = None
                with patch("safepckids.admin_dashboard.load_programs_config", return_value=cfg), \
                     patch("safepckids.admin_dashboard.messagebox.showinfo"):
                    p_dlg = ProgramsConfigDialog(root)
                    p_dlg._auto_detect()
                    names = [p["name"] for p in p_dlg.config_data["programs"]]
                    self.assertIn("Roblox", names)
                    self.assertIn("Minecraft", names)
                    p_dlg.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
