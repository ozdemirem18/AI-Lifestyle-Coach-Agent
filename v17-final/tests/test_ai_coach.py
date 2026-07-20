"""Tests for the AI Coach module — rule-based report generation."""

import sqlite3
import unittest
from unittest.mock import patch

from ai_coach import ai_coach

_real_connect = sqlite3.connect


class TestHasProfile(unittest.TestCase):
    def test_complete_profile_returns_true(self):
        profile = {"age": 30, "height_cm": 170, "weight_kg": 70}
        self.assertTrue(ai_coach._has_profile(profile))

    def test_missing_age_returns_false(self):
        profile = {"age": None, "height_cm": 170, "weight_kg": 70}
        self.assertFalse(ai_coach._has_profile(profile))

    def test_missing_height_returns_false(self):
        profile = {"age": 30, "height_cm": None, "weight_kg": 70}
        self.assertFalse(ai_coach._has_profile(profile))

    def test_missing_weight_returns_false(self):
        profile = {"age": 30, "height_cm": 170, "weight_kg": None}
        self.assertFalse(ai_coach._has_profile(profile))

    def test_all_none_returns_false(self):
        profile = {"age": None, "height_cm": None, "weight_kg": None}
        self.assertFalse(ai_coach._has_profile(profile))

    def test_empty_dict_returns_false(self):
        self.assertFalse(ai_coach._has_profile({}))


class TestCollectUserData(unittest.TestCase):
    """Tests for collect_user_data — the data aggregation layer."""

    def setUp(self):
        self.user_conn = sqlite3.connect(":memory:")
        self.user_conn.execute(
            "CREATE TABLE users ("
            "  username TEXT PRIMARY KEY, age INTEGER, height_cm REAL,"
            "  weight_kg REAL, bmi REAL, ideal_weight_min REAL,"
            "  ideal_weight_max REAL, target_weight_kg REAL,"
            "  gender TEXT, daily_calorie_goal REAL"
            ")"
        )
        self.user_conn.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("alice", 30, 170, 65, 22.5, 53.5, 72.0, 68.0, "Female", 2000),
        )

        self.spor_conn = sqlite3.connect(":memory:")
        self.spor_conn.execute(
            "CREATE TABLE exercise_daily_logs ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  username TEXT, exercise_name TEXT,"
            "  log_date TEXT, total_amount REAL, unit TEXT"
            ")"
        )

        self.calorie_conn = sqlite3.connect(":memory:")
        self.calorie_conn.execute(
            "CREATE TABLE daily_records ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  username TEXT, record_date TEXT, food_name TEXT,"
            "  weight_grams REAL, calories REAL"
            ")"
        )
        self.calorie_conn.execute(
            "CREATE TABLE exercise_calorie_logs ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  username TEXT, log_date TEXT, exercise_name TEXT,"
            "  met REAL, duration_hours REAL,"
            "  calories REAL, status TEXT, updated_at TEXT"
            ")"
        )
        self.calorie_conn.execute(
            "CREATE TABLE exercise_calorie_daily_summary ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  username TEXT, log_date TEXT,"
            "  total_exercise_kcal REAL, bmr_kcal_per_day REAL, updated_at TEXT"
            ")"
        )

        self.sleep_conn = sqlite3.connect(":memory:")
        self.sleep_conn.execute(
            "CREATE TABLE sleep_records ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  username TEXT, record_date TEXT, sleep_hours REAL"
            ")"
        )

        self.water_conn = sqlite3.connect(":memory:")
        self.water_conn.execute(
            "CREATE TABLE water_records ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  username TEXT, record_date TEXT, water_ml REAL"
            ")"
        )

        self.step_conn = sqlite3.connect(":memory:")
        self.step_conn.execute(
            "CREATE TABLE step_records ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  username TEXT, record_date TEXT, steps INTEGER"
            ")"
        )

        def mock_connect(path):
            mapping = {
                str(ai_coach.USER_DB): self.user_conn,
                str(ai_coach.SPOR_DB): self.spor_conn,
                str(ai_coach.CALORIE_DB): self.calorie_conn,
                str(ai_coach.SLEEP_DB): self.sleep_conn,
                str(ai_coach.WATER_DB): self.water_conn,
                str(ai_coach.STEP_DB): self.step_conn,
            }
            key = str(path)
            if key in mapping:
                return mapping[key]
            return _real_connect(":memory:")

        self.patcher = patch("ai_coach.ai_coach.sqlite3.connect", side_effect=mock_connect)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        for c in [self.user_conn, self.spor_conn, self.calorie_conn,
                  self.sleep_conn, self.water_conn, self.step_conn]:
            c.close()

    def test_collects_profile_data(self):
        data = ai_coach.collect_user_data("alice")
        self.assertEqual(data["profile"]["age"], 30)
        self.assertEqual(data["profile"]["weight_kg"], 65)

    def test_collects_exercise_data(self):
        self.spor_conn.execute(
            "INSERT INTO exercise_daily_logs (username, exercise_name, log_date, total_amount, unit) "
            "VALUES (?, ?, date('now'), ?, ?)",
            ("alice", "push_up", 30, "reps"),
        )
        data = ai_coach.collect_user_data("alice")
        self.assertEqual(len(data["today_exercise"]), 1)
        self.assertEqual(data["today_exercise"][0][0], "push_up")

    def test_collects_empty_data_for_nonexistent_user(self):
        """collect_user_data should return zeros/Nones for missing user."""
        data = ai_coach.collect_user_data("nobody")
        self.assertIsNone(data["profile"]["age"])
        self.assertEqual(data["water_ml"], 0.0)
        self.assertEqual(data["sleep_hours"], 0.0)
        self.assertEqual(data["steps"], 0)
        self.assertEqual(data["calorie_intake"], 0.0)

    def test_collects_sleep_data(self):
        self.sleep_conn.execute(
            "INSERT INTO sleep_records (username, record_date, sleep_hours) "
            "VALUES (?, date('now'), ?)",
            ("alice", 7.5),
        )
        data = ai_coach.collect_user_data("alice")
        self.assertEqual(data["sleep_hours"], 7.5)

    def test_collects_water_data(self):
        self.water_conn.execute(
            "INSERT INTO water_records (username, record_date, water_ml) "
            "VALUES (?, date('now'), ?)",
            ("alice", 1500),
        )
        data = ai_coach.collect_user_data("alice")
        self.assertEqual(data["water_ml"], 1500.0)

    def test_collects_step_data(self):
        self.step_conn.execute(
            "INSERT INTO step_records (username, record_date, steps) "
            "VALUES (?, date('now'), ?)",
            ("alice", 8000),
        )
        data = ai_coach.collect_user_data("alice")
        self.assertEqual(data["steps"], 8000)


class TestGenerateCoachReportIncompleteProfile(unittest.TestCase):
    """When no profile exists, the report should warn the user."""

    def test_generates_warning_for_incomplete_profile(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock_collect:
            mock_collect.return_value = {
                "username": "nobody",
                "date": "2025-01-01",
                "profile": {"age": None, "height_cm": None, "weight_kg": None},
                "today_exercise": [],
                "weekly_exercise": [],
                "weekly_minutes": 0.0,
                "exercise_days": 0,
                "calorie_intake": 0.0,
                "calorie_goal": 2000.0,
                "exercise_kcal": 0.0,
                "bmr": 0.0,
                "sleep_hours": 0.0,
                "water_ml": 0.0,
                "steps": 0,
            }
            report = ai_coach.generate_coach_report("nobody")
            self.assertIn("WARNING", report)
            self.assertIn("Profile incomplete", report)


class TestGenerateCoachReportFullProfile(unittest.TestCase):
    """With a complete profile, the report should include all sections."""

    def _make_data(self, **overrides):
        data = {
            "username": "alice",
            "date": "2025-01-15",
            "profile": {
                "age": 30, "height_cm": 170, "weight_kg": 65,
                "bmi": 22.5, "ideal_weight_min": 53.5,
                "ideal_weight_max": 72.0, "target_weight_kg": 68.0,
                "gender": "Female", "daily_calorie_goal": 2000.0,
            },
            "today_exercise": [],
            "weekly_exercise": [],
            "weekly_minutes": 0.0,
            "exercise_days": 0,
            "calorie_intake": 0.0,
            "calorie_goal": 2000.0,
            "exercise_kcal": 0.0,
            "bmr": 1400.0,
            "sleep_hours": 0.0,
            "water_ml": 0.0,
            "steps": 0,
        }
        data.update(overrides)
        return data

    def test_report_contains_body_metrics(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock_collect:
            mock_collect.return_value = self._make_data()
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("BODY METRICS", report)
            self.assertIn("BMI: 22.5", report)

    def test_report_contains_hydration_section(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock_collect:
            mock_collect.return_value = self._make_data()
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("HYDRATION", report)

    def test_report_contains_sleep_section(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock_collect:
            mock_collect.return_value = self._make_data()
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("SLEEP", report)

    def test_report_contains_steps_section(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock_collect:
            mock_collect.return_value = self._make_data()
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("STEPS", report)

    def test_report_contains_nutrition_section(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock_collect:
            mock_collect.return_value = self._make_data()
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("NUTRITION", report)

    def test_report_contains_exercise_section(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock_collect:
            mock_collect.return_value = self._make_data()
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("EXERCISE", report)

    def test_report_contains_coach_tip(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock_collect:
            mock_collect.return_value = self._make_data()
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("COACH'S TIP", report)

    def test_report_includes_disclaimer(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock_collect:
            mock_collect.return_value = self._make_data()
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("substitute for professional medical guidance", report)


class TestCoachReportBMISections(unittest.TestCase):
    """Verify BMI-specific advice appears at each threshold."""

    def _make_data(self, bmi, weight_kg):
        return {
            "username": "alice", "date": "2025-01-15",
            "profile": {
                "age": 30, "height_cm": 170, "weight_kg": weight_kg,
                "bmi": bmi, "ideal_weight_min": 53.5,
                "ideal_weight_max": 72.0, "target_weight_kg": None,
                "gender": "Female", "daily_calorie_goal": 2000.0,
            },
            "today_exercise": [], "weekly_exercise": [],
            "weekly_minutes": 0.0, "exercise_days": 0,
            "calorie_intake": 0.0, "calorie_goal": 2000.0,
            "exercise_kcal": 0.0, "bmr": 1400.0,
            "sleep_hours": 0.0, "water_ml": 0.0, "steps": 0,
        }

    def test_underweight_bmi(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(17.0, 50)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("Underweight", report)

    def test_healthy_bmi(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(22.0, 65)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("Healthy weight range", report)

    def test_overweight_bmi(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(27.0, 78)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("Overweight", report)

    def test_obese_bmi(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(32.0, 92)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("Obese range", report)


class TestCoachReportHydrationFeedback(unittest.TestCase):
    def _make_data(self, water_ml, weight_kg=65):
        return {
            "username": "alice", "date": "2025-01-15",
            "profile": {
                "age": 30, "height_cm": 170, "weight_kg": weight_kg,
                "bmi": 22.5, "ideal_weight_min": 53.5,
                "ideal_weight_max": 72.0, "target_weight_kg": 68.0,
                "gender": "Female", "daily_calorie_goal": 2000.0,
            },
            "today_exercise": [], "weekly_exercise": [],
            "weekly_minutes": 0.0, "exercise_days": 0,
            "calorie_intake": 0.0, "calorie_goal": 2000.0,
            "exercise_kcal": 0.0, "bmr": 1400.0,
            "sleep_hours": 0.0, "water_ml": water_ml, "steps": 0,
        }

    def test_good_hydration(self):
        # 65 kg * 33 ml/kg = 2145 ml -> 2000 ml is ~93%
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(2000)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("Good hydration", report)

    def test_moderate_hydration(self):
        # 65*33=2145 -> 1500 ml is ~70%
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(1500)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("Drink", report)

    def test_low_hydration(self):
        # 65*33=2145 -> 500 ml is ~23%
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(500)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("Low water intake", report)


class TestCoachReportSleepFeedback(unittest.TestCase):
    def _make_data(self, sleep_hours):
        return {
            "username": "alice", "date": "2025-01-15",
            "profile": {
                "age": 30, "height_cm": 170, "weight_kg": 65,
                "bmi": 22.5, "ideal_weight_min": 53.5,
                "ideal_weight_max": 72.0, "target_weight_kg": 68.0,
                "gender": "Female", "daily_calorie_goal": 2000.0,
            },
            "today_exercise": [], "weekly_exercise": [],
            "weekly_minutes": 0.0, "exercise_days": 0,
            "calorie_intake": 0.0, "calorie_goal": 2000.0,
            "exercise_kcal": 0.0, "bmr": 1400.0,
            "sleep_hours": sleep_hours, "water_ml": 0.0, "steps": 0,
        }

    def test_optimal_sleep(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(8.0)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("sweet spot", report)

    def test_insufficient_sleep(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(5.0)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("short", report)

    def test_excessive_sleep(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(10.0)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("oversleeping", report)

    def test_no_sleep_logged(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(0.0)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("No sleep logged", report)


class TestCoachReportStepsFeedback(unittest.TestCase):
    def _make_data(self, steps, weight_kg=65):
        return {
            "username": "alice", "date": "2025-01-15",
            "profile": {
                "age": 30, "height_cm": 170, "weight_kg": weight_kg,
                "bmi": 22.5, "ideal_weight_min": 53.5,
                "ideal_weight_max": 72.0, "target_weight_kg": 68.0,
                "gender": "Female", "daily_calorie_goal": 2000.0,
            },
            "today_exercise": [], "weekly_exercise": [],
            "weekly_minutes": 0.0, "exercise_days": 0,
            "calorie_intake": 0.0, "calorie_goal": 2000.0,
            "exercise_kcal": 0.0, "bmr": 1400.0,
            "sleep_hours": 8.0, "water_ml": 1500.0, "steps": steps,
        }

    def test_10000_steps_hit_target(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(10000)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("hit 10,000", report)

    def test_7000_steps_close_to_target(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(7000)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("more steps to hit 10k", report)

    def test_few_steps(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(100)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("Low step count", report)

    def test_no_steps_logged(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(0)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("No steps logged", report)


class TestCoachReportCalorieFeedback(unittest.TestCase):
    def _make_data(self, calorie_intake, calorie_goal=2000.0):
        return {
            "username": "alice", "date": "2025-01-15",
            "profile": {
                "age": 30, "height_cm": 170, "weight_kg": 65,
                "bmi": 22.5, "ideal_weight_min": 53.5,
                "ideal_weight_max": 72.0, "target_weight_kg": 68.0,
                "gender": "Female", "daily_calorie_goal": calorie_goal,
            },
            "today_exercise": [], "weekly_exercise": [],
            "weekly_minutes": 0.0, "exercise_days": 0,
            "calorie_intake": calorie_intake,
            "calorie_goal": calorie_goal,
            "exercise_kcal": 0.0, "bmr": 1400.0,
            "sleep_hours": 8.0, "water_ml": 1500.0, "steps": 5000,
        }

    def test_no_food_logged(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(0)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("No food logged", report)

    def test_under_goal(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(1200)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("under your goal", report)

    def test_over_goal(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(2500)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("over your goal", report)

    def test_on_target(self):
        with patch("ai_coach.ai_coach.collect_user_data") as mock:
            mock.return_value = self._make_data(1900)
            report = ai_coach.generate_coach_report("alice")
            self.assertIn("on target", report)


if __name__ == "__main__":
    unittest.main()
