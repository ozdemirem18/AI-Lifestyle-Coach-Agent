"""Tests for the spor_calorie_f module (exercise calorie calculations)."""

import sqlite3
import unittest
from unittest.mock import patch
from datetime import date

from calorie import spor_calorie_f


class TestNormalizeExerciseName(unittest.TestCase):
    def test_lowercases(self):
        result = spor_calorie_f._normalize_exercise_name("Push-Up")
        self.assertEqual(result, "push_up")

    def test_replaces_hyphens(self):
        result = spor_calorie_f._normalize_exercise_name("arm-raise")
        self.assertEqual(result, "arm_raise")

    def test_replaces_spaces(self):
        result = spor_calorie_f._normalize_exercise_name("arm raise")
        self.assertEqual(result, "arm_raise")

    def test_strips_whitespace(self):
        result = spor_calorie_f._normalize_exercise_name("  Plank  ")
        self.assertEqual(result, "plank")

    def test_already_normalized(self):
        result = spor_calorie_f._normalize_exercise_name("push_up")
        self.assertEqual(result, "push_up")


class TestAmountToHours(unittest.TestCase):
    def test_hours_direct(self):
        result = spor_calorie_f._amount_to_hours(2, "hours")
        self.assertEqual(result, 2.0)

    def test_minutes_conversion(self):
        result = spor_calorie_f._amount_to_hours(60, "min")
        self.assertEqual(result, 1.0)

    def test_seconds_conversion(self):
        result = spor_calorie_f._amount_to_hours(3600, "seconds")
        self.assertEqual(result, 1.0)

    def test_reps_with_known_exercise(self):
        # pushup: 2.2 sec/rep -> 10 * 2.2 / 3600
        result = spor_calorie_f._amount_to_hours(10, "reps", exercise_name="push_up")
        expected = (10 * 2.2) / 3600.0
        self.assertAlmostEqual(result, expected)

    def test_reps_unknown_exercise_defaults_to_2_5_sec(self):
        result = spor_calorie_f._amount_to_hours(10, "reps", exercise_name="unknown_exercise")
        expected = (10 * 2.5) / 3600.0
        self.assertAlmostEqual(result, expected)

    def test_turkish_units(self):
        result = spor_calorie_f._amount_to_hours(30, "dk")
        self.assertAlmostEqual(result, 0.5)

        result2 = spor_calorie_f._amount_to_hours(7200, "sn")
        self.assertAlmostEqual(result2, 2.0)

        result3 = spor_calorie_f._amount_to_hours(50, "tekrar")
        self.assertAlmostEqual(result3, (50 * 2.5) / 3600.0)

    def test_unknown_unit_falls_back_to_minutes(self):
        result = spor_calorie_f._amount_to_hours(120, "unknown_unit")
        self.assertEqual(result, 2.0)

    def test_zero_amount(self):
        result = spor_calorie_f._amount_to_hours(0, "minutes")
        self.assertEqual(result, 0.0)


class TestCalculateExerciseCalorie(unittest.TestCase):
    def test_basic_calculation(self):
        # MET 5.0 * 70 kg * 1 hour = 350
        result = spor_calorie_f.calculate_exercise_calorie(5.0, 70.0, 1.0)
        self.assertEqual(result, 350.0)

    def test_half_hour(self):
        result = spor_calorie_f.calculate_exercise_calorie(8.0, 70.0, 0.5)
        self.assertEqual(result, 280.0)

    def test_zero_duration(self):
        result = spor_calorie_f.calculate_exercise_calorie(5.0, 70.0, 0.0)
        self.assertEqual(result, 0.0)


class TestCalculateStepsCalorie(unittest.TestCase):
    def test_7000_steps_one_hour_walking(self):
        # MET 3.0 * 70 * (7000/7000) = 210
        result = spor_calorie_f.calculate_steps_calorie(7000, 70.0)
        self.assertEqual(result, 210.0)

    def test_zero_steps(self):
        result = spor_calorie_f.calculate_steps_calorie(0, 70.0)
        self.assertEqual(result, 0.0)


class TestCalculateBMR(unittest.TestCase):
    def test_male_using_mifflin_st_jeor(self):
        # (10 * 70) + (6.25 * 170) - (5 * 30) + 5 = 700 + 1062.5 - 150 + 5 = 1617.5
        result = spor_calorie_f.calculate_bmr(70, 170, 30, "Male")
        self.assertEqual(result, 1617.5)

    def test_female_using_mifflin_st_jeor(self):
        # (10 * 60) + (6.25 * 160) - (5 * 25) - 161 = 600 + 1000 - 125 - 161 = 1314
        result = spor_calorie_f.calculate_bmr(60, 160, 25, "Female")
        self.assertEqual(result, 1314.0)

    def test_turkish_gender_labels(self):
        result_m = spor_calorie_f.calculate_bmr(70, 170, 30, "Erkek")
        self.assertEqual(result_m, 1617.5)
        result_f = spor_calorie_f.calculate_bmr(60, 160, 25, "Kadın")
        self.assertEqual(result_f, 1314.0)

    def test_other_gender_averages(self):
        # (10*70)+(6.25*170)-(5*30)-78 = 700+1062.5-150-78 = 1534.5
        result = spor_calorie_f.calculate_bmr(70, 170, 30, "Other")
        self.assertEqual(result, 1534.5)

    def test_shorthand_gender(self):
        result = spor_calorie_f.calculate_bmr(70, 170, 30, "m")
        self.assertEqual(result, 1617.5)
        result2 = spor_calorie_f.calculate_bmr(60, 160, 25, "f")
        self.assertEqual(result2, 1314.0)


class TestMETValues(unittest.TestCase):
    """Verify that expected exercises have MET values defined."""

    def test_key_exercises_have_met(self):
        exercises = ["squat", "push_up", "plank", "march", "jump"]
        for ex in exercises:
            with self.subTest(exercise=ex):
                self.assertIn(ex, spor_calorie_f.EXERCISE_MET)
                self.assertGreater(spor_calorie_f.EXERCISE_MET[ex], 0)


class TestGetExerciseLogs(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE exercise_daily_logs ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  username TEXT NOT NULL,"
            "  exercise_name TEXT NOT NULL,"
            "  log_date TEXT NOT NULL,"
            "  total_amount REAL NOT NULL,"
            "  unit TEXT NOT NULL,"
            "  created_at TEXT,"
            "  updated_at TEXT"
            ")"
        )
        self.conn.execute(
            "INSERT INTO exercise_daily_logs (username, exercise_name, log_date, total_amount, unit) "
            "VALUES (?, ?, ?, ?, ?)",
            ("alice", "push_up", "2025-01-15", 20, "reps"),
        )
        self.patcher = patch("calorie.spor_calorie_f.sqlite3.connect", return_value=self.conn)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.conn.close()

    def test_returns_logs_for_user_and_date(self):
        logs = spor_calorie_f.get_exercise_logs("alice", "2025-01-15")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["exercise_name"], "push_up")
        self.assertEqual(logs[0]["total_amount"], 20)

    def test_empty_for_no_logs(self):
        logs = spor_calorie_f.get_exercise_logs("alice", "2099-01-01")
        self.assertEqual(logs, [])


class TestGetUserInfo(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE users ("
            "  username TEXT PRIMARY KEY, password_hash TEXT,"
            "  age INTEGER, height_cm REAL, weight_kg REAL, gender TEXT"
            ")"
        )
        self.conn.execute(
            "INSERT INTO users (username, password_hash, age, height_cm, weight_kg, gender) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("alice", "h", 30, 170, 65, "Female"),
        )
        self.patcher = patch("calorie.spor_calorie_f.sqlite3.connect", return_value=self.conn)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.conn.close()

    def test_returns_user_info(self):
        info = spor_calorie_f.get_user_info("alice")
        self.assertEqual(info["age"], 30)
        self.assertEqual(info["height_cm"], 170)
        self.assertEqual(info["weight_kg"], 65)
        self.assertEqual(info["gender"], "Female")

    def test_missing_user_raises(self):
        with self.assertRaises(ValueError):
            spor_calorie_f.get_user_info("nobody")

    def test_missing_weight_raises(self):
        self.conn.execute(
            "UPDATE users SET weight_kg = NULL WHERE username = ?", ("alice",),
        )
        with self.assertRaises(ValueError):
            spor_calorie_f.get_user_info("alice")


class TestCalculateDailyExerciseReport(unittest.TestCase):
    def setUp(self):
        self.spor_conn = sqlite3.connect(":memory:")
        self.spor_conn.execute(
            "CREATE TABLE exercise_daily_logs ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  username TEXT NOT NULL,"
            "  exercise_name TEXT NOT NULL,"
            "  log_date TEXT NOT NULL,"
            "  total_amount REAL NOT NULL,"
            "  unit TEXT NOT NULL,"
            "  created_at TEXT,"
            "  updated_at TEXT"
            ")"
        )
        self.spor_conn.execute(
            "INSERT INTO exercise_daily_logs (username, exercise_name, log_date, total_amount, unit) "
            "VALUES (?, ?, ?, ?, ?)",
            ("alice", "Push-up", "2025-01-15", 30, "reps"),
        )
        self.user_conn = sqlite3.connect(":memory:")
        self.user_conn.execute(
            "CREATE TABLE users ("
            "  username TEXT PRIMARY KEY, password_hash TEXT,"
            "  age INTEGER, height_cm REAL, weight_kg REAL, gender TEXT"
            ")"
        )
        self.user_conn.execute(
            "INSERT INTO users (username, password_hash, age, height_cm, weight_kg, gender) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("alice", "h", 30, 170, 70, "Male"),
        )
        self.user_patcher = patch("calorie.spor_calorie_f.sqlite3.connect", side_effect=self._connect)
        self.user_patcher.start()

    def _connect(self, path):
        if "spor" in str(path):
            return self.spor_conn
        if "user" in str(path):
            return self.user_conn
        raise ValueError(f"Unexpected path: {path}")

    def tearDown(self):
        self.user_patcher.stop()
        self.spor_conn.close()
        self.user_conn.close()

    def test_returns_report_with_exercise_breakdown(self):
        report = spor_calorie_f.calculate_daily_exercise_report("alice", "2025-01-15")
        self.assertEqual(report["username"], "alice")
        self.assertIn("exercise_breakdown", report)
        self.assertIn("total_exercise_kcal", report)
        self.assertIn("bmr_kcal_per_day", report)
        self.assertGreater(len(report["exercise_breakdown"]), 0)

    def test_exercise_calorie_non_zero(self):
        report = spor_calorie_f.calculate_daily_exercise_report("alice", "2025-01-15")
        self.assertGreater(report["total_exercise_kcal"], 0)

    def test_bmr_is_calculated(self):
        report = spor_calorie_f.calculate_daily_exercise_report("alice", "2025-01-15")
        # Male, 70kg, 170cm, 30y: (10*70)+(6.25*170)-(5*30)+5 = 1617.5
        self.assertAlmostEqual(report["bmr_kcal_per_day"], 1617.5)


class TestSaveDailyExerciseReport(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.patcher = patch("calorie.spor_calorie_f.sqlite3.connect", return_value=self.conn)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.conn.close()

    def test_creates_tables_and_inserts(self):
        report = {
            "username": "alice",
            "log_date": "2025-01-15",
            "exercise_breakdown": [
                {
                    "exercise_name": "Push-up",
                    "met": 8.0,
                    "duration_hours": 0.01833,
                    "calories": 10.26,
                    "status": "ok",
                }
            ],
            "total_exercise_kcal": 10.26,
            "bmr_kcal_per_day": 1617.5,
        }
        spor_calorie_f.save_daily_exercise_report_to_calorie_db(report)
        logs = self.conn.execute(
            "SELECT exercise_name, calories FROM exercise_calorie_logs"
        ).fetchall()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0][0], "Push-up")
        self.assertAlmostEqual(logs[0][1], 10.26)

        summary = self.conn.execute(
            "SELECT total_exercise_kcal, bmr_kcal_per_day FROM exercise_calorie_daily_summary"
        ).fetchall()
        self.assertEqual(len(summary), 1)
        self.assertAlmostEqual(summary[0][0], 10.26)
        self.assertAlmostEqual(summary[0][1], 1617.5)


class TestIsRegisteredUser(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE)"
        )
        self.conn.execute("INSERT INTO users (username) VALUES ('alice')")
        self.patcher = patch("calorie.spor_calorie_f.sqlite3.connect", return_value=self.conn)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.conn.close()

    def test_registered_returns_true(self):
        self.assertTrue(spor_calorie_f.is_registered_user("alice"))

    def test_unregistered_returns_false(self):
        self.assertFalse(spor_calorie_f.is_registered_user("bob"))


class TestDailyReportValidation(unittest.TestCase):
    def test_unregistered_user_raises(self):
        with patch("calorie.spor_calorie_f.is_registered_user", return_value=False):
            with self.assertRaises(ValueError):
                spor_calorie_f.calculate_daily_exercise_report("nobody")


if __name__ == "__main__":
    unittest.main()
