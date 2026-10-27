"""P6 guest diagnostics: no -c quoting and guaranteed camera release."""
import unittest
from unittest.mock import patch, MagicMock

from facekids import vm_guest_diagnostics as diag


class VmGuestDiagnosticsTests(unittest.TestCase):
    def test_dependency_check_imports_and_reports_success(self):
        with patch("builtins.print") as printer:
            self.assertEqual(diag.main(["dependencies"]), 0)
        printer.assert_called_once()
        self.assertIn("Tkinter", printer.call_args.args[0])

    def test_guest_camera_success_and_release(self):
        frame = object()
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (True, frame)
        with patch("cv2.VideoCapture", return_value=cap) as camera:
            with patch("builtins.print") as output:
                self.assertEqual(diag.main(["camera", "--index", "2"]), 0)
        camera.assert_called_once()
        self.assertEqual(camera.call_args.args[0], 2)
        cap.release.assert_called_once()
        output.assert_called_once_with("CAMERA_GUEST_INTERACTIVE=FRAME_OBSERVED")

    def test_guest_camera_unavailable_or_empty_frame_release(self):
        for opened, frames, wanted, label in [
            (False, (False, None), 2, "UNAVAILABLE"),
            (True, (False, None), 3, "NO_FRAME"),
            (True, (True, None), 3, "NO_FRAME"),
        ]:
            with self.subTest(opened=opened, frames=frames):
                cap = MagicMock()
                cap.isOpened.return_value = opened
                cap.read.return_value = frames
                with patch("cv2.VideoCapture", return_value=cap):
                    with patch("builtins.print") as output:
                        self.assertEqual(diag.main(["camera"]), wanted)
                cap.release.assert_called_once()
                output.assert_called_once_with(
                    "CAMERA_GUEST_INTERACTIVE=" + label)

    def test_camera_raises_but_still_releases(self):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.side_effect = RuntimeError("device disconnected")
        with patch("cv2.VideoCapture", return_value=cap):
            with self.assertRaises(RuntimeError):
                diag.main(["camera"])
        cap.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
