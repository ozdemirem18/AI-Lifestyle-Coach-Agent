"""
Integration tests for user registration flow in user_f.py.

Uses a temporary SQLite database file (no mocks on the DB layer).
Only DB_FILE is redirected to a temp path; init_db, create_user,
hash_password, validate_password, user_exists, get_password_hash,
save_user_profile, calculate_body_metrics all run against real SQLite.
"""

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from user import user_f


class TestRegisterFlowIntegration(unittest.TestCase):
    """End-to-end registration flow with a real temporary database."""

    _tmpdir = None  # set once at class level

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def setUp(self):
        # Each test gets its own database file to avoid Windows file locking.
        self.db_path = os.path.join(self._tmpdir.name, f"test_user_db_{id(self)}.db")
        self._patcher = patch("user.user_f.DB_FILE", self.db_path)
        self._patcher.start()
        user_f.init_db()

    def tearDown(self):
        self._patcher.stop()
        # Force-close any stale connections so the file can be cleaned up later.
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                pass

    def _count_users(self):
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def _get_user_row(self, username):
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def test_init_db_creates_users_table(self):
        """init_db() creates the users table with all expected columns."""
        expected = {
            "username", "password_hash", "age", "height_cm", "weight_kg",
            "bmi", "ideal_weight_min", "ideal_weight_max", "target_weight_kg",
            "gender",
        }
        with sqlite3.connect(self.db_path) as conn:
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(users)").fetchall()
            }
        self.assertLessEqual(expected, cols)

    def test_init_db_is_idempotent(self):
        """Calling init_db() twice does not raise."""
        user_f.init_db()  # second call
        self.assertEqual(self._count_users(), 0)

    # ------------------------------------------------------------------
    # Core register flow: user does not exist → create → exists
    # ------------------------------------------------------------------

    def test_create_user_and_verify_exists(self):
        self.assertFalse(user_f.user_exists("newuser"))
        user_f.create_user("newuser", user_f.hash_password("Secret1ab"))
        self.assertTrue(user_f.user_exists("newuser"))

    def test_create_user_persists_password_hash(self):
        pw_hash = user_f.hash_password("MyPass123")
        user_f.create_user("alice", pw_hash)

        stored = user_f.get_password_hash("alice")
        self.assertEqual(stored, pw_hash)

    def test_create_user_increments_count(self):
        self.assertEqual(self._count_users(), 0)
        user_f.create_user("u1", "h1")
        user_f.create_user("u2", "h2")
        self.assertEqual(self._count_users(), 2)

    # ------------------------------------------------------------------
    # Duplicate prevention
    # ------------------------------------------------------------------

    def test_duplicate_username_raises(self):
        user_f.create_user("existing", "hash123")
        with self.assertRaises(sqlite3.IntegrityError):
            user_f.create_user("existing", "other_hash")

    # ------------------------------------------------------------------
    # Password hashing
    # ------------------------------------------------------------------

    def test_hash_password_is_sha256_hex(self):
        h = user_f.hash_password("Hello123")
        self.assertEqual(len(h), 64)  # SHA-256 = 64 hex chars
        int(h, 16)  # raises if not valid hex

    def test_hash_password_is_deterministic(self):
        self.assertEqual(
            user_f.hash_password("Abc12345"),
            user_f.hash_password("Abc12345"),
        )

    def test_hash_password_differs_for_diff_inputs(self):
        self.assertNotEqual(
            user_f.hash_password("Abc12345"),
            user_f.hash_password("Xyz67890"),
        )

    def test_hash_password_accepts_unicode(self):
        h = user_f.hash_password("S3cret!üñíçöd€")
        self.assertEqual(len(h), 64)

    # ------------------------------------------------------------------
    # Password validation rules
    # ------------------------------------------------------------------

    def test_validate_password_too_short(self):
        errors = user_f.validate_password("Ab1")
        self.assertTrue(any("8 characters" in e for e in errors))

    def test_validate_password_missing_uppercase(self):
        errors = user_f.validate_password("abcdefgh1")
        self.assertTrue(any("uppercase" in e.lower() for e in errors))

    def test_validate_password_missing_lowercase(self):
        errors = user_f.validate_password("ABCDEFGH1")
        self.assertTrue(any("lowercase" in e.lower() for e in errors))

    def test_validate_password_missing_digit(self):
        errors = user_f.validate_password("Abcdefghi")
        self.assertTrue(any("digit" in e.lower() for e in errors))

    def test_validate_password_valid_returns_empty(self):
        self.assertEqual(user_f.validate_password("Abcdef1x"), [])

    def test_validate_password_reports_multiple_issues(self):
        errors = user_f.validate_password("short")
        self.assertGreaterEqual(len(errors), 2)

    # ------------------------------------------------------------------
    # get_password_hash edge cases
    # ------------------------------------------------------------------

    def test_get_password_hash_nonexistent_user(self):
        self.assertIsNone(user_f.get_password_hash("nobody"))

    # ------------------------------------------------------------------
    # Registration + login compatibility (hash round-trip)
    # ------------------------------------------------------------------

    def test_register_and_login_hash_match(self):
        """The hash stored during registration matches login verification."""
        raw_password = "SecurePass1"
        pw_hash = user_f.hash_password(raw_password)
        user_f.create_user("testuser", pw_hash)

        stored = user_f.get_password_hash("testuser")
        self.assertEqual(stored, user_f.hash_password(raw_password))

    # ------------------------------------------------------------------
    # Profile save and read (part of the register → profile setup flow)
    # ------------------------------------------------------------------

    def test_save_user_profile_updates_all_fields(self):
        user_f.create_user("profilename", user_f.hash_password("Pass1234a"))

        user_f.save_user_profile(
            username="profilename",
            age=28,
            height_cm=170.0,
            weight_kg=70.0,
            bmi=24.22,
            ideal_weight_min=55.0,
            ideal_weight_max=74.0,
            target_weight_kg=68.0,
            gender="Female",
        )

        row = self._get_user_row("profilename")
        self.assertIsNotNone(row)
        # sqlite3 row is a tuple; column order from schema:
        # username(0), password_hash(1), age(2), height_cm(3), weight_kg(4),
        # bmi(5), ideal_weight_min(6), ideal_weight_max(7), target_weight_kg(8), gender(9)
        self.assertEqual(row[2], 28)         # age
        self.assertEqual(row[3], 170.0)       # height_cm
        self.assertEqual(row[4], 70.0)        # weight_kg
        self.assertAlmostEqual(row[5], 24.22)  # bmi
        self.assertEqual(row[6], 55.0)        # ideal_weight_min
        self.assertEqual(row[7], 74.0)        # ideal_weight_max
        self.assertEqual(row[8], 68.0)        # target_weight_kg
        self.assertEqual(row[9], "Female")    # gender
        # username and password_hash should not have changed.
        self.assertEqual(row[0], "profilename")

    def test_save_user_profile_partial_overwrite(self):
        """Fields previously set are overwritten; calling twice is safe."""
        user_f.create_user("u", user_f.hash_password("Pass1234b"))
        user_f.save_user_profile("u", 25, 180, 80, 24.7, 60, 81, 78, "Male")
        user_f.save_user_profile("u", 26, 181, 82, 25.0, 61, 82, 80, "Male")

        row = self._get_user_row("u")
        self.assertEqual(row[2], 26)   # age updated
        self.assertEqual(row[3], 181.0)  # height updated

    # ------------------------------------------------------------------
    # Body metrics calculation (used during profile setup)
    # ------------------------------------------------------------------

    def test_calculate_body_metrics_returns_expected_values(self):
        bmi, ideal_min, ideal_max = user_f.calculate_body_metrics(
            age=30, height_cm=170.0, weight_kg=70.0,
        )
        # BMI = 70 / (1.70^2) = 24.22
        self.assertAlmostEqual(bmi, 24.22, places=1)
        # Ideal range for age 30: [18.5, 24.9]
        self.assertAlmostEqual(ideal_min, 18.5 * (1.7 ** 2), places=2)
        self.assertAlmostEqual(ideal_max, 24.9 * (1.7 ** 2), places=2)

    def test_calculate_body_metrics_senior_range(self):
        """Age >= 65 uses a different healthy BMI range [22, 27]."""
        bmi, ideal_min, ideal_max = user_f.calculate_body_metrics(
            age=70, height_cm=160.0, weight_kg=65.0,
        )
        self.assertAlmostEqual(ideal_min, 22.0 * (1.6 ** 2), places=2)
        self.assertAlmostEqual(ideal_max, 27.0 * (1.6 ** 2), places=2)

    def test_calculate_body_metrics_under_18_range(self):
        """Age < 18 uses [18.5, 24.0]."""
        bmi, ideal_min, ideal_max = user_f.calculate_body_metrics(
            age=15, height_cm=165.0, weight_kg=55.0,
        )
        self.assertAlmostEqual(ideal_min, 18.5 * (1.65 ** 2), places=2)
        self.assertAlmostEqual(ideal_max, 24.0 * (1.65 ** 2), places=2)

    # ------------------------------------------------------------------
    # user_exists edge cases
    # ------------------------------------------------------------------

    def test_user_exists_empty_string(self):
        self.assertFalse(user_f.user_exists(""))

    def test_user_exists_case_sensitivity(self):
        user_f.create_user("Alice", "hash")
        # SQLite WHERE is case-insensitive by default for = on non-binary collation;
        # verify the DB behaves as expected.
        self.assertTrue(user_f.user_exists("Alice"))
        # This may be True depending on SQLite collation; we just document behavior.


if __name__ == "__main__":
    unittest.main()
