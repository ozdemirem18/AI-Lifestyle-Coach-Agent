import os
import sqlite3
import unittest
from unittest.mock import patch
from datetime import date

from sleep import sleep_f


class TestIsRegisteredUser(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE)"
        )
        self.conn.execute("INSERT INTO users (username) VALUES ('alice')")
        self.patcher = patch("sleep.sleep_f.sqlite3.connect", return_value=self.conn)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.conn.close()

    def test_registered_returns_true(self):
        self.assertTrue(sleep_f.is_registered_user("alice"))

    def test_unregistered_returns_false(self):
        self.assertFalse(sleep_f.is_registered_user("bob"))

    def test_empty_returns_false(self):
        self.assertFalse(sleep_f.is_registered_user(""))

    def test_none_returns_false(self):
        self.assertFalse(sleep_f.is_registered_user(None))


class TestSetupDatabase(unittest.TestCase):
    def setUp(self):
        self._makedirs_patch = patch("sleep.sleep_f.os.makedirs")
        self._makedirs_patch.start()

    def tearDown(self):
        self._makedirs_patch.stop()

    def _patch_conn(self):
        conn = sqlite3.connect(":memory:")
        patcher = patch("sleep.sleep_f.sqlite3.connect", return_value=conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(conn.close)
        return conn

    def test_creates_sleep_records_table(self):
        conn = self._patch_conn()
        sleep_f.setup_database()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sleep_records'"
        )
        self.assertIsNotNone(cursor.fetchone())

    def test_table_has_expected_columns(self):
        conn = self._patch_conn()
        sleep_f.setup_database()
        columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(sleep_records)").fetchall()
        }
        self.assertIn("id", columns)
        self.assertIn("username", columns)
        self.assertIn("record_date", columns)
        self.assertIn("sleep_hours", columns)

    def test_is_idempotent(self):
        conn = self._patch_conn()
        sleep_f.setup_database()
        sleep_f.setup_database()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sleep_records'"
        ).fetchall()
        self.assertEqual(len(tables), 1)

    def test_migrates_adds_username_column(self):
        conn = self._patch_conn()
        conn.execute(
            "CREATE TABLE sleep_records ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  record_date TEXT NOT NULL,"
            "  sleep_hours REAL NOT NULL"
            ")"
        )
        conn.execute(
            "INSERT INTO sleep_records (record_date, sleep_hours) VALUES (?, ?)",
            ("2025-01-01", 7.5),
        )
        sleep_f.setup_database()
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(sleep_records)").fetchall()
        }
        self.assertIn("username", columns)
        row = conn.execute(
            "SELECT username, sleep_hours FROM sleep_records WHERE record_date = ?",
            ("2025-01-01",),
        ).fetchone()
        self.assertEqual(row[0], "legacy")
        self.assertEqual(row[1], 7.5)


class TestStartGuiValidation(unittest.TestCase):
    @patch("sleep.sleep_f.messagebox.showerror")
    @patch("sleep.sleep_f.is_registered_user", return_value=False)
    def test_unregistered_user_shows_error(self, mock_check, mock_showerror):
        sleep_f.start_gui("unknown_user")
        mock_showerror.assert_called_once()
        args = mock_showerror.call_args[0]
        self.assertIn("not registered", args[1])

    @patch("sleep.sleep_f.is_registered_user", return_value=False)
    def test_unregistered_does_not_open_gui(self, mock_check):
        with patch("sleep.sleep_f.setup_database") as mock_setup:
            sleep_f.start_gui("unknown_user")
            mock_setup.assert_not_called()


class TestDatabaseOperations(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE sleep_records ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  username TEXT NOT NULL DEFAULT 'legacy',"
            "  record_date TEXT NOT NULL,"
            "  sleep_hours REAL NOT NULL"
            ")"
        )

    def test_insert_and_sum_daily(self):
        today = str(date.today())
        self.conn.execute(
            "INSERT INTO sleep_records (username, record_date, sleep_hours) VALUES (?, ?, ?)",
            ("testuser", today, 7.0),
        )
        self.conn.execute(
            "INSERT INTO sleep_records (username, record_date, sleep_hours) VALUES (?, ?, ?)",
            ("testuser", today, 1.5),
        )
        row = self.conn.execute(
            "SELECT COALESCE(SUM(sleep_hours), 0) FROM sleep_records"
            " WHERE username = ? AND record_date = ?",
            ("testuser", today),
        ).fetchone()
        self.assertEqual(row[0], 8.5)

    def test_sum_empty_day_returns_zero(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(sleep_hours), 0) FROM sleep_records"
            " WHERE username = ? AND record_date = ?",
            ("nobody", "2099-01-01"),
        ).fetchone()
        self.assertEqual(row[0], 0)

    def test_delete_record(self):
        today = str(date.today())
        cur = self.conn.execute(
            "INSERT INTO sleep_records (username, record_date, sleep_hours) VALUES (?, ?, ?)",
            ("testuser", today, 8.0),
        )
        rid = cur.lastrowid
        self.conn.execute("DELETE FROM sleep_records WHERE id = ?", (rid,))
        remaining = self.conn.execute(
            "SELECT COUNT(*) FROM sleep_records WHERE username = ?",
            ("testuser",),
        ).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_multiple_users_separate_sums(self):
        today = str(date.today())
        for u, h in [("alice", 7), ("alice", 1), ("bob", 8)]:
            self.conn.execute(
                "INSERT INTO sleep_records (username, record_date, sleep_hours) VALUES (?, ?, ?)",
                (u, today, h),
            )
        alice_total = self.conn.execute(
            "SELECT COALESCE(SUM(sleep_hours), 0) FROM sleep_records"
            " WHERE username = ? AND record_date = ?",
            ("alice", today),
        ).fetchone()[0]
        self.assertEqual(alice_total, 8.0)


if __name__ == "__main__":
    unittest.main()
