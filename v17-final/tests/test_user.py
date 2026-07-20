import sqlite3
import unittest
from unittest.mock import patch

from user import user_f


class TestHashPassword(unittest.TestCase):
    def test_hash_is_deterministic(self):
        self.assertEqual(
            user_f.hash_password("MyP@ss123"),
            user_f.hash_password("MyP@ss123"),
        )

    def test_different_passwords_differ(self):
        self.assertNotEqual(
            user_f.hash_password("Pass1234"),
            user_f.hash_password("Pass5678"),
        )

    def test_hash_is_sha256_hex(self):
        h = user_f.hash_password("hello")
        self.assertEqual(len(h), 64)
        int(h, 16)  # raises ValueError if not hex

    def test_empty_password_hashes(self):
        h = user_f.hash_password("")
        self.assertEqual(len(h), 64)


class TestValidatePassword(unittest.TestCase):
    def test_too_short_returns_error(self):
        errors = user_f.validate_password("Ab1")
        self.assertTrue(any("8 characters" in e for e in errors))

    def test_no_uppercase_returns_error(self):
        errors = user_f.validate_password("abcdefgh1")
        self.assertTrue(any("uppercase" in e for e in errors))

    def test_no_lowercase_returns_error(self):
        errors = user_f.validate_password("ABCDEFGH1")
        self.assertTrue(any("lowercase" in e for e in errors))

    def test_no_digit_returns_error(self):
        errors = user_f.validate_password("Abcdefgh")
        self.assertTrue(any("digit" in e for e in errors))

    def test_valid_password_returns_empty_list(self):
        errors = user_f.validate_password("ValidPass1")
        self.assertEqual(errors, [])

    def test_multiple_rules_caught_together(self):
        errors = user_f.validate_password("short")
        self.assertGreaterEqual(len(errors), 2)


class TestGetHealthyBmiRange(unittest.TestCase):
    def test_adult_range(self):
        lo, hi = user_f.get_healthy_bmi_range(30)
        self.assertEqual(lo, 18.5)
        self.assertEqual(hi, 24.9)

    def test_teen_range(self):
        lo, hi = user_f.get_healthy_bmi_range(16)
        self.assertEqual(lo, 18.5)
        self.assertEqual(hi, 24.0)

    def test_senior_range(self):
        lo, hi = user_f.get_healthy_bmi_range(70)
        self.assertEqual(lo, 22.0)
        self.assertEqual(hi, 27.0)

    def test_exactly_65_uses_senior_range(self):
        lo, hi = user_f.get_healthy_bmi_range(65)
        self.assertEqual(lo, 22.0)

    def test_exactly_18_uses_adult_range(self):
        lo, hi = user_f.get_healthy_bmi_range(18)
        self.assertEqual(lo, 18.5)
        self.assertEqual(hi, 24.9)


class TestCalculateBodyMetrics(unittest.TestCase):
    def test_bmi_formula(self):
        bmi, ideal_min, ideal_max = user_f.calculate_body_metrics(30, 170, 65)
        expected_bmi = 65 / (1.7 * 1.7)
        self.assertAlmostEqual(bmi, round(expected_bmi, 2))
        self.assertAlmostEqual(ideal_min, round(18.5 * 1.7 * 1.7, 2))
        self.assertAlmostEqual(ideal_max, round(24.9 * 1.7 * 1.7, 2))

    def test_bmi_rounding(self):
        bmi, _, _ = user_f.calculate_body_metrics(25, 180, 80)
        self.assertEqual(bmi, round(80 / (1.8 * 1.8), 2))

    def test_zero_height_division(self):
        with self.assertRaises(ZeroDivisionError):
            user_f.calculate_body_metrics(30, 0, 65)

    def test_senior_ideal_range(self):
        _, ideal_min, ideal_max = user_f.calculate_body_metrics(70, 160, 70)
        expected_min = 22.0 * (1.6 * 1.6)
        expected_max = 27.0 * (1.6 * 1.6)
        self.assertAlmostEqual(ideal_min, round(expected_min, 2))
        self.assertAlmostEqual(ideal_max, round(expected_max, 2))


class TestUserExists(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE users (username TEXT PRIMARY KEY, password_hash TEXT)"
        )
        self.conn.execute("INSERT INTO users (username, password_hash) VALUES ('alice', 'abc')")
        self.patcher = patch("user.user_f.get_connection", return_value=self.conn)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.conn.close()

    def test_existing_user_returns_true(self):
        self.assertTrue(user_f.user_exists("alice"))

    def test_missing_user_returns_false(self):
        self.assertFalse(user_f.user_exists("bob"))

    def test_case_sensitive(self):
        self.assertFalse(user_f.user_exists("Alice"))


class TestCreateUser(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE users (username TEXT PRIMARY KEY, password_hash TEXT)"
        )
        self.patcher = patch("user.user_f.get_connection", return_value=self.conn)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.conn.close()

    def test_creates_user(self):
        user_f.create_user("bob", "hashed123")
        row = self.conn.execute(
            "SELECT username, password_hash FROM users WHERE username = ?",
            ("bob",),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "bob")
        self.assertEqual(row[1], "hashed123")

    def test_duplicate_username_raises(self):
        user_f.create_user("bob", "h1")
        with self.assertRaises(sqlite3.IntegrityError):
            user_f.create_user("bob", "h2")


class TestGetPasswordHash(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE users (username TEXT PRIMARY KEY, password_hash TEXT)"
        )
        self.conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("alice", "abc123"),
        )
        self.patcher = patch("user.user_f.get_connection", return_value=self.conn)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.conn.close()

    def test_returns_hash_for_existing_user(self):
        self.assertEqual(user_f.get_password_hash("alice"), "abc123")

    def test_returns_none_for_missing_user(self):
        self.assertIsNone(user_f.get_password_hash("nobody"))


class TestSaveUserProfile(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE users ("
            "  username TEXT PRIMARY KEY, password_hash TEXT,"
            "  age INTEGER, height_cm REAL, weight_kg REAL,"
            "  bmi REAL, ideal_weight_min REAL, ideal_weight_max REAL,"
            "  target_weight_kg REAL, gender TEXT"
            ")"
        )
        self.conn.execute(
            "INSERT INTO users (username, password_hash) VALUES ('alice', 'h')"
        )
        self.patcher = patch("user.user_f.get_connection", return_value=self.conn)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.conn.close()

    def test_saves_all_fields(self):
        user_f.save_user_profile(
            "alice", 30, 170, 65, 22.5, 53.5, 72.0, 68.0, "Female"
        )
        row = self.conn.execute(
            "SELECT age, height_cm, weight_kg, bmi, ideal_weight_min, "
            "ideal_weight_max, target_weight_kg, gender FROM users WHERE username = ?",
            ("alice",),
        ).fetchone()
        self.assertEqual(row, (30, 170, 65, 22.5, 53.5, 72.0, 68.0, "Female"))

    def test_updates_existing_user(self):
        user_f.save_user_profile("alice", 25, 160, 55, 21.5, 50.0, 65.0, 60.0, "Male")
        user_f.save_user_profile("alice", 26, 161, 56, 21.6, 50.5, 65.5, 61.0, "Male")
        row = self.conn.execute(
            "SELECT age, weight_kg FROM users WHERE username = ?", ("alice",),
        ).fetchone()
        self.assertEqual(row, (26, 56))


if __name__ == "__main__":
    unittest.main()
