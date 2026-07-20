import sqlite3
import unittest
from unittest.mock import patch
from datetime import date

from calorie import calorie_f


class TestIsRegisteredUser(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE)"
        )
        self.conn.execute("INSERT INTO users (username) VALUES ('alice')")
        self.patcher = patch("calorie.calorie_f.sqlite3.connect", return_value=self.conn)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.conn.close()

    def test_registered_returns_true(self):
        self.assertTrue(calorie_f.is_registered_user("alice"))

    def test_unregistered_returns_false(self):
        self.assertFalse(calorie_f.is_registered_user("bob"))

    def test_empty_returns_false(self):
        self.assertFalse(calorie_f.is_registered_user(""))


class TestSetupDatabase(unittest.TestCase):
    def setUp(self):
        self._makedirs_patch = patch("calorie.calorie_f.os.makedirs")
        self._makedirs_patch.start()

    def tearDown(self):
        self._makedirs_patch.stop()

    def _patch_conn(self):
        conn = sqlite3.connect(":memory:")
        patcher = patch("calorie.calorie_f.sqlite3.connect", return_value=conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(conn.close)
        return conn

    def test_creates_daily_records_table(self):
        conn = self._patch_conn()
        calorie_f.setup_database()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_records'"
        )
        self.assertIsNotNone(cursor.fetchone())

    def test_table_has_expected_columns(self):
        conn = self._patch_conn()
        calorie_f.setup_database()
        columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(daily_records)").fetchall()
        }
        self.assertIn("id", columns)
        self.assertIn("username", columns)
        self.assertIn("record_date", columns)
        self.assertIn("food_name", columns)
        self.assertIn("calories", columns)

    def test_is_idempotent(self):
        conn = self._patch_conn()
        calorie_f.setup_database()
        calorie_f.setup_database()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_records'"
        ).fetchall()
        self.assertEqual(len(tables), 1)


class TestStartGuiValidation(unittest.TestCase):
    @patch("calorie.calorie_f.messagebox.showerror")
    @patch("calorie.calorie_f.is_registered_user", return_value=False)
    def test_unregistered_shows_error(self, mock_check, mock_showerror):
        calorie_f.start_gui("unknown_user")
        mock_showerror.assert_called_once()
        args = mock_showerror.call_args[0]
        self.assertIn("not registered", args[1])

    @patch("calorie.calorie_f.is_registered_user", return_value=False)
    def test_unregistered_does_not_open_gui(self, mock_check):
        with patch("calorie.calorie_f.setup_database") as mock_setup:
            calorie_f.start_gui("unknown_user")
            mock_setup.assert_not_called()


class TestFetchCaloriesQueryBuilding(unittest.TestCase):
    """
    Test the food name processing and URL construction logic in fetch_calories.
    Uses mocked HTTP requests so no real API calls are made.
    """

    @patch("calorie.calorie_f.os.getenv", return_value="")
    def test_no_usda_key_skips_usda(self, mock_getenv):
        """When USDA_API_KEY is empty, USDA is skipped."""
        with patch("calorie.calorie_f.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"products": []}
            result = calorie_f.fetch_calories("apple")
            # Should try Open Food Facts URLs
            self.assertIsNone(result)
            self.assertGreaterEqual(mock_get.call_count, 1)

    @patch("calorie.calorie_f.os.getenv", return_value="fake_key")
    def test_usda_url_contains_api_key_and_query(self, mock_getenv):
        """USDA URL is built correctly with API key and query."""
        with patch("calorie.calorie_f.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"foods": []}
            calorie_f.fetch_calories("banana")
            first_call_args = mock_get.call_args_list[0]
            url = str(first_call_args[0][0])
            self.assertIn("api.nal.usda.gov", url)
            params = first_call_args[1].get("params", {})
            self.assertEqual(params.get("api_key"), "fake_key")
            self.assertEqual(params.get("query"), "banana")


class TestDatabaseOperations(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE daily_records ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  username TEXT NOT NULL DEFAULT 'legacy',"
            "  record_date TEXT NOT NULL,"
            "  food_name TEXT,"
            "  weight_grams REAL,"
            "  calories REAL"
            ")"
        )

    def test_insert_and_sum_daily(self):
        today = str(date.today())
        self.conn.execute(
            "INSERT INTO daily_records (username, record_date, food_name, weight_grams, calories) "
            "VALUES (?, ?, ?, ?, ?)",
            ("testuser", today, "apple", 200, 104),
        )
        self.conn.execute(
            "INSERT INTO daily_records (username, record_date, food_name, weight_grams, calories) "
            "VALUES (?, ?, ?, ?, ?)",
            ("testuser", today, "banana", 100, 89),
        )
        row = self.conn.execute(
            "SELECT COALESCE(SUM(calories), 0) FROM daily_records"
            " WHERE username = ? AND record_date = ?",
            ("testuser", today),
        ).fetchone()
        self.assertEqual(row[0], 193.0)

    def test_sum_empty_returns_zero(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(calories), 0) FROM daily_records"
            " WHERE username = ? AND record_date = ?",
            ("nobody", "2099-01-01"),
        ).fetchone()
        self.assertEqual(row[0], 0)

    def test_delete_record(self):
        today = str(date.today())
        cur = self.conn.execute(
            "INSERT INTO daily_records (username, record_date, food_name, weight_grams, calories) "
            "VALUES (?, ?, ?, ?, ?)",
            ("testuser", today, "orange", 150, 70),
        )
        rid = cur.lastrowid
        self.conn.execute("DELETE FROM daily_records WHERE id = ?", (rid,))
        remaining = self.conn.execute(
            "SELECT COUNT(*) FROM daily_records WHERE username = ?",
            ("testuser",),
        ).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_calorie_calculation(self):
        """Verify the formula: (kcal_per_100g / 100) * weight_grams"""
        kcal_100g = 52  # apple
        weight = 200
        consumed = (kcal_100g / 100) * weight
        self.assertEqual(consumed, 104.0)


if __name__ == "__main__":
    unittest.main()
