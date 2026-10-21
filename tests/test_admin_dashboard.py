import json
import tempfile
import unittest
from pathlib import Path

from facekids.admin_dashboard import is_admin_account, time_format_hm
from facekids.avatar_utils import PhotoUpdateResult, set_child_photo_from_file, remove_child_avatar_files
from facekids.storage import Storage


class TestAdminDashboard(unittest.TestCase):
    def test_is_admin_account(self):
        # On MarcosMiniPC, account check must return True
        self.assertTrue(is_admin_account())

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


if __name__ == "__main__":
    unittest.main()
