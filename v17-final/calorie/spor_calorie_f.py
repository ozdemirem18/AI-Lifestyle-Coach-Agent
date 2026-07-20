import sqlite3
from datetime import date


SPOR_DB_PATH = r"C:\project_database\spor_db.db"
USER_DB_PATH = r"C:\project_database\user_db.db"
CALORIE_DB_PATH = r"C:\project_database\calorie_db.db"


EXERCISE_MET = {
    "walking": 3.0,
    "hafif tempolu yuruyus": 3.0,
    "squat": 5.0,
    "pushup": 8.0,
    "push_up": 8.0,
    "sinav": 8.0,
    "situp": 3.0,
    "sit_up": 3.0,
    "mekik": 3.0,
    "bicep_curl": 3.0,
    "arm_raise": 3.0,
    "arm raise": 3.0,
    "plank": 3.8,
    "march": 4.0,
    "jumping_jack": 8.0,
    "burpee": 10.0,
    "jump": 5.0,
}

EXERCISE_REP_SECONDS = {
    "pushup": 2.2,
    "push_up": 2.2,
    "sinav": 2.2,
    "squat": 2.4,
    "situp": 2.0,
    "sit_up": 2.0,
    "mekik": 2.0,
    "bicep_curl": 3.0,
    "march": 1.0,
    "arm_raise": 2.5,
    "jump": 1.0,
}

# Walking / steps constants
WALKING_MET = 3.0
STEPS_PER_HOUR = 7000  # moderate walking pace


def is_registered_user(username):
    normalized = str(username or "").strip()
    if not normalized:
        return False
    with sqlite3.connect(USER_DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE username = ? LIMIT 1",
            (normalized,),
        ).fetchone()
    return row is not None


def _normalize_exercise_name(exercise_name):
    return str(exercise_name).strip().lower().replace("-", "_").replace(" ", "_")


def _amount_to_hours(amount, unit, exercise_name=None):
    unit_normalized = str(unit).strip().lower()
    value = float(amount)

    if unit_normalized in {"hour", "hours", "saat", "hr"}:
        return value
    if unit_normalized in {"minute", "minutes", "dk", "dakika", "min"}:
        return value / 60.0
    if unit_normalized in {"second", "seconds", "sn", "saniye", "sec"}:
        return value / 3600.0
    if unit_normalized in {"rep", "reps", "tekrar"}:
        rep_key = _normalize_exercise_name(exercise_name or "")
        seconds_per_rep = EXERCISE_REP_SECONDS.get(rep_key, 2.5)
        return (value * seconds_per_rep) / 3600.0

    # If the unit is unknown we assume minutes to keep backward compatibility.
    return value / 60.0


def get_exercise_logs(username, log_date=None):
    target_date = log_date or str(date.today())
    with sqlite3.connect(SPOR_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT username, exercise_name, total_amount, unit, log_date
            FROM exercise_daily_logs
            WHERE username = ? AND log_date = ?
            ORDER BY id ASC
            """,
            (username, target_date),
        ).fetchall()
    return [dict(row) for row in rows]


def get_user_info(username):
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT username, age, height_cm, weight_kg, gender
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

    if row is None:
        raise ValueError(f"User not found: {username}")

    user_info = dict(row)
    if user_info.get("weight_kg") is None:
        raise ValueError("Kilo bilgisi eksik. Lütfen user profile kaydını tamamlayın.")
    if user_info.get("height_cm") is None:
        raise ValueError("Boy bilgisi eksik. Lütfen user profile kaydını tamamlayın.")
    if user_info.get("age") is None:
        raise ValueError("Yaş bilgisi eksik. Lütfen user profile kaydını tamamlayın.")

    return user_info


def calculate_exercise_calorie(met_value, weight_kg, duration_hours):
    return float(met_value) * float(weight_kg) * float(duration_hours)


def calculate_steps_calorie(steps: int, weight_kg: float) -> float:
    """
    Estimate calories burned from walking steps using MET formula.
    Uses walking MET (3.0) and average steps/hour (7000).
    Calories = MET * weight_kg * (steps / steps_per_hour)
    """
    duration_hours = float(steps) / STEPS_PER_HOUR
    return round(calculate_exercise_calorie(WALKING_MET, weight_kg, duration_hours), 2)


def calculate_bmr(weight_kg, height_cm, age, gender):
    gender_normalized = str(gender or "").strip().lower()
    base = (10 * float(weight_kg)) + (6.25 * float(height_cm)) - (5 * float(age))

    if gender_normalized in {"male", "erkek", "m"}:
        return base + 5
    if gender_normalized in {"female", "kadin", "kadın", "f"}:
        return base - 161

    # For undefined/other gender: average of male and female constants.
    return base - 78


def calculate_daily_exercise_report(username, log_date=None):
    if not is_registered_user(username):
        raise ValueError("Bu username user_db.db icinde kayitli degil.")
    user = get_user_info(username)
    logs = get_exercise_logs(username=username, log_date=log_date)
    weight_kg = user["weight_kg"]

    exercise_breakdown = []
    total_exercise_kcal = 0.0

    for item in logs:
        exercise_name = item["exercise_name"]
        normalized_name = _normalize_exercise_name(exercise_name)
        met_value = EXERCISE_MET.get(normalized_name)

        if met_value is None:
            exercise_breakdown.append(
                {
                    "exercise_name": exercise_name,
                    "met": None,
                    "duration_hours": 0.0,
                    "calories": 0.0,
                    "status": "MET tanimi yok",
                }
            )
            continue

        duration_hours = _amount_to_hours(
            item["total_amount"], item["unit"], exercise_name=exercise_name
        )
        burned_kcal = calculate_exercise_calorie(met_value, weight_kg, duration_hours)
        total_exercise_kcal += burned_kcal

        exercise_breakdown.append(
            {
                "exercise_name": exercise_name,
                "met": met_value,
                "duration_hours": round(duration_hours, 4),
                "calories": round(burned_kcal, 2),
                "status": "ok",
            }
        )

    bmr_value = calculate_bmr(
        weight_kg=user["weight_kg"],
        height_cm=user["height_cm"],
        age=user["age"],
        gender=user.get("gender"),
    )

    return {
        "username": username,
        "log_date": log_date or str(date.today()),
        "user": user,
        "exercise_breakdown": exercise_breakdown,
        "total_exercise_kcal": round(total_exercise_kcal, 2),
        "bmr_kcal_per_day": round(bmr_value, 2),
    }


def save_daily_exercise_report_to_calorie_db(report):
    with sqlite3.connect(CALORIE_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS exercise_calorie_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                log_date TEXT NOT NULL,
                exercise_name TEXT NOT NULL,
                met REAL,
                duration_hours REAL NOT NULL DEFAULT 0,
                calories REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(username, log_date, exercise_name)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS exercise_calorie_daily_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                log_date TEXT NOT NULL,
                total_exercise_kcal REAL NOT NULL DEFAULT 0,
                bmr_kcal_per_day REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                UNIQUE(username, log_date)
            )
            """
        )

        username = report["username"]
        log_date = report["log_date"]
        now_ts = str(date.today())

        for item in report.get("exercise_breakdown", []):
            cursor.execute(
                """
                INSERT INTO exercise_calorie_logs
                (username, log_date, exercise_name, met, duration_hours, calories, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(username, log_date, exercise_name)
                DO UPDATE SET
                    met = excluded.met,
                    duration_hours = excluded.duration_hours,
                    calories = excluded.calories,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    username,
                    log_date,
                    item.get("exercise_name", ""),
                    item.get("met"),
                    float(item.get("duration_hours", 0)),
                    float(item.get("calories", 0)),
                    item.get("status", "unknown"),
                    now_ts,
                ),
            )

        cursor.execute(
            """
            INSERT INTO exercise_calorie_daily_summary
            (username, log_date, total_exercise_kcal, bmr_kcal_per_day, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(username, log_date)
            DO UPDATE SET
                total_exercise_kcal = excluded.total_exercise_kcal,
                bmr_kcal_per_day = excluded.bmr_kcal_per_day,
                updated_at = excluded.updated_at
            """,
            (
                username,
                log_date,
                float(report.get("total_exercise_kcal", 0)),
                float(report.get("bmr_kcal_per_day", 0)),
                now_ts,
            ),
        )

        conn.commit()


if __name__ == "__main__":
    sample_username = input("Username: ").strip()
    sample_date = input("Date (YYYY-MM-DD, bos gec): ").strip() or None

    report = calculate_daily_exercise_report(sample_username, sample_date)
    print(f"\nKullanici: {report['username']}")
    print(f"Tarih: {report['log_date']}")
    print(f"BMR (gunluk): {report['bmr_kcal_per_day']} kcal")
    print(f"Egzersiz Toplam: {report['total_exercise_kcal']} kcal")
    print("-" * 40)
    for row in report["exercise_breakdown"]:
        if row["status"] != "ok":
            print(f"{row['exercise_name']}: {row['status']}")
            continue
        print(
            f"{row['exercise_name']}: MET={row['met']}, "
            f"sure={row['duration_hours']} saat, "
            f"kalori={row['calories']} kcal"
        )
