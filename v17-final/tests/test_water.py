import os
import sqlite3
import unittest
from unittest.mock import patch, MagicMock
from datetime import date

from water import water_f


class TestIsRegisteredUser(unittest.TestCase):
    """Tests for water_f.is_registered_user()."""

    def setUp(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE)"
        )
        self._conn.execute("INSERT INTO users (username) VALUES ('alice')")
        self._patcher = patch("water.water_f.sqlite3.connect", return_value=self._conn)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._conn.close()

    def test_registered_user_returns_true(self):
        self.assertTrue(water_f.is_registered_user("alice"))

    def test_unregistered_user_returns_false(self):
        self.assertFalse(water_f.is_registered_user("bob"))

    def test_empty_string_returns_false(self):
        self.assertFalse(water_f.is_registered_user(""))
        self.assertFalse(water_f.is_registered_user("   "))

    def test_none_returns_false(self):
        self.assertFalse(water_f.is_registered_user(None))

    def test_whitespace_is_stripped(self):
        self.assertTrue(water_f.is_registered_user("  alice  "))


class TestSetupDatabase(unittest.TestCase):
    """Tests for water_f.setup_database()."""

    def setUp(self):
        self._makedirs_patch = patch("water.water_f.os.makedirs")
        self.mock_makedirs = self._makedirs_patch.start()

    def tearDown(self):
        self._makedirs_patch.stop()

    def _make_connect(self, db):
        """Return a patcher that makes sqlite3.connect return *db*."""
        patcher = patch("water.water_f.sqlite3.connect", return_value=db)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_creates_directory(self):
        conn = sqlite3.connect(":memory:")
        self._make_connect(conn)

        water_f.setup_database()

        self.mock_makedirs.assert_called_once_with(r"C:\project_database", exist_ok=True)

    def test_creates_water_records_table(self):
        conn = sqlite3.connect(":memory:")
        self._make_connect(conn)

        water_f.setup_database()

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='water_records'"
        )
        self.assertIsNotNone(cursor.fetchone())

    def test_table_has_expected_columns(self):
        conn = sqlite3.connect(":memory:")
        self._make_connect(conn)

        water_f.setup_database()

        columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(water_records)").fetchall()
        }
        self.assertIn("id", columns)
        self.assertIn("username", columns)
        self.assertIn("record_date", columns)
        self.assertIn("water_ml", columns)
        # username should be TEXT NOT NULL
        self.assertEqual(columns["username"].upper(), "TEXT")

    def test_id_is_auto_increment_primary_key(self):
        conn = sqlite3.connect(":memory:")
        self._make_connect(conn)

        water_f.setup_database()

        pk_cols = [
            row[5] for row in conn.execute("PRAGMA table_info(water_records)").fetchall()
            if row[5] > 0  # pk flag > 0
        ]
        self.assertEqual(len(pk_cols), 1)
        # Insert two rows without specifying id; both should succeed.
        conn.execute(
            "INSERT INTO water_records (username, record_date, water_ml) VALUES (?, ?, ?)",
            ("u1", "2025-01-01", 250),
        )
        conn.execute(
            "INSERT INTO water_records (username, record_date, water_ml) VALUES (?, ?, ?)",
            ("u1", "2025-01-01", 500),
        )
        ids = [r[0] for r in conn.execute("SELECT id FROM water_records").fetchall()]
        self.assertEqual(ids, [1, 2])

    def test_is_idempotent(self):
        conn = sqlite3.connect(":memory:")
        self._make_connect(conn)

        water_f.setup_database()
        water_f.setup_database()  # second call should not raise

        tables = [
            r for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
            ).fetchall()
        ]
        self.assertEqual(len(tables), 1)

    def test_migrates_adds_username_column(self):
        """Simulate legacy table that lacks the username column."""
        conn = sqlite3.connect(":memory:")
        self._make_connect(conn)

        conn.execute(
            "CREATE TABLE water_records ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  record_date TEXT NOT NULL,"
            "  water_ml REAL NOT NULL"
            ")"
        )
        conn.execute(
            "INSERT INTO water_records (record_date, water_ml) VALUES (?, ?)",
            ("2025-01-01", 250),
        )

        water_f.setup_database()

        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(water_records)").fetchall()
        }
        self.assertIn("username", columns)
        # Data should still be there, and legacy row gets default 'legacy' username.
        row = conn.execute(
            "SELECT username, water_ml FROM water_records WHERE record_date = ?",
            ("2025-01-01",),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "legacy")
        self.assertEqual(row[1], 250)


class TestStartGuiValidation(unittest.TestCase):
    """start_gui short-circuits for unregistered users — test that branch."""

    @patch("water.water_f.messagebox.showerror")
    @patch("water.water_f.is_registered_user", return_value=False)
    def test_unregistered_user_shows_error(self, mock_check, mock_showerror):
        water_f.start_gui("unknown_user")

        mock_showerror.assert_called_once()
        args = mock_showerror.call_args[0]
        self.assertIn("Unauthorized", args)

    @patch("water.water_f.is_registered_user", return_value=False)
    def test_unregistered_user_does_not_open_gui(self, mock_check):
        with patch("water.water_f.setup_database") as mock_setup:
            water_f.start_gui("unknown_user")
            mock_setup.assert_not_called()


class TestDatabaseOperations(unittest.TestCase):
    """
    Verify the core SQL patterns used inside start_gui's closures
    (add_record, refresh_list, delete_selected) work correctly.
    """

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE water_records ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  username TEXT NOT NULL DEFAULT 'legacy',"
            "  record_date TEXT NOT NULL,"
            "  water_ml REAL NOT NULL"
            ")"
        )

    def test_insert_and_sum_daily(self):
        today = str(date.today())
        self.conn.execute(
            "INSERT INTO water_records (username, record_date, water_ml) VALUES (?, ?, ?)",
            ("testuser", today, 250),
        )
        self.conn.execute(
            "INSERT INTO water_records (username, record_date, water_ml) VALUES (?, ?, ?)",
            ("testuser", today, 500),
        )
        row = self.conn.execute(
            "SELECT COALESCE(SUM(water_ml), 0) FROM water_records"
            " WHERE username = ? AND record_date = ?",
            ("testuser", today),
        ).fetchone()
        self.assertEqual(row[0], 750)

    def test_sum_empty_day_returns_zero(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(water_ml), 0) FROM water_records"
            " WHERE username = ? AND record_date = ?",
            ("nobody", "2099-01-01"),
        ).fetchone()
        self.assertEqual(row[0], 0)

    def test_delete_record(self):
        today = str(date.today())
        cur = self.conn.execute(
            "INSERT INTO water_records (username, record_date, water_ml) VALUES (?, ?, ?)",
            ("testuser", today, 300),
        )
        rid = cur.lastrowid

        self.conn.execute("DELETE FROM water_records WHERE id = ?", (rid,))
        remaining = self.conn.execute(
            "SELECT COUNT(*) FROM water_records WHERE username = ?",
            ("testuser",),
        ).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_multiple_users_separate_sums(self):
        today = str(date.today())
        for u, ml in [("alice", 250), ("alice", 250), ("bob", 500)]:
            self.conn.execute(
                "INSERT INTO water_records (username, record_date, water_ml) VALUES (?, ?, ?)",
                (u, today, ml),
            )
        alice_total = self.conn.execute(
            "SELECT COALESCE(SUM(water_ml), 0) FROM water_records"
            " WHERE username = ? AND record_date = ?",
            ("alice", today),
        ).fetchone()[0]
        self.assertEqual(alice_total, 500)


if __name__ == "__main__":
    unittest.main()
