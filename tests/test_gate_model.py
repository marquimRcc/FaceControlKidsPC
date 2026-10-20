import unittest

from facekids.gate_model import GateModel, GateState


class GateModelTest(unittest.TestCase):
    def test_starts_restricted_and_requires_two_matches(self):
        model = GateModel()
        self.assertEqual(model.state, GateState.WAITING)
        self.assertTrue(model.gate_visible)
        self.assertEqual(model.observe(1, 0), GateState.VERIFYING)
        self.assertEqual(model.observe(1, 5), GateState.OPEN)
        self.assertFalse(model.gate_visible)

    def test_charges_only_active_child(self):
        model = GateModel()
        model.observe(1, 0)
        model.observe(1, 5)
        model.advance(65)
        self.assertEqual(model.remaining[1], 7140)
        self.assertEqual(model.remaining[2], 7200)

    def test_absence_pauses_immediately_then_shows_gate(self):
        model = GateModel()
        model.observe(1, 0)
        model.observe(1, 5)
        model.observe(None, 10)
        self.assertEqual(model.remaining[1], 7195)
        model.advance(20)
        self.assertEqual(model.remaining[1], 7195)
        self.assertEqual(model.state, GateState.OPEN)
        model.advance(25)
        self.assertEqual(model.state, GateState.WAITING)
        self.assertTrue(model.gate_visible)

    def test_return_during_away_grace(self):
        model = GateModel()
        model.observe(1, 0)
        model.observe(1, 5)
        model.observe(None, 10)
        self.assertEqual(model.observe(1, 18), GateState.OPEN)
        model.advance(23)
        self.assertEqual(model.remaining[1], 7190)

    def test_different_child_requires_reconfirmation(self):
        model = GateModel()
        model.observe(1, 0)
        model.observe(1, 5)
        self.assertEqual(model.observe(2, 10), GateState.VERIFYING)
        self.assertTrue(model.gate_visible)
        self.assertEqual(model.observe(2, 15), GateState.OPEN)
        model.advance(20)
        self.assertEqual(model.remaining[1], 7195)
        self.assertEqual(model.remaining[2], 7195)

    def test_exhaustion_and_second_child_allowed(self):
        model = GateModel(daily_seconds=20)
        model.observe(1, 0)
        model.observe(1, 5)
        model.advance(25)
        self.assertEqual(model.state, GateState.DENIED)
        self.assertEqual(model.remaining[1], 0)
        self.assertEqual(model.observe(1, 30), GateState.VERIFYING)
        self.assertEqual(model.observe(1, 35), GateState.DENIED)
        self.assertEqual(model.observe(2, 40), GateState.VERIFYING)
        self.assertEqual(model.observe(2, 45), GateState.OPEN)

    def test_unknown_and_multiple_restrict_immediately(self):
        for observation, expected in [("unknown", GateState.UNKNOWN),
                                      ("multiple", GateState.MULTIPLE)]:
            with self.subTest(observation=observation):
                model = GateModel()
                model.observe(1, 0)
                model.observe(1, 5)
                self.assertEqual(model.observe(observation, 10), expected)
                self.assertTrue(model.gate_visible)
                model.advance(60)
                self.assertEqual(model.remaining[1], 7195)

    def test_errors_require_fresh_face_confirmation(self):
        model = GateModel()
        model.observe(1, 0)
        model.observe(1, 5)
        self.assertEqual(model.observe("camera_error", 10), GateState.CAMERA_ERROR)
        self.assertEqual(model.observe(1, 15), GateState.VERIFYING)
        self.assertEqual(model.observe("service_error", 20), GateState.SERVICE_ERROR)
        self.assertEqual(model.observe(1, 25), GateState.VERIFYING)
        self.assertEqual(model.observe(1, 30), GateState.OPEN)

    def test_no_face_before_authorization_never_unlocks(self):
        model = GateModel()
        model.observe(None, 0)
        model.advance(100)
        self.assertEqual(model.state, GateState.WAITING)
        self.assertEqual(model.remaining[1], 7200)

    def test_reject_invalid_observations_and_backwards_time(self):
        model = GateModel()
        with self.assertRaises(ValueError):
            model.observe("unsupported", 0)
        with self.assertRaises(ValueError):
            model.observe(True, 0)
        model.advance(10)
        with self.assertRaises(ValueError):
            model.advance(9)
        with self.assertRaises(ValueError):
            model.fast_forward(-1, 10)


if __name__ == "__main__":
    unittest.main()
