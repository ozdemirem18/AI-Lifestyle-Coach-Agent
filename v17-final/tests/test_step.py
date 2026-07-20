import sqlite3
import unittest
from unittest.mock import patch
from datetime import date

from step import step_f


class TestIsRegisteredUser(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE)"
        )
        self.conn.execute("INSERT INTO users (username) VALUES ('alice')")
        self.patcher = patch("step.step_f.sqlite3.connect", return_value=self.conn)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.conn.close()

    def test_registered_returns_true(self):
        self.assertTrue(step_f.is_registered_user("alice"))

    def test_unregistered_returns_false(self):
        self.assertFalse(step_f.is_registered_user("bob"))

    def test_none_returns_false(self):
        self.assertFalse(step_f.is_registered_user(None))


class TestCalculateStepCalories(unittest.TestCase):
    def test_zero_steps_returns_zero(self):
        result = step_f._calculate_step_calories(0, 70)
        self.assertEqual(result, 0.0)

    def test_zero_weight_returns_zero(self):
        result = step_f._calculate_step_calories(10000, 0)
        self.assertEqual(result, 0.0)

    def test_negative_steps_returns_zero(self):
        result = step_f._calculate_step_calories(-100, 70)
        self.assertEqual(result, 0.0)

    def test_none_weight_returns_zero(self):
        result = step_f._calculate_step_calories(10000, None)
        self.assertEqual(result, 0.0)

    def test_calculation_formula(self):
        steps = 7000
        weight = 70.0
        # MET 3.0 * 70 kg * (7000 / 7000) = 210.0
        result = step_f._calculate_step_calories(steps, weight)
        self.assertEqual(result, 210.0)

    def test_partial_hour(self):
        steps = 3500
        weight = 70.0
        # MET 3.0 * 70 * (3500/7000) = 105.0
        result = step_f._calculate_step_calories(steps, weight)
        self.assertEqual(result, 105.0)

    def test_different_weight(self):
        steps = 7000
        weight = 80.0
        # MET 3.0 * 80 * (7000/7000) = 240.0
        result = step_f._calculate_step_calories(steps, weight)
        self.assertEqual(result, 240.0)

    def test_floating_point_weight(self):
        steps = 10000
        weight = 72.5
        expected = round(3.0 * 72.5 * (10000 / 7000.0), 1)
        result = step_f._calculate_step_calories(steps, weight)
        self.assertEqual(result, expected)


class TestGetWeightKg(unittest.TestCase):
    """Tests for the internal _get_weight_kg helper."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE users (username TEXT PRIMARY KEY, password_hash TEXT, weight_kg REAL)"
        )
        self.patcher = patch("step.step_f.sqlite3.connect", return_value=self.conn)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.conn.close()

    def test_returns_weight(self):
        self.conn.execute(
            "INSERT INTO users (username, password_hash, weight_kg) VALUES (?, ?, ?)",
            ("alice", "h", 65.0),
        )
        result = step_f._get_weight_kg("alice")
        self.assertEqual(result, 65.0)

    def test_returns_none_if_no_weight(self):
        self.conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("bob", "h"),
        )
        result = step_f._get_weight_kg("bob")
        self.assertIsNone(result)

    def test_returns_none_for_missing_user(self):
        result = step_f._get_weight_kg("nobody")
        self.assertIsNone(result)


class TestSetupDatabase(unittest.TestCase):
    def setUp(self):
        self._makedirs_patch = patch("step.step_f.os.makedirs")
        self._makedirs_patch.start()

    def tearDown(self):
        self._makedirs_patch.stop()

    def _patch_conn(self):
        conn = sqlite3.connect(":memory:")
        patcher = patch("step.step_f.sqlite3.connect", return_value=conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(conn.close)
        return conn

    def test_creates_step_records_table(self):
        conn = self._patch_conn()
        step_f.setup_database()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='step_records'"
        )
        self.assertIsNotNone(cursor.fetchone())

    def test_table_has_expected_columns(self):
        conn = self._patch_conn()
        step_f.setup_database()
        columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(step_records)").fetchall()
        }
        self.assertIn("id", columns)
        self.assertIn("username", columns)
        self.assertIn("record_date", columns)
        self.assertIn("steps", columns)
        self.assertEqual(columns["steps"].upper(), "INTEGER")

    def test_is_idempotent(self):
        conn = self._patch_conn()
        step_f.setup_database()
        step_f.setup_database()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='step_records'"
        ).fetchall()
        self.assertEqual(len(tables), 1)


class TestDatabaseOperations(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE step_records ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  username TEXT NOT NULL DEFAULT 'legacy',"
            "  record_date TEXT NOT NULL,"
            "  steps INTEGER NOT NULL"
            ")"
        )

    def test_insert_and_sum_daily(self):
        today = str(date.today())
        self.conn.execute(
            "INSERT INTO step_records (username, record_date, steps) VALUES (?, ?, ?)",
            ("testuser", today, 3000),
        )
        self.conn.execute(
            "INSERT INTO step_records (username, record_date, steps) VALUES (?, ?, ?)",
            ("testuser", today, 5000),
        )
        row = self.conn.execute(
            "SELECT COALESCE(SUM(steps), 0) FROM step_records"
            " WHERE username = ? AND record_date = ?",
            ("testuser", today),
        ).fetchone()
        self.assertEqual(row[0], 8000)

    def test_sum_empty_returns_zero(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(steps), 0) FROM step_records"
            " WHERE username = ? AND record_date = ?",
            ("nobody", "2099-01-01"),
        ).fetchone()
        self.assertEqual(row[0], 0)

    def test_delete_record(self):
        today = str(date.today())
        cur = self.conn.execute(
            "INSERT INTO step_records (username, record_date, steps) VALUES (?, ?, ?)",
            ("testuser", today, 5000),
        )
        rid = cur.lastrowid
        self.conn.execute("DELETE FROM step_records WHERE id = ?", (rid,))
        remaining = self.conn.execute(
            "SELECT COUNT(*) FROM step_records WHERE username = ?",
            ("testuser",),
        ).fetchone()[0]
        self.assertEqual(remaining, 0)


class TestStartGuiValidation(unittest.TestCase):
    @patch("step.step_f.messagebox.showerror")
    @patch("step.step_f.is_registered_user", return_value=False)
    def test_unregistered_shows_error(self, mock_check, mock_showerror):
        step_f.start_gui("unknown_user")
        mock_showerror.assert_called_once()
        args = mock_showerror.call_args[0]
        self.assertIn("not registered", args[1])

    @patch("step.step_f.is_registered_user", return_value=False)
    def test_unregistered_does_not_open_gui(self, mock_check):
        with patch("step.step_f.setup_database") as mock_setup:
            step_f.start_gui("unknown_user")
            mock_setup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
