import unittest

from facekids.windows_session_diagnostic import LockView
from facekids.hardware_camera_probe import ProbeStats


class CameraProbeTests(unittest.TestCase):
    def test_positive_preliminary_requires_real_locked_samples(self):
        stats = ProbeStats()
        for _ in range(5):
            stats.record(LockView.LOCKED, frame_read=True, nonuniform=True)
        self.assertEqual(stats.locked_samples, 5)
        self.assertEqual(stats.locked_frames, 5)
        self.assertEqual(stats.locked_nonuniform, 5)
        self.assertEqual(stats.outcome(), "FRAMES_DURING_WIN_L_PRELIMINARY_ONLY")

    def test_never_confuse_unlocked_frames_with_locked_frames(self):
        stats = ProbeStats()
        for _ in range(10):
            stats.record(LockView.UNLOCKED, frame_read=True, nonuniform=True)
        self.assertEqual(stats.locked_frames, 0)
        self.assertEqual(stats.outcome(), "INCONCLUSIVE_NOT_ENOUGH_LOCKED_SAMPLES")

    def test_missing_camera_frames_do_not_count_as_evidence(self):
        stats = ProbeStats()
        for _ in range(6):
            stats.record(LockView.LOCKED, frame_read=False, nonuniform=True)
        self.assertEqual(stats.locked_frames, 0)
        self.assertEqual(stats.locked_nonuniform, 0)
        self.assertEqual(stats.camera_errors, 6)
        self.assertEqual(stats.outcome(), "NO_USABLE_LOCKED_FRAMES")

    def test_unknown_or_inactive_wts_state_does_not_count(self):
        stats = ProbeStats()
        for state in [LockView.UNKNOWN, LockView.INACTIVE, LockView.UNLOCKED] * 3:
            stats.record(state, frame_read=True, nonuniform=True)
        self.assertEqual(stats.unknown_sessions, 3)
        self.assertEqual(stats.locked_samples, 0)
        self.assertEqual(stats.outcome(), "INCONCLUSIVE_NOT_ENOUGH_LOCKED_SAMPLES")


if __name__ == "__main__":
    unittest.main()
