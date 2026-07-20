"""Tests for exercise logic — ExerciseTracker, angle smoothing, stability."""

import sys
import unittest
from unittest.mock import patch, MagicMock
from collections import deque
import numpy as np

# camera4.py calls parser.parse_args() at module level — provide dummy args.
sys.argv = ["test_exercise.py", "--username", "test_user"]

from camera4 import ExerciseTracker, format_daily_logs_text, save_exercise_log


class TestExerciseTrackerInitialization(unittest.TestCase):
    def test_default_smoothing(self):
        t = ExerciseTracker()
        self.assertEqual(t.smoothing, 0.6)

    def test_custom_smoothing(self):
        t = ExerciseTracker(smoothing=0.8)
        self.assertEqual(t.smoothing, 0.8)

    def test_initial_state_empty(self):
        t = ExerciseTracker()
        self.assertEqual(t.prev_angles, {})
        self.assertEqual(t.stability, {})
        self.assertEqual(t.current_lmlist, [])
        self.assertEqual(t.img_h, 0)
        self.assertEqual(t.img_w, 0)


class TestTrackLandmarkVisibility(unittest.TestCase):
    def setUp(self):
        self.tracker = ExerciseTracker()
        # Fake image: 480x640
        self.tracker.img_h = 480
        self.tracker.img_w = 640
        self.tracker.current_lmlist = [
            [0, 320, 240],   # nose — center of frame
            [1, 100, 50],    # left eye — within bounds
            [2, -10, 50],    # out of bounds (x < 0)
            [3, 700, 50],    # out of bounds (x >= 640)
        ]

    def test_visible_landmark(self):
        self.assertTrue(self.tracker._is_landmark_visible(0))

    def test_negative_x_not_visible(self):
        self.assertFalse(self.tracker._is_landmark_visible(2))

    def test_beyond_width_not_visible(self):
        self.assertFalse(self.tracker._is_landmark_visible(3))

    def test_out_of_range_index_not_visible(self):
        self.assertFalse(self.tracker._is_landmark_visible(99))

    def test_empty_lmlist_not_visible(self):
        self.tracker.current_lmlist = []
        self.assertFalse(self.tracker._is_landmark_visible(0))


class TestHasVisibleLandmarks(unittest.TestCase):
    def setUp(self):
        self.tracker = ExerciseTracker()
        self.tracker.img_h = 480
        self.tracker.img_w = 640
        self.tracker.current_lmlist = [
            [0, 320, 240],
            [1, 100, 50],
            [2, -10, 50],
        ]

    def test_all_visible(self):
        self.assertTrue(self.tracker.has_visible_landmarks(0, 1))

    def test_one_invisible(self):
        self.assertFalse(self.tracker.has_visible_landmarks(0, 2))

    def test_all_invisible(self):
        self.assertFalse(self.tracker.has_visible_landmarks(2))

    def test_no_arguments_returns_true(self):
        self.assertTrue(self.tracker.has_visible_landmarks())


class TestSmoothAngle(unittest.TestCase):
    def setUp(self):
        self.tracker = ExerciseTracker(smoothing=0.6)

    def test_first_call_returns_raw(self):
        result = self.tracker._smooth_angle("test", 90.0)
        self.assertEqual(result, 90.0)

    def test_second_call_applies_smoothing(self):
        self.tracker._smooth_angle("test", 90.0)
        # 0.6 * 100 + 0.4 * 90 = 60 + 36 = 96
        result = self.tracker._smooth_angle("test", 100.0)
        self.assertEqual(result, 96.0)

    def test_multiple_calls_converge(self):
        self.tracker._smooth_angle("test", 0.0)
        self.tracker._smooth_angle("test", 0.0)
        self.tracker._smooth_angle("test", 0.0)
        result = self.tracker._smooth_angle("test", 0.0)
        self.assertEqual(result, 0.0)

    def test_different_keys_independent(self):
        self.tracker._smooth_angle("a", 90.0)
        self.tracker._smooth_angle("b", 10.0)
        result_a = self.tracker._smooth_angle("a", 100.0)  # 0.6*100+0.4*90 = 96
        result_b = self.tracker._smooth_angle("b", 20.0)   # 0.6*20+0.4*10 = 16
        self.assertEqual(result_a, 96.0)
        self.assertEqual(result_b, 16.0)

    def test_smoothing_factor_affects_weight(self):
        t = ExerciseTracker(smoothing=0.9)
        t._smooth_angle("x", 100.0)
        result = t._smooth_angle("x", 200.0)  # 0.9*200 + 0.1*100 = 180 + 10 = 190
        self.assertEqual(result, 190.0)


class TestIsStable(unittest.TestCase):
    def setUp(self):
        self.tracker = ExerciseTracker()

    def test_insufficient_frames_not_stable(self):
        self.tracker.is_stable("test", True, window=5)
        self.tracker.is_stable("test", True, window=5)
        result = self.tracker.is_stable("test", False, window=5)
        self.assertFalse(result)

    def test_all_true_fills_window(self):
        result = None
        for _ in range(5):
            result = self.tracker.is_stable("test", True, window=5)
        self.assertTrue(result)

    def test_false_breaks_stability(self):
        for _ in range(3):
            self.tracker.is_stable("test", True, window=5)
        self.tracker.is_stable("test", False, window=5)
        for _ in range(2):
            self.tracker.is_stable("test", True, window=5)
        # The deque has [True, False, True, True, True] — not all True
        result = self.tracker.is_stable("test", True, window=5)
        self.assertFalse(result)

    def test_different_keys_independent(self):
        for _ in range(5):
            self.tracker.is_stable("a", True, window=5)
            self.tracker.is_stable("b", False, window=5)
        self.assertTrue(self.tracker.is_stable("a", True, window=5))
        self.assertFalse(self.tracker.is_stable("b", False, window=5))

    def test_custom_window_size(self):
        for _ in range(3):
            self.tracker.is_stable("x", True, window=3)
        self.assertTrue(self.tracker.is_stable("x", True, window=3))


class TestUpdateLandmarks(unittest.TestCase):
    def test_updates_lmlist_and_dims(self):
        tracker = ExerciseTracker()
        fake_img = np.zeros((480, 640, 3), dtype=np.uint8)
        fake_lmlist = [[0, 100, 200], [1, 300, 400]]
        tracker.update_landmarks(fake_lmlist, fake_img)
        self.assertEqual(tracker.current_lmlist, fake_lmlist)
        self.assertEqual(tracker.img_h, 480)
        self.assertEqual(tracker.img_w, 640)


class TestFormatDailyLogsText(unittest.TestCase):
    @patch("camera4.is_registered_user", return_value=True)
    @patch("camera4.get_daily_logs")
    @patch("camera4.calculate_daily_exercise_report")
    def test_formats_exercise_logs(self, mock_report, mock_get_logs, mock_reg):
        mock_get_logs.return_value = [
            ("Push-up", 20, "reps"),
            ("Plank", 30, "seconds"),
        ]
        mock_report.return_value = {
            "exercise_breakdown": [
                {"exercise_name": "Push-up", "calories": 25.5, "status": "ok"},
                {"exercise_name": "Plank", "calories": 8.2, "status": "ok"},
            ],
            "total_exercise_kcal": 33.7,
        }
        text = format_daily_logs_text("alice")
        self.assertIn("Bugun", text)
        self.assertIn("Push-up", text)
        self.assertIn("Plank", text)
        self.assertIn("25.5 kcal", text)

    @patch("camera4.is_registered_user", return_value=True)
    @patch("camera4.get_daily_logs")
    def test_no_logs_today(self, mock_get_logs, mock_reg):
        mock_get_logs.return_value = []
        text = format_daily_logs_text("alice")
        self.assertIn("kayit yok", text)

    @patch("camera4.is_registered_user", return_value=False)
    def test_unregistered_user(self, mock_reg):
        text = format_daily_logs_text("unknown")
        self.assertIn("kayitli degil", text)


class TestSaveExerciseLog(unittest.TestCase):
    def setUp(self):
        self.reg_patcher = patch("camera4.is_registered_user", return_value=True)
        self.reg_patcher.start()

    def tearDown(self):
        self.reg_patcher.stop()

    def test_saves_exercise(self):
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        with patch("camera4.sqlite3.connect", return_value=mock_conn):
            save_exercise_log("alice", "Push-up", 15, "reps")
        mock_cursor.execute.assert_called_once()
        call_sql = mock_cursor.execute.call_args[0][0]
        self.assertIn("INSERT INTO exercise_daily_logs", call_sql)

    def test_unregistered_user_raises(self):
        with patch("camera4.is_registered_user", return_value=False):
            with self.assertRaises(ValueError):
                save_exercise_log("unknown", "Push-up", 10, "reps")


if __name__ == "__main__":
    unittest.main()
