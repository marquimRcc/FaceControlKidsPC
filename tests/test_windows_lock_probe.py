import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from facekids.session import SessionState
from facekids.windows_lock_probe import (
    ProbeSample, assess_sample, observe, run_probe, summarize,
)


class FakeCamera:
    def __init__(self, ok=True):
        self.ok = ok
    def read(self):
        return (self.ok, object() if self.ok else None)


class LockProbeTest(unittest.TestCase):
    def test_locked_camera_is_positive_only_with_actual_locked_samples(self):
        active = assess_sample(1, SessionState.ACTIVE, True, (640,480), (100,45))
        locked = assess_sample(2, SessionState.LOCKED, True, (640,480), (100,45))
        report = summarize([active] + [locked] * 5)
        self.assertEqual(report["result"], "CAMERA_READS_DURING_LOCK")
        self.assertEqual(report["locked_nonuniform_frames"], 5)

    def test_no_locked_samples_is_not_a_success(self):
        active = assess_sample(2, SessionState.ACTIVE, True, (640,480), (100,45))
        self.assertEqual(summarize([active] * 20)["result"], "INCONCLUSIVE")

    def test_black_frames_do_not_count_as_valid_locked_frames(self):
        locked = assess_sample(5, SessionState.LOCKED, True, (640,480), (0, 0))
        self.assertEqual(summarize([locked]*8)["result"], "NO_USABLE_LOCKED_FRAMES")

    def test_observe_checks_state_even_after_failed_camera_capture(self):
        sample = observe(FakeCamera(ok=False), lambda: SessionState.LOCKED, 4)
        self.assertEqual(sample.session, "locked")
        self.assertFalse(sample.capture_ok)
        self.assertEqual(sample.error, "camera_read_failed")

    def test_observe_accepts_injected_statistics_without_opencv_camera(self):
        sample = observe(FakeCamera(), lambda: SessionState.LOCKED, 3,
                         stats_fn=lambda _: ((1280, 720),(110, 28)))
        self.assertTrue(sample.frame_nonuniform)
        self.assertEqual(sample.width, 1280)

    def test_unknown_wts_is_explicit(self):
        def failed_state():
            raise RuntimeError("wts error")
        sample = observe(FakeCamera(), failed_state, 0,
                         stats_fn=lambda _: ((1,1),(12,30)))
        self.assertEqual(sample.session, "unknown")
        self.assertEqual(summarize([sample]*9)["result"], "INCONCLUSIVE")

    def test_csv_is_flushed_and_contains_no_video_data(self):
        class Clock:
            time = 0.0
            def now(self): return self.time
            def sleep(self, d): self.time += max(0.01, d)
        with TemporaryDirectory() as tmp:
            output = Path(tmp)/"probe.csv"
            c = Clock()
            sample = assess_sample(1, SessionState.LOCKED, True, (640,480),(100,14))
            report = run_probe(FakeCamera(), output, duration=5, interval=1,
                               session_fn=lambda: SessionState.LOCKED,
                               now=c.now, wait=c.sleep,
                               sample_fn=lambda *args: sample)
            self.assertEqual(report["result"], "CAMERA_READS_DURING_LOCK")
            data = output.read_text()
            self.assertIn("frame_nonuniform",data)
            self.assertNotIn("base64",data)
            self.assertEqual(len(data.splitlines()), 6)

    def test_bad_interval_rejected(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                run_probe(FakeCamera(), Path(tmp)/"bad.csv", duration=30, interval=0)


if __name__ == "__main__":
    unittest.main()
