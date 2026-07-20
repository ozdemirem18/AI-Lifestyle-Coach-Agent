import json
import hashlib
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


DEFAULT_USER_DB = r"C:\project_database\user_db.db"
DEFAULT_SLEEP_DB = r"C:\project_database\sleep_db.db"
DEFAULT_WATER_DB = r"C:\project_database\water_db.db"
DEFAULT_CALORIE_DB = r"C:\project_database\calorie_db.db"
DEFAULT_SPOR_DB = r"C:\project_database\spor_db.db"
DEFAULT_STEP_DB = r"C:\project_database\step_db.db"
USER_DB_PATH = os.getenv("USER_DB_PATH", DEFAULT_USER_DB)
SLEEP_DB_PATH = os.getenv("SLEEP_DB_PATH", DEFAULT_SLEEP_DB)
WATER_DB_PATH = os.getenv("WATER_DB_PATH", DEFAULT_WATER_DB)
CALORIE_DB_PATH = os.getenv("CALORIE_DB_PATH", DEFAULT_CALORIE_DB)
SPOR_DB_PATH = os.getenv("SPOR_DB_PATH", DEFAULT_SPOR_DB)
STEP_DB_PATH = os.getenv("STEP_DB_PATH", DEFAULT_STEP_DB)
DEFAULT_COACH_DB = r"C:\project_database\coach_db.db"
COACH_DB_PATH = os.getenv("COACH_DB_PATH", DEFAULT_COACH_DB)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent  # <project_root> (webapp/../..)
STATIC_DIR = PROJECT_ROOT / "webapp" / "frontend" / "websitedesign"

# Register project root so ai_coach module can be imported later
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RegisterRequest(BaseModel):
    username: str
    password: str
    confirm_password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class SleepRecordRequest(BaseModel):
    username: str
    sleep_hours: float


class WaterRecordRequest(BaseModel):
    username: str
    water_ml: float


class CalorieRecordRequest(BaseModel):
    username: str
    food_name: str
    weight_grams: float
    calories: float


class StepRecordRequest(BaseModel):
    username: str
    steps: int


class ExerciseRecordRequest(BaseModel):
    username: str
    exercise_name: str
    amount: float
    unit: str


class ExerciseLaunchRequest(BaseModel):
    username: str


class ExerciseLogDeleteRequest(BaseModel):
    log_id: int


class ProfileUpdateRequest(BaseModel):
    username: str
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    gender: str | None = None
    target_weight_kg: float | None = None
    daily_calorie_goal: float | None = None


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    text: str


class CreateChatRequest(BaseModel):
    username: str
    title: str | None = None


class AddMessageRequest(BaseModel):
    role: str
    text: str


class UpdateChatTitleRequest(BaseModel):
    title: str


class AICoachChatRequest(BaseModel):
    username: str
    message: str
    history: list[ChatMessage] = []


OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"


def get_connection(db_path: str) -> sqlite3.Connection:
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    return sqlite3.connect(db_path)


def init_user_db() -> None:
    with get_connection(USER_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                age INTEGER,
                height_cm REAL,
                weight_kg REAL,
                bmi REAL,
                ideal_weight_min REAL,
                ideal_weight_max REAL,
                target_weight_kg REAL,
                gender TEXT
            )
            """
        )
        conn.commit()

    # Add daily_calorie_goal column if it doesn't exist
    with get_connection(USER_DB_PATH) as conn:
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN daily_calorie_goal REAL DEFAULT 2000"
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists


def init_sleep_db() -> None:
    with get_connection(SLEEP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sleep_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL DEFAULT 'legacy',
                record_date TEXT NOT NULL,
                sleep_hours REAL NOT NULL
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sleep_records)").fetchall()}
        if "username" not in columns:
            conn.execute(
                "ALTER TABLE sleep_records ADD COLUMN username TEXT NOT NULL DEFAULT 'legacy'"
            )
        conn.commit()


def init_water_db() -> None:
    with get_connection(WATER_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS water_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL DEFAULT 'legacy',
                record_date TEXT NOT NULL,
                water_ml REAL NOT NULL
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(water_records)").fetchall()}
        if "username" not in columns:
            conn.execute(
                "ALTER TABLE water_records ADD COLUMN username TEXT NOT NULL DEFAULT 'legacy'"
            )
        conn.commit()


def init_calorie_db() -> None:
    with get_connection(CALORIE_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL DEFAULT 'legacy',
                record_date TEXT,
                food_name TEXT,
                weight_grams REAL,
                calories REAL
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(daily_records)").fetchall()}
        if "username" not in columns:
            conn.execute(
                "ALTER TABLE daily_records ADD COLUMN username TEXT NOT NULL DEFAULT 'legacy'"
            )
        conn.commit()


def init_step_db() -> None:
    with get_connection(STEP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS step_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL DEFAULT 'legacy',
                record_date TEXT NOT NULL,
                steps INTEGER NOT NULL
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(step_records)").fetchall()}
        if "username" not in columns:
            conn.execute(
                "ALTER TABLE step_records ADD COLUMN username TEXT NOT NULL DEFAULT 'legacy'"
            )
        conn.commit()


def init_coach_db() -> None:
    with get_connection(COACH_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_coach_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT 'New Chat',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_coach_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES ai_coach_chats(id)
            )
            """
        )
        conn.commit()


def init_spor_db() -> None:
    with get_connection(SPOR_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exercise_daily_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                exercise_name TEXT NOT NULL,
                log_date TEXT NOT NULL,
                total_amount REAL NOT NULL DEFAULT 0,
                unit TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(exercise_daily_logs)").fetchall()}
        if "username" not in columns:
            conn.execute(
                "ALTER TABLE exercise_daily_logs ADD COLUMN username TEXT NOT NULL DEFAULT 'legacy'"
            )
        conn.commit()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def validate_password(password: str) -> list[str]:
    errors: list[str] = []
    if len(password) < 8:
        errors.append("Must be at least 8 characters.")
    if not re.search(r"[A-Z]", password):
        errors.append("Must include at least 1 uppercase letter.")
    if not re.search(r"[a-z]", password):
        errors.append("Must include at least 1 lowercase letter.")
    if not re.search(r"[0-9]", password):
        errors.append("Must include at least 1 digit.")
    return errors


def user_exists(username: str) -> bool:
    with get_connection(USER_DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return row is not None


def get_password_hash(username: str) -> str | None:
    with get_connection(USER_DB_PATH) as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return row[0] if row else None


def require_known_user(username: str) -> str:
    normalized = username.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
    if not user_exists(normalized):
        raise HTTPException(status_code=404, detail="User not found.")
    return normalized


app = FastAPI(title="AI Fitness Trainer Web API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_user_db()
    init_sleep_db()
    init_water_db()
    init_calorie_db()
    init_spor_db()
    init_step_db()
    init_coach_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/register")
def register(payload: RegisterRequest) -> dict[str, str]:
    username = payload.username.strip()
    password = payload.password
    confirm_password = payload.confirm_password

    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")
    if user_exists(username):
        raise HTTPException(status_code=409, detail="This username is already registered.")

    password_errors = validate_password(password)
    if password_errors:
        raise HTTPException(status_code=400, detail=" ".join(password_errors))

    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    with get_connection(USER_DB_PATH) as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, hash_password(password)),
        )
        conn.commit()

    return {"message": "Registration successful."}


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> dict[str, str]:
    username = payload.username.strip()
    password = payload.password

    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")

    stored_hash = get_password_hash(username)
    if stored_hash is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if stored_hash != hash_password(password):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    return {"message": "Login successful.", "username": username}


@app.get("/api/profile/{username}")
def get_profile(username: str) -> dict[str, object]:
    normalized = require_known_user(username)
    with get_connection(USER_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT username, age, height_cm, weight_kg, bmi, ideal_weight_min,
                   ideal_weight_max, target_weight_kg, gender, daily_calorie_goal
            FROM users
            WHERE username = ?
            """,
            (normalized,),
        ).fetchone()
    return {"profile": dict(row) if row else None}


def get_healthy_bmi_range(age: int) -> tuple[float, float]:
    if age >= 65:
        return 22.0, 27.0
    if age < 18:
        return 18.5, 24.0
    return 18.5, 24.9


def calculate_body_metrics(age: int, height_cm: float, weight_kg: float) -> tuple[float, float, float]:
    height_m = height_cm / 100.0
    bmi = weight_kg / (height_m * height_m)
    bmi_min, bmi_max = get_healthy_bmi_range(age)
    ideal_min = bmi_min * (height_m * height_m)
    ideal_max = bmi_max * (height_m * height_m)
    return round(bmi, 2), round(ideal_min, 2), round(ideal_max, 2)


@app.post("/api/profile/update")
def update_profile(payload: ProfileUpdateRequest) -> dict[str, object]:
    username = require_known_user(payload.username)

    if payload.age is not None and (payload.age <= 0 or payload.age > 150):
        raise HTTPException(status_code=400, detail="Invalid age.")
    if payload.height_cm is not None and payload.height_cm <= 0:
        raise HTTPException(status_code=400, detail="Height must be positive.")
    if payload.weight_kg is not None and payload.weight_kg <= 0:
        raise HTTPException(status_code=400, detail="Weight must be positive.")
    if payload.target_weight_kg is not None and payload.target_weight_kg <= 0:
        raise HTTPException(status_code=400, detail="Target weight must be positive.")

    age = payload.age
    height = payload.height_cm
    weight = payload.weight_kg
    gender = payload.gender
    target = payload.target_weight_kg
    calorie_goal = payload.daily_calorie_goal

    if calorie_goal is not None and calorie_goal <= 0:
        raise HTTPException(status_code=400, detail="Calorie goal must be positive.")

    with get_connection(USER_DB_PATH) as conn:
        current = conn.execute(
            "SELECT age, height_cm, weight_kg, daily_calorie_goal FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    if current:
        if age is None:
            age = current[0]
        if height is None:
            height = current[1]
        if weight is None:
            weight = current[2]
        if calorie_goal is None:
            calorie_goal = current[3]

    if age and height and weight:
        bmi, ideal_min, ideal_max = calculate_body_metrics(age, height, weight)
    else:
        bmi, ideal_min, ideal_max = None, None, None

    with get_connection(USER_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE users
            SET age = ?,
                height_cm = ?,
                weight_kg = ?,
                bmi = ?,
                ideal_weight_min = ?,
                ideal_weight_max = ?,
                target_weight_kg = ?,
                gender = ?,
                daily_calorie_goal = ?
            WHERE username = ?
            """,
            (age, height, weight, bmi, ideal_min, ideal_max, target, gender, calorie_goal, username),
        )
        conn.commit()

    return {
        "message": "Profile updated.",
        "profile": {
            "username": username,
            "age": age,
            "height_cm": height,
            "weight_kg": weight,
            "bmi": bmi,
            "ideal_weight_min": ideal_min,
            "ideal_weight_max": ideal_max,
            "target_weight_kg": target,
            "gender": gender,
            "daily_calorie_goal": calorie_goal,
        }
    }


@app.post("/api/sleep/add")
def add_sleep_record(payload: SleepRecordRequest) -> dict[str, object]:
    username = require_known_user(payload.username)
    if payload.sleep_hours <= 0:
        raise HTTPException(status_code=400, detail="sleep_hours must be positive.")
    today = str(date.today())
    with get_connection(SLEEP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO sleep_records (username, record_date, sleep_hours)
            VALUES (?, ?, ?)
            """,
            (username, today, float(payload.sleep_hours)),
        )
        conn.commit()
        total_row = conn.execute(
            """
            SELECT COALESCE(SUM(sleep_hours), 0)
            FROM sleep_records
            WHERE username = ? AND record_date = ?
            """,
            (username, today),
        ).fetchone()
    return {"message": "Sleep record added.", "date": today, "total_sleep_hours": round(float(total_row[0]), 2)}


@app.get("/api/sleep/logs/{username}")
def get_sleep_logs_today(username: str) -> dict[str, object]:
    normalized = require_known_user(username)
    today = str(date.today())
    rows: list[dict[str, object]] = []
    with get_connection(SLEEP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        try:
            result = conn.execute(
                "SELECT id, sleep_hours FROM sleep_records WHERE username = ? AND record_date = ? ORDER BY id ASC",
                (normalized, today),
            ).fetchall()
            for r in result:
                rows.append({"id": r["id"], "sleep_hours": float(r["sleep_hours"])})
        except sqlite3.OperationalError:
            pass
    return {"logs": rows}


@app.delete("/api/sleep/logs/{log_id}")
def delete_sleep_log(log_id: int) -> dict[str, object]:
    with get_connection(SLEEP_DB_PATH) as conn:
        cursor = conn.execute("SELECT id FROM sleep_records WHERE id = ?", (log_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Sleep record not found.")
        conn.execute("DELETE FROM sleep_records WHERE id = ?", (log_id,))
        conn.commit()
    return {"message": "Sleep record deleted.", "log_id": log_id}


@app.post("/api/water/add")
def add_water_record(payload: WaterRecordRequest) -> dict[str, object]:
    username = require_known_user(payload.username)
    if payload.water_ml <= 0:
        raise HTTPException(status_code=400, detail="water_ml must be positive.")
    today = str(date.today())
    with get_connection(WATER_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO water_records (username, record_date, water_ml)
            VALUES (?, ?, ?)
            """,
            (username, today, float(payload.water_ml)),
        )
        conn.commit()
        total_row = conn.execute(
            """
            SELECT COALESCE(SUM(water_ml), 0)
            FROM water_records
            WHERE username = ? AND record_date = ?
            """,
            (username, today),
        ).fetchone()
    return {"message": "Water record added.", "date": today, "total_water_ml": round(float(total_row[0]), 2)}


@app.get("/api/water/logs/{username}")
def get_water_logs_today(username: str) -> dict[str, object]:
    normalized = require_known_user(username)
    today = str(date.today())
    rows: list[dict[str, object]] = []
    with get_connection(WATER_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        try:
            result = conn.execute(
                "SELECT id, water_ml FROM water_records WHERE username = ? AND record_date = ? ORDER BY id ASC",
                (normalized, today),
            ).fetchall()
            for r in result:
                rows.append({"id": r["id"], "water_ml": float(r["water_ml"])})
        except sqlite3.OperationalError:
            pass
    return {"logs": rows}


@app.delete("/api/water/logs/{log_id}")
def delete_water_log(log_id: int) -> dict[str, object]:
    with get_connection(WATER_DB_PATH) as conn:
        cursor = conn.execute("SELECT id FROM water_records WHERE id = ?", (log_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Water record not found.")
        conn.execute("DELETE FROM water_records WHERE id = ?", (log_id,))
        conn.commit()
    return {"message": "Water record deleted.", "log_id": log_id}


@app.post("/api/calories/add")
def add_calorie_record(payload: CalorieRecordRequest) -> dict[str, object]:
    username = require_known_user(payload.username)
    if payload.weight_grams <= 0 or payload.calories <= 0:
        raise HTTPException(status_code=400, detail="weight_grams and calories must be positive.")
    food_name = payload.food_name.strip()
    if not food_name:
        raise HTTPException(status_code=400, detail="food_name cannot be empty.")
    today = str(date.today())
    with get_connection(CALORIE_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO daily_records (username, record_date, food_name, weight_grams, calories)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, today, food_name, float(payload.weight_grams), float(payload.calories)),
        )
        conn.commit()
        total_row = conn.execute(
            """
            SELECT COALESCE(SUM(calories), 0)
            FROM daily_records
            WHERE username = ? AND record_date = ?
            """,
            (username, today),
        ).fetchone()
    return {"message": "Calorie record added.", "date": today, "total_calories": round(float(total_row[0]), 2)}


@app.get("/api/calories/logs/{username}")
def get_calorie_logs_today(username: str) -> dict[str, object]:
    normalized = require_known_user(username)
    today = str(date.today())
    rows: list[dict[str, object]] = []
    with get_connection(CALORIE_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        try:
            result = conn.execute(
                "SELECT id, food_name, weight_grams, calories FROM daily_records WHERE username = ? AND record_date = ? ORDER BY id ASC",
                (normalized, today),
            ).fetchall()
            for r in result:
                rows.append({
                    "id": r["id"],
                    "food_name": r["food_name"],
                    "weight_grams": float(r["weight_grams"]),
                    "calories": float(r["calories"]),
                })
        except sqlite3.OperationalError:
            pass
    return {"logs": rows}


@app.delete("/api/calories/logs/{log_id}")
def delete_calorie_log(log_id: int) -> dict[str, object]:
    with get_connection(CALORIE_DB_PATH) as conn:
        cursor = conn.execute("SELECT id FROM daily_records WHERE id = ?", (log_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Calorie record not found.")
        conn.execute("DELETE FROM daily_records WHERE id = ?", (log_id,))
        conn.commit()
    return {"message": "Calorie record deleted.", "log_id": log_id}


@app.post("/api/steps/add")
def add_step_record(payload: StepRecordRequest) -> dict[str, object]:
    username = require_known_user(payload.username)
    if payload.steps <= 0:
        raise HTTPException(status_code=400, detail="steps must be positive.")
    today = str(date.today())
    with get_connection(STEP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO step_records (username, record_date, steps)
            VALUES (?, ?, ?)
            """,
            (username, today, int(payload.steps)),
        )
        conn.commit()
        total_row = conn.execute(
            """
            SELECT COALESCE(SUM(steps), 0)
            FROM step_records
            WHERE username = ? AND record_date = ?
            """,
            (username, today),
        ).fetchone()
    return {"message": "Step record added.", "date": today, "total_steps": int(total_row[0])}


@app.get("/api/steps/logs/{username}")
def get_step_logs_today(username: str) -> dict[str, object]:
    normalized = require_known_user(username)
    today = str(date.today())
    rows: list[dict[str, object]] = []
    with get_connection(STEP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        try:
            result = conn.execute(
                "SELECT id, steps FROM step_records WHERE username = ? AND record_date = ? ORDER BY id ASC",
                (normalized, today),
            ).fetchall()
            for r in result:
                rows.append({"id": r["id"], "steps": int(r["steps"])})
        except sqlite3.OperationalError:
            pass
    return {"logs": rows}


@app.delete("/api/steps/logs/{log_id}")
def delete_step_log(log_id: int) -> dict[str, object]:
    with get_connection(STEP_DB_PATH) as conn:
        cursor = conn.execute("SELECT id FROM step_records WHERE id = ?", (log_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Step record not found.")
        conn.execute("DELETE FROM step_records WHERE id = ?", (log_id,))
        conn.commit()
    return {"message": "Step record deleted.", "log_id": log_id}


@app.post("/api/exercise/add")
def add_exercise_record(payload: ExerciseRecordRequest) -> dict[str, object]:
    username = require_known_user(payload.username)
    exercise_name = payload.exercise_name.strip()
    unit = payload.unit.strip().lower()
    if not exercise_name:
        raise HTTPException(status_code=400, detail="exercise_name cannot be empty.")
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive.")
    if unit not in {"reps", "seconds"}:
        raise HTTPException(status_code=400, detail="unit must be 'reps' or 'seconds'.")

    today = str(date.today())
    now_ts = date.today().isoformat()
    with get_connection(SPOR_DB_PATH) as conn:
        existing = conn.execute(
            """
            SELECT id, total_amount
            FROM exercise_daily_logs
            WHERE username = ? AND exercise_name = ? AND log_date = ? AND unit = ?
            LIMIT 1
            """,
            (username, exercise_name, today, unit),
        ).fetchone()

        if existing:
            updated_total = float(existing[1]) + float(payload.amount)
            conn.execute(
                """
                UPDATE exercise_daily_logs
                SET total_amount = ?, updated_at = ?
                WHERE id = ?
                """,
                (updated_total, now_ts, int(existing[0])),
            )
        else:
            conn.execute(
                """
                INSERT INTO exercise_daily_logs
                (username, exercise_name, log_date, total_amount, unit, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (username, exercise_name, today, float(payload.amount), unit, now_ts, now_ts),
            )
        conn.commit()

        total_row = conn.execute(
            """
            SELECT COALESCE(SUM(total_amount), 0)
            FROM exercise_daily_logs
            WHERE username = ? AND log_date = ? AND exercise_name = ? AND unit = ?
            """,
            (username, today, exercise_name, unit),
        ).fetchone()
    return {
        "message": "Exercise record added.",
        "date": today,
        "exercise_name": exercise_name,
        "unit": unit,
        "total_amount_for_exercise_today": round(float(total_row[0]), 2),
    }


@app.get("/api/exercise/logs/{username}")
def get_exercise_logs_today(username: str) -> dict[str, object]:
    """Return today's exercise logs with their row IDs so they can be deleted."""
    normalized = require_known_user(username)
    today = str(date.today())
    rows: list[dict[str, object]] = []
    if os.path.exists(SPOR_DB_PATH):
        with get_connection(SPOR_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            try:
                result = conn.execute(
                    """
                    SELECT id, exercise_name, total_amount, unit
                    FROM exercise_daily_logs
                    WHERE username = ? AND log_date = ?
                    ORDER BY id ASC
                    """,
                    (normalized, today),
                ).fetchall()
                for r in result:
                    rows.append({
                        "id": r["id"],
                        "exercise_name": r["exercise_name"],
                        "total_amount": float(r["total_amount"]),
                        "unit": r["unit"],
                    })
            except sqlite3.OperationalError:
                pass
    return {"logs": rows}


@app.delete("/api/exercise/logs/{log_id}")
def delete_exercise_log(log_id: int) -> dict[str, object]:
    """Delete a single exercise log row by its ID."""
    if not os.path.exists(SPOR_DB_PATH):
        raise HTTPException(status_code=404, detail="Exercise database not found.")
    with get_connection(SPOR_DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT id FROM exercise_daily_logs WHERE id = ?",
            (log_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Log entry not found.")
        conn.execute("DELETE FROM exercise_daily_logs WHERE id = ?", (log_id,))
        conn.commit()
    return {"message": "Log deleted.", "log_id": log_id}


@app.get("/api/exercise-stats/{username}")
def get_exercise_stats(username: str) -> dict[str, object]:
    normalized = require_known_user(username)
    stats: dict[str, object] = {}
    if os.path.exists(SPOR_DB_PATH):
        with get_connection(SPOR_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT exercise_name, SUM(total_amount) as total, unit
                    FROM exercise_daily_logs
                    WHERE username = ?
                    GROUP BY exercise_name, unit
                    ORDER BY exercise_name ASC
                    """,
                    (normalized,),
                ).fetchall()
                for row in rows:
                    name = row["exercise_name"]
                    stats[name] = {
                        "total": round(float(row["total"]), 2),
                        "unit": row["unit"],
                    }
            except sqlite3.OperationalError:
                pass
    return {"stats": stats}


@app.get("/api/steps/{username}")
def get_step_stats(username: str, days: int = 7) -> dict[str, object]:
    normalized = require_known_user(username)
    today = str(date.today())
    with get_connection(STEP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT record_date, COALESCE(SUM(steps), 0) as total
                FROM step_records
                WHERE username = ? AND record_date >= date('now', ?)
                GROUP BY record_date
                ORDER BY record_date ASC
                """,
                (normalized, f"-{days} days"),
            ).fetchall()
            history = [{"date": row["record_date"], "steps": int(row["total"])} for row in rows]
        except sqlite3.OperationalError:
            history = []

    # Today's total
    today_row = conn.execute(
        "SELECT COALESCE(SUM(steps), 0) FROM step_records WHERE username = ? AND record_date = ?",
        (normalized, today),
    ).fetchone()
    today_steps = int(today_row[0]) if today_row else 0

    return {
        "username": normalized,
        "today_steps": today_steps,
        "history": history,
    }


@app.get("/api/exercise-history/{username}")
def get_exercise_history(username: str, days: int = 7) -> dict[str, object]:
    normalized = require_known_user(username)
    result: dict[str, list[dict[str, object]]] = {}
    if not os.path.exists(SPOR_DB_PATH):
        return {"history": result}
    with get_connection(SPOR_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT exercise_name, log_date, SUM(total_amount) as total, unit
                FROM exercise_daily_logs
                WHERE username = ?
                  AND log_date >= date('now', ?)
                GROUP BY exercise_name, log_date, unit
                ORDER BY log_date ASC
                """,
                (normalized, f"-{days} days"),
            ).fetchall()
            for row in rows:
                name = row["exercise_name"]
                if name not in result:
                    result[name] = []
                result[name].append({
                    "date": row["log_date"],
                    "total": round(float(row["total"]), 2),
                    "unit": row["unit"],
                })
        except sqlite3.OperationalError:
            pass
    return {"history": result}


@app.get("/api/monthly-stats/{username}")
def get_monthly_stats(username: str, year: int = 0, month: int = 0) -> dict[str, object]:
    normalized = require_known_user(username)
    today = date.today()
    if year == 0:
        year = today.year
    if month == 0:
        month = today.month

    # Get user's calorie goal
    calorie_goal = 2000
    with get_connection(USER_DB_PATH) as conn:
        row = conn.execute(
            "SELECT daily_calorie_goal FROM users WHERE username = ?",
            (normalized,),
        ).fetchone()
        if row and row[0]:
            calorie_goal = row[0]

    # Build date range for the month
    month_str = f"{year:04d}-{month:02d}"

    # Get exercise data per day
    exercise_days: set[str] = set()
    if os.path.exists(SPOR_DB_PATH):
        with get_connection(SPOR_DB_PATH) as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT log_date
                    FROM exercise_daily_logs
                    WHERE username = ? AND log_date LIKE ?
                    GROUP BY log_date
                    HAVING SUM(total_amount) > 0
                    """,
                    (normalized, month_str + "%"),
                ).fetchall()
                for row in rows:
                    exercise_days.add(row[0])
            except sqlite3.OperationalError:
                pass

    # Get calorie data per day
    calorie_per_day: dict[str, float] = {}
    if os.path.exists(CALORIE_DB_PATH):
        with get_connection(CALORIE_DB_PATH) as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT record_date, COALESCE(SUM(calories), 0)
                    FROM daily_records
                    WHERE username = ? AND record_date LIKE ?
                    GROUP BY record_date
                    """,
                    (normalized, month_str + "%"),
                ).fetchall()
                for row in rows:
                    calorie_per_day[row[0]] = round(float(row[1]), 2)
            except sqlite3.OperationalError:
                pass

    # Build per-day result
    days: dict[str, dict[str, object]] = {}
    for day_str in exercise_days:
        cal = calorie_per_day.get(day_str, 0)
        days[day_str] = {
            "exercised": True,
            "calories": cal,
            "calorie_goal": calorie_goal,
            "goal_met": cal >= calorie_goal,
        }
    for day_str, cal in calorie_per_day.items():
        if day_str not in days:
            days[day_str] = {
                "exercised": False,
                "calories": cal,
                "calorie_goal": calorie_goal,
                "goal_met": cal >= calorie_goal,
            }

    return {
        "year": year,
        "month": month,
        "calorie_goal": calorie_goal,
        "days": days,
    }


@app.get("/api/daily-summary/{username}")
def get_daily_summary(username: str) -> dict[str, object]:
    normalized = require_known_user(username)
    today = str(date.today())
    with get_connection(SLEEP_DB_PATH) as sleep_conn:
        sleep_total = sleep_conn.execute(
            "SELECT COALESCE(SUM(sleep_hours), 0) FROM sleep_records WHERE username = ? AND record_date = ?",
            (normalized, today),
        ).fetchone()[0]
    with get_connection(WATER_DB_PATH) as water_conn:
        water_total = water_conn.execute(
            "SELECT COALESCE(SUM(water_ml), 0) FROM water_records WHERE username = ? AND record_date = ?",
            (normalized, today),
        ).fetchone()[0]
    with get_connection(CALORIE_DB_PATH) as calorie_conn:
        calorie_total = calorie_conn.execute(
            "SELECT COALESCE(SUM(calories), 0) FROM daily_records WHERE username = ? AND record_date = ?",
            (normalized, today),
        ).fetchone()[0]
    with get_connection(STEP_DB_PATH) as step_conn:
        step_total = step_conn.execute(
            "SELECT COALESCE(SUM(steps), 0) FROM step_records WHERE username = ? AND record_date = ?",
            (normalized, today),
        ).fetchone()[0]

    # Exercise calorie burn and BMR from calorie_db
    exercise_kcal = 0.0
    bmr_kcal = 0.0
    if os.path.exists(CALORIE_DB_PATH):
        try:
            with get_connection(CALORIE_DB_PATH) as cal_conn:
                row = cal_conn.execute(
                    "SELECT total_exercise_kcal, bmr_kcal_per_day FROM exercise_calorie_daily_summary WHERE username = ? AND log_date = ?",
                    (normalized, today),
                ).fetchone()
                if row:
                    exercise_kcal = float(row[0]) if row[0] else 0.0
                    bmr_kcal = float(row[1]) if row[1] else 0.0
        except sqlite3.OperationalError:
            pass

    # Step calorie estimate using user's weight
    step_calories = 0.0
    if step_total > 0:
        try:
            with get_connection(USER_DB_PATH) as user_conn:
                row = user_conn.execute(
                    "SELECT weight_kg FROM users WHERE username = ?", (normalized,)
                ).fetchone()
                if row and row[0]:
                    weight_kg = float(row[0])
                    step_calories = round(3.0 * weight_kg * (step_total / 7000.0), 1)
        except (sqlite3.OperationalError, ValueError, TypeError):
            pass

    exercise_rows: list[dict[str, object]] = []
    if os.path.exists(SPOR_DB_PATH):
        with get_connection(SPOR_DB_PATH) as spor_conn:
            spor_conn.row_factory = sqlite3.Row
            try:
                rows = spor_conn.execute(
                    """
                    SELECT exercise_name, total_amount, unit
                    FROM exercise_daily_logs
                    WHERE username = ? AND log_date = ?
                    ORDER BY exercise_name ASC
                    """,
                    (normalized, today),
                ).fetchall()
                exercise_rows = [dict(r) for r in rows]
            except sqlite3.OperationalError:
                exercise_rows = []

    return {
        "username": normalized,
        "date": today,
        "sleep_hours": round(float(sleep_total), 2),
        "water_ml": round(float(water_total), 2),
        "calories": round(float(calorie_total), 2),
        "steps": int(step_total),
        "exercise_kcal": round(exercise_kcal, 1),
        "step_calories": round(step_calories, 1),
        "bmr_kcal": round(bmr_kcal, 1),
        "total_burn": round(exercise_kcal + step_calories + bmr_kcal, 1),
        "exercise_logs": exercise_rows,
    }


@app.get("/api/ai-coach/{username}")
def get_ai_coach_report(username: str) -> dict[str, object]:
    """Return the AI Coach personalised report for the given user."""
    normalized = require_known_user(username)
    try:
        from ai_coach.ai_coach import generate_coach_report
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"AI Coach module not available: {exc}",
        )
    try:
        report = generate_coach_report(normalized)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"AI Coach report generation failed: {exc}",
        )
    return {"report": report, "username": normalized}


def _clean_llm_text(text: str) -> str:
    """Fix common spacing/punctuation issues from small LLM output."""
    # Ensure space after sentence-ending punctuation if missing
    import re as _re
    text = _re.sub(r'([.!?:;,])([A-Za-z])', r'\1 \2', text)
    # Ensure space after closing paren/bracket if followed by a letter
    text = _re.sub(r'([\)\]])([A-Za-z])', r'\1 \2', text)
    # Collapse multiple spaces
    text = _re.sub(r' +', ' ', text)
    return text.strip()


@app.post("/api/ai-coach/chat")
def ai_coach_chat(payload: AICoachChatRequest) -> dict[str, object]:
    """Chat with the AI Coach — uses Ollama (local LLM) with the user's live fitness data."""
    normalized = require_known_user(payload.username)

    # Get user's live fitness data
    try:
        from ai_coach.ai_coach import collect_user_data
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"AI Coach module not available: {exc}")

    try:
        data = collect_user_data(normalized)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load user data: {exc}")

    p = data["profile"]
    profile_block = (
        f"Age: {p.get('age', 'N/A')}\n"
        f"Weight: {p.get('weight_kg', 'N/A')} kg\n"
        f"Height: {p.get('height_cm', 'N/A')} cm\n"
        f"BMI: {p.get('bmi', 'N/A')}\n"
        f"Target weight: {p.get('target_weight_kg', 'N/A')} kg\n"
        f"Gender: {p.get('gender', 'N/A')}\n"
        f"Daily calorie goal: {p.get('daily_calorie_goal', 'N/A')} kcal"
    )

    exercise_today = data["today_exercise"]
    if exercise_today:
        ex_lines = []
        for name, amount, unit in exercise_today:
            label = "sec" if unit == "seconds" else "reps"
            ex_lines.append(f"  - {name}: {float(amount):.1f} {label}")
        exercise_block = "\n".join(ex_lines)
    else:
        exercise_block = "  None logged yet today."

    # Fetch all exercise names ever logged in the system
    all_exercises = set()
    try:
        with get_connection(SPOR_DB_PATH) as conn:
            rows = conn.execute(
                "SELECT DISTINCT exercise_name FROM exercise_daily_logs ORDER BY exercise_name"
            ).fetchall()
            all_exercises = {row[0] for row in rows}
    except Exception:
        pass
    # Always include the built-in exercises even if never logged yet
    all_exercises.update(["Push-up", "Squat", "Plank", "Sit-up", "March", "Arm Raise", "Jump"])
    exercises_list = sorted(all_exercises)

    system_prompt = (
        "You are an expert AI fitness coach. You have access to the user's live data below. "
        "Answer questions concisely and helpfully. Give specific, actionable advice based on "
        "their actual numbers. Keep responses under 4-5 sentences unless asked for detail.\n\n"
        f"TODAY'S DATE: {data['date']}\n\n"
        f"=== USER PROFILE ===\n{profile_block}\n\n"
        f"=== TODAY'S EXERCISE ===\n{exercise_block}\n\n"
        f"=== TODAY'S NUTRITION ===\n"
        f"  Calories consumed: {data['calorie_intake']:.0f} / {data['calorie_goal']:.0f} kcal\n"
        f"  Exercise calories burned: {data['exercise_kcal']:.0f} kcal\n"
        f"  BMR: {data['bmr']:.0f} kcal/day\n\n"
        f"=== TODAY'S SLEEP ===\n"
        f"  {data['sleep_hours']:.1f} hours\n\n"
        f"=== TODAY'S WATER ===\n"
        f"  {data['water_ml']:.0f} ml\n\n"
        f"=== TODAY'S STEPS ===\n"
        f"  {data['steps']:,} steps\n\n"
        f"Weekly exercise minutes (est.): {data['weekly_minutes']:.0f}\n"
        f"Exercise days this week: {data['exercise_days']}\n"
        f"\n=== AVAILABLE EXERCISES ===\n"
        f"The system can only track these exercises: {', '.join(exercises_list)}.\n"
        f"IMPORTANT: ONLY recommend exercises from this list. Do NOT suggest any other exercises."
    )

    # Build Ollama message format: system prompt + conversation history
    ollama_messages = [
        {"role": "system", "content": system_prompt},
    ]
    for msg in payload.history:
        ollama_messages.append({
            "role": msg.role,  # "user" or "assistant"
            "content": msg.text,
        })
    ollama_messages.append({"role": "user", "content": payload.message})

    # Try Ollama with retries, fall back to local coach on exhaustion
    reply = None
    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                OLLAMA_CHAT_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 512,
                    },
                },
                timeout=60,
            )
            resp.raise_for_status()
            result = resp.json()
            reply = result.get("message", {}).get("content", "")
            if reply:
                # Clean up common spacing issues from small LLMs
                reply = _clean_llm_text(reply)
                break
        except requests.exceptions.RequestException as exc:
            last_error = str(exc)
            if attempt < max_retries - 1:
                sleep_sec = 2 ** attempt
                time.sleep(sleep_sec)
                continue

    # Fallback to local rule-based coach if Ollama failed after all retries
    if reply is None:
        try:
            from ai_coach.ai_coach import generate_coach_report
            local_report = generate_coach_report(normalized)
            reply = (
                "(Local AI Coach report — Ollama is unavailable)\n\n"
                + local_report
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"AI Coach unavailable: Gemini error ({last_error}). Local coach also failed: {exc}",
            )

    return {"response": reply}


# ---------------------------------------------------------------------------
# AI Coach — Chat History Persistence
# ---------------------------------------------------------------------------


@app.get("/api/ai-coach/chats/{username}")
def list_coach_chats(username: str) -> dict[str, object]:
    """Return all chats for a user, with last message preview."""
    normalized = require_known_user(username)
    chats: list[dict[str, object]] = []
    with get_connection(COACH_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at,
                       (SELECT text FROM ai_coach_messages
                        WHERE chat_id = c.id ORDER BY id DESC LIMIT 1) AS last_message,
                       (SELECT COUNT(*) FROM ai_coach_messages
                        WHERE chat_id = c.id) AS message_count
                FROM ai_coach_chats c
                WHERE c.username = ?
                ORDER BY c.updated_at DESC
                """,
                (normalized,),
            ).fetchall()
            for row in rows:
                chats.append({
                    "id": row["id"],
                    "title": row["title"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "last_message": (row["last_message"][:80] + "…")
                                   if row["last_message"] and len(row["last_message"]) > 80
                                   else (row["last_message"] or ""),
                    "message_count": row["message_count"],
                })
        except sqlite3.OperationalError:
            pass
    return {"chats": chats}


@app.post("/api/ai-coach/chats")
def create_coach_chat(payload: CreateChatRequest) -> dict[str, object]:
    """Create a new chat session."""
    username = require_known_user(payload.username)
    now = datetime.utcnow().isoformat()
    title = (payload.title or "New Chat").strip()
    with get_connection(COACH_DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO ai_coach_chats (username, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (username, title, now, now),
        )
        conn.commit()
        chat_id = cursor.lastrowid
    return {"chat_id": chat_id, "title": title, "created_at": now}


@app.get("/api/ai-coach/chats/{chat_id}/messages")
def get_coach_chat_messages(chat_id: int) -> dict[str, object]:
    """Return all messages for a chat."""
    messages: list[dict[str, object]] = []
    with get_connection(COACH_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT id, role, text, created_at
                FROM ai_coach_messages
                WHERE chat_id = ?
                ORDER BY id ASC
                """,
                (chat_id,),
            ).fetchall()
            for row in rows:
                messages.append({
                    "id": row["id"],
                    "role": row["role"],
                    "text": row["text"],
                    "created_at": row["created_at"],
                })
        except sqlite3.OperationalError:
            pass
    return {"messages": messages}


@app.post("/api/ai-coach/chats/{chat_id}/messages")
def add_coach_chat_message(chat_id: int, payload: AddMessageRequest) -> dict[str, object]:
    """Add a message to a chat and update its timestamp."""
    role = payload.role.strip().lower()
    if role not in ("user", "assistant"):
        raise HTTPException(status_code=400, detail="role must be 'user' or 'assistant'.")
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message text cannot be empty.")
    now = datetime.utcnow().isoformat()
    with get_connection(COACH_DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO ai_coach_messages (chat_id, role, text, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, role, text, now),
        )
        conn.execute(
            "UPDATE ai_coach_chats SET updated_at = ? WHERE id = ?",
            (now, chat_id),
        )
        conn.commit()
        msg_id = cursor.lastrowid
    return {"message_id": msg_id, "role": role, "created_at": now}


@app.put("/api/ai-coach/chats/{chat_id}/title")
def update_coach_chat_title(chat_id: int, payload: UpdateChatTitleRequest) -> dict[str, object]:
    """Update the title of a chat (e.g. auto-generated from first message)."""
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty.")
    now = datetime.utcnow().isoformat()
    with get_connection(COACH_DB_PATH) as conn:
        conn.execute(
            "UPDATE ai_coach_chats SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, chat_id),
        )
        conn.commit()
    return {"message": "Title updated.", "title": title}


@app.delete("/api/ai-coach/chats/{chat_id}")
def delete_coach_chat(chat_id: int) -> dict[str, object]:
    """Delete a chat and all its messages."""
    with get_connection(COACH_DB_PATH) as conn:
        cursor = conn.execute("SELECT id FROM ai_coach_chats WHERE id = ?", (chat_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Chat not found.")
        conn.execute("DELETE FROM ai_coach_messages WHERE chat_id = ?", (chat_id,))
        conn.execute("DELETE FROM ai_coach_chats WHERE id = ?", (chat_id,))
        conn.commit()
    return {"message": "Chat deleted.", "chat_id": chat_id}


CALORIE_SCRIPT = PROJECT_ROOT / "calorie" / "calorie_f.py"
SLEEP_SCRIPT = PROJECT_ROOT / "sleep" / "sleep_f.py"
WATER_SCRIPT = PROJECT_ROOT / "water" / "water_f.py"
STEP_SCRIPT = PROJECT_ROOT / "step" / "step_f.py"
CAMERA4_SCRIPT = PROJECT_ROOT / "camera4.py"


@app.post("/api/launch-pose-detection")
def launch_pose_detection(payload: ExerciseLaunchRequest) -> dict[str, object]:
    """Launch camera4.py with the logged-in username passed as argument."""
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")

    script_path = str(CAMERA4_SCRIPT.resolve())
    if not os.path.isfile(script_path):
        raise HTTPException(status_code=500, detail=f"camera4.py not found at {script_path}")

    try:
        subprocess.Popen([sys.executable, script_path, "--username", username])
        return {"message": "Pose detection launched successfully.", "username": username}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch pose detection: {e}")


@app.post("/api/launch-calorie")
def launch_calorie(payload: ExerciseLaunchRequest) -> dict[str, object]:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    script_path = str(CALORIE_SCRIPT.resolve())
    if not os.path.isfile(script_path):
        raise HTTPException(status_code=500, detail=f"calorie_f.py not found at {script_path}")
    try:
        subprocess.Popen([sys.executable, script_path, "--username", username])
        return {"message": "Calorie tracker launched.", "username": username}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch calorie tracker: {e}")


@app.post("/api/launch-sleep")
def launch_sleep(payload: ExerciseLaunchRequest) -> dict[str, object]:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    script_path = str(SLEEP_SCRIPT.resolve())
    if not os.path.isfile(script_path):
        raise HTTPException(status_code=500, detail=f"sleep_f.py not found at {script_path}")
    try:
        subprocess.Popen([sys.executable, script_path, "--username", username])
        return {"message": "Sleep tracker launched.", "username": username}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch sleep tracker: {e}")


@app.post("/api/launch-water")
def launch_water(payload: ExerciseLaunchRequest) -> dict[str, object]:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    script_path = str(WATER_SCRIPT.resolve())
    if not os.path.isfile(script_path):
        raise HTTPException(status_code=500, detail=f"water_f.py not found at {script_path}")
    try:
        subprocess.Popen([sys.executable, script_path, "--username", username])
        return {"message": "Water tracker launched.", "username": username}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch water tracker: {e}")


@app.post("/api/launch-step")
def launch_step(payload: ExerciseLaunchRequest) -> dict[str, object]:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    script_path = str(STEP_SCRIPT.resolve())
    if not os.path.isfile(script_path):
        raise HTTPException(status_code=500, detail=f"step_f.py not found at {script_path}")
    try:
        subprocess.Popen([sys.executable, script_path, "--username", username])
        return {"message": "Step tracker launched.", "username": username}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch step tracker: {e}")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
