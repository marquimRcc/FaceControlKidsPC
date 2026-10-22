import unittest

from facekids.linux_probe import ProbeResult


class LinuxProbeTests(unittest.TestCase):
    def test_status_is_conservative(self):
        self.assertEqual(ProbeResult(False, 0, 0, 0, 0, None).status, "CAMERA_NAO_ABRIU")
        self.assertEqual(ProbeResult(True, 0, 0, 0, 1, None).status, "SEM_QUADROS")
        self.assertEqual(
            ProbeResult(True, 10, 0, 0, 1, 0.5).status,
            "QUADROS_PRETOS_OU_UNIFORMES",
        )
        self.assertEqual(
            ProbeResult(True, 10, 8, 0, 1, 80).status,
            "CAMERA_UTILIZAVEL",
        )


if __name__ == "__main__":
    unittest.main()
