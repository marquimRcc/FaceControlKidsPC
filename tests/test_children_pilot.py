import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from facekids.children_pilot import (
    validate_real_lock, _child_id, child_pilot_database, _status,
)
from facekids.child_quota_pilot import ChildQuotaEngine, provision_three_children
from facekids.storage import Storage


class ChildrenPilotCliTests(unittest.TestCase):
    def test_admin_real_lock_refused_even_with_confirmation(self):
        for os_type, account, confirm in (
            ("nt","MarcosMiniPC",True), ("posix","Filhos",True),
            ("nt","Filhos",False), ("nt","FILHOS ",True)
        ):
            with self.subTest(os_type=os_type,account=account):
                with self.assertRaises(PermissionError):
                    validate_real_lock(os_type, account, confirmed=confirm)
        validate_real_lock("nt","fIlHoS",confirmed=True)

    def test_child_profile_mapping_never_accepts_fourth(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Storage(Path(directory)/"kids.sqlite3")
            try:
                provision_three_children(db)
                engine=ChildQuotaEngine(db)
                self.assertEqual(_child_id(db,1),next(iter(engine.people)))
                with self.assertRaises(KeyError):
                    _child_id(db,4)
                fourth = db.add_person("Crianca ficticia 4", 30)
                self.assertEqual(_child_id(db,fourth), fourth)
                engine = ChildQuotaEngine(db)
                with patch("builtins.print") as printer:
                    _status(db,engine)
                self.assertEqual(printer.call_count,4)
            finally:
                db.close()


if __name__=="__main__":
    unittest.main()
