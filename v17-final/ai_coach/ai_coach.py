"""
Simple AI Coach — reads all user data across databases and generates
personalized fitness, nutrition, hydration, and sleep recommendations.
"""

import sqlite3
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Database paths
# ---------------------------------------------------------------------------
USER_DB = r"C:\project_database\user_db.db"
SPOR_DB = r"C:\project_database\spor_db.db"
CALORIE_DB = r"C:\project_database\calorie_db.db"
SLEEP_DB = r"C:\project_database\sleep_db.db"
WATER_DB = r"C:\project_database\water_db.db"
STEP_DB = r"C:\project_database\step_db.db"

# ---------------------------------------------------------------------------
# Nutritional / health constants
# ---------------------------------------------------------------------------
WATER_ML_PER_KG = 33          # average recommendation
SLEEP_MIN = 7.0
SLEEP_MAX = 9.0
EXERCISE_MIN_PER_WEEK = 150   # minutes of moderate activity per WHO
STEPS_DAILY_TARGET = 10000    # general wellness recommendation


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def _fetchone(db, sql, params=()):
    try:
        with sqlite3.connect(db) as conn:
            return conn.execute(sql, params).fetchone()
    except sqlite3.OperationalError:
        return None


def _fetchall(db, sql, params=()):
    try:
        with sqlite3.connect(db) as conn:
            return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []


def collect_user_data(username: str) -> dict:
    """Gather every piece of data we have about *username*."""
    today = str(date.today())

    # --- Profile -----------------------------------------------------------
    row = _fetchone(
        USER_DB,
        "SELECT age, height_cm, weight_kg, bmi, ideal_weight_min, "
        "ideal_weight_max, target_weight_kg, gender, daily_calorie_goal "
        "FROM users WHERE username = ?",
        (username,),
    )
    profile = {
        "age": None, "height_cm": None, "weight_kg": None, "bmi": None,
        "ideal_weight_min": None, "ideal_weight_max": None,
        "target_weight_kg": None, "gender": None, "daily_calorie_goal": None,
    }
    if row:
        keys = list(profile.keys())
        for i, k in enumerate(keys):
            profile[k] = row[i]

    # --- Today's exercise --------------------------------------------------
    today_exercise = _fetchall(
        SPOR_DB,
        "SELECT exercise_name, total_amount, unit "
        "FROM exercise_daily_logs "
        "WHERE username = ? AND log_date = ? ORDER BY exercise_name",
        (username, today),
    )

    # --- Weekly exercise (last 7 days, including today) --------------------
    weekly_exercise = _fetchall(
        SPOR_DB,
        "SELECT exercise_name, SUM(total_amount), unit "
        "FROM exercise_daily_logs "
        "WHERE username = ? AND log_date >= date('now', '-6 days') "
        "GROUP BY exercise_name, unit ORDER BY exercise_name",
        (username,),
    )

    # Total minutes of exercise this week (approximate from known exercises)
    weekly_minutes = 0.0
    for name, amount, unit in weekly_exercise:
        if unit in ("minute", "minutes", "min", "dk", "dakika"):
            weekly_minutes += float(amount)
        elif unit in ("second", "seconds", "sn", "saniye", "sec"):
            weekly_minutes += float(amount) / 60.0
        elif unit in ("rep", "reps", "tekrar"):
            weekly_minutes += float(amount) * 2.5 / 60.0  # ~2.5 s/rep
        elif unit in ("hour", "hours", "saat", "hr"):
            weekly_minutes += float(amount) * 60.0

    # --- Calorie intake (today) -------------------------------------------
    cal_row = _fetchone(
        CALORIE_DB,
        "SELECT COALESCE(SUM(calories), 0) FROM daily_records "
        "WHERE username = ? AND record_date = ?",
        (username, today),
    )
    calorie_intake = float(cal_row[0]) if cal_row else 0.0

    # --- Calorie goal (from user profile or fallback) ----------------------
    calorie_goal = profile["daily_calorie_goal"] or 2000.0

    # --- Exercise calorie burn today ---------------------------------------
    burn_row = _fetchone(
        CALORIE_DB,
        "SELECT COALESCE(SUM(calories), 0) FROM exercise_calorie_logs "
        "WHERE username = ? AND log_date = ?",
        (username, today),
    )
    exercise_kcal = float(burn_row[0]) if burn_row else 0.0

    bmr_row = _fetchone(
        CALORIE_DB,
        "SELECT bmr_kcal_per_day FROM exercise_calorie_daily_summary "
        "WHERE username = ? AND log_date = ?",
        (username, today),
    )
    bmr = float(bmr_row[0]) if bmr_row else 0.0

    # --- Sleep (today) -----------------------------------------------------
    sleep_row = _fetchone(
        SLEEP_DB,
        "SELECT COALESCE(SUM(sleep_hours), 0) FROM sleep_records "
        "WHERE username = ? AND record_date = ?",
        (username, today),
    )
    sleep_hours = float(sleep_row[0]) if sleep_row else 0.0

    # --- Water (today) -----------------------------------------------------
    water_row = _fetchone(
        WATER_DB,
        "SELECT COALESCE(SUM(water_ml), 0) FROM water_records "
        "WHERE username = ? AND record_date = ?",
        (username, today),
    )
    water_ml = float(water_row[0]) if water_row else 0.0

    # --- Steps (today) ------------------------------------------------------
    step_row = _fetchone(
        STEP_DB,
        "SELECT COALESCE(SUM(steps), 0) FROM step_records "
        "WHERE username = ? AND record_date = ?",
        (username, today),
    )
    steps = int(step_row[0]) if step_row else 0

    # --- Weekly exercise frequency (how many unique days) ------------------
    freq_rows = _fetchall(
        SPOR_DB,
        "SELECT DISTINCT log_date FROM exercise_daily_logs "
        "WHERE username = ? AND log_date >= date('now', '-6 days')",
        (username,),
    )
    exercise_days = len(freq_rows)

    return {
        "username": username,
        "date": today,
        "profile": profile,
        "today_exercise": today_exercise,
        "weekly_exercise": weekly_exercise,
        "weekly_minutes": round(weekly_minutes, 1),
        "exercise_days": exercise_days,
        "calorie_intake": calorie_intake,
        "calorie_goal": calorie_goal,
        "exercise_kcal": exercise_kcal,
        "bmr": bmr,
        "sleep_hours": sleep_hours,
        "water_ml": water_ml,
        "steps": steps,
    }


# ---------------------------------------------------------------------------
# Rule-based analysis & recommendation engine
# ---------------------------------------------------------------------------

def _has_profile(profile: dict) -> bool:
    return all(profile.get(k) is not None for k in ("age", "height_cm", "weight_kg"))


def generate_coach_report(username: str) -> str:
    """Return a plain-text fitness report with personalised advice."""
    d = collect_user_data(username)
    profile = d["profile"]
    lines = []
    sep = "─" * 50

    lines.append(f"  AI COACH REPORT")
    lines.append(f"  {d['date']}  —  {d['username']}")
    lines.append(sep)

    # ── Profile check ────────────────────────────────────────────────────
    if not _has_profile(profile):
        lines.append("")
        lines.append("  WARNING: Profile incomplete — set your age, height")
        lines.append("  and weight in the User Profile for personalised advice.")
        lines.append(sep)
        return "\n".join(lines)

    age = profile["age"]
    weight = profile["weight_kg"]
    height = profile["height_cm"]
    bmi = profile["bmi"]
    bmi_min = profile["ideal_weight_min"]
    bmi_max = profile["ideal_weight_max"]
    target = profile["target_weight_kg"]
    gender = profile.get("gender") or "Unknown"

    # ── Body metrics ─────────────────────────────────────────────────────
    lines.append("")
    lines.append(f"  BODY METRICS")
    lines.append(f"  Age: {age}  |  Weight: {weight} kg  |  Height: {height} cm")
    if bmi:
        lines.append(f"  BMI: {bmi:.1f}  (healthy range: {bmi_min:.1f}–{bmi_max:.1f} kg)")
        if bmi < 18.5:
            lines.append("  -> Underweight. Consider a nutrient-dense diet to reach a")
            lines.append("     healthier weight.")
        elif bmi < 25:
            lines.append("  -> Healthy weight range. Great work keeping balanced!")
        elif bmi < 30:
            lines.append("  -> Overweight. A slight calorie deficit + regular exercise")
            lines.append("     can help move toward the ideal range.")
        else:
            lines.append("  -> Obese range. Please consult a healthcare professional")
            lines.append("     for a safe, structured plan.")
    if target:
        diff = target - weight
        if abs(diff) < 1:
            lines.append(f"  Target: {target} kg — you're right on target!")
        elif diff > 0:
            lines.append(f"  Target: {target} kg (gain {diff:.1f} kg more)")
        else:
            lines.append(f"  Target: {target} kg (lose {abs(diff):.1f} kg more)")

    # ── Water ────────────────────────────────────────────────────────────
    lines.append("")
    lines.append(f"  HYDRATION")
    water_goal = weight * WATER_ML_PER_KG
    water_pct = (d["water_ml"] / water_goal * 100) if water_goal else 0
    lines.append(f"  Today: {d['water_ml']:.0f} ml / {water_goal:.0f} ml ({water_pct:.0f}%)")
    if water_pct >= 90:
        lines.append("  -> Good hydration! Keep this up.")
    elif water_pct >= 60:
        lines.append(f"  -> Drink {water_goal - d['water_ml']:.0f} ml more today.")
    else:
        lines.append(f"  -> Low water intake! Aim for {water_goal:.0f} ml daily.")
        lines.append("     Spread intake throughout the day.")

    # ── Sleep ────────────────────────────────────────────────────────────
    lines.append("")
    lines.append(f"  SLEEP")
    lines.append(f"  Today: {d['sleep_hours']:.1f} h  (recommended: {SLEEP_MIN}–{SLEEP_MAX} h)")
    if d["sleep_hours"] >= SLEEP_MIN and d["sleep_hours"] <= SLEEP_MAX:
        lines.append("  -> You're in the sweet spot! Quality sleep aids recovery.")
    elif d["sleep_hours"] < SLEEP_MIN and d["sleep_hours"] > 0:
        missing = SLEEP_MIN - d["sleep_hours"]
        lines.append(f"  -> You're {missing:.1f} h short. Prioritise an earlier bedtime")
        lines.append("     — sleep is when your body repairs muscle.")
    elif d["sleep_hours"] > SLEEP_MAX:
        lines.append("  -> You slept more than 9 h. While rest is good, oversleeping")
        lines.append("     can leave you groggy. Try a consistent wake-up time.")
    else:
        lines.append("  -> No sleep logged today. Log before bed!")

    # ── Steps ────────────────────────────────────────────────────────────
    lines.append("")
    lines.append(f"  STEPS")
    step_calories = round(
        3.0 * weight * (d["steps"] / 7000.0), 1
    ) if weight and d["steps"] > 0 else 0.0
    line = f"  Today: {d['steps']:,} / {STEPS_DAILY_TARGET:,} steps"
    if step_calories > 0:
        line += f"  (~{step_calories:.0f} kcal burned)"
    lines.append(line)
    if d["steps"] >= STEPS_DAILY_TARGET:
        lines.append("  -> You hit 10,000 steps! Great for cardiovascular health.")
    elif d["steps"] >= 7000:
        left = STEPS_DAILY_TARGET - d["steps"]
        lines.append(f"  -> Just {left:,} more steps to hit 10k. A short walk will do it.")
    elif d["steps"] >= 4000:
        left = STEPS_DAILY_TARGET - d["steps"]
        lines.append(f"  -> {left:,} steps to go. Try a brisk 20-min walk this evening.")
    elif d["steps"] > 0:
        lines.append("  -> Low step count. Aim for short walks throughout the day.")
    else:
        lines.append("  -> No steps logged today. Every step counts — start tracking!")

    # ── Calories ─────────────────────────────────────────────────────────
    lines.append("")
    lines.append(f"  NUTRITION")
    total_burn = d["bmr"] + d["exercise_kcal"]
    if d["bmr"] > 0:
        lines.append(f"  BMR (resting): {d['bmr']:.0f} kcal/day")
        lines.append(f"  Exercise burn: {d['exercise_kcal']:.0f} kcal")
        lines.append(f"  Estimated total burn: {total_burn:.0f} kcal")
    lines.append(f"  Intake: {d['calorie_intake']:.0f} / {d['calorie_goal']:.0f} kcal")
    if d["calorie_intake"] <= 0:
        lines.append("  -> No food logged. Log your meals to track nutrition.")
    elif d["calorie_intake"] < d["calorie_goal"] * 0.85:
        deficit = d["calorie_goal"] - d["calorie_intake"]
        lines.append(f"  -> You're {deficit:.0f} kcal under your goal. Eat enough to")
        lines.append("     fuel your activity level!")
    elif d["calorie_intake"] > d["calorie_goal"] * 1.15:
        surplus = d["calorie_intake"] - d["calorie_goal"]
        lines.append(f"  -> You're {surplus:.0f} kcal over your goal today.")
        if target and weight > target:
            lines.append("     Consider a lighter dinner or extra movement.")
    else:
        lines.append("  -> Calorie intake is on target.")

    # ── Exercise ─────────────────────────────────────────────────────────
    lines.append("")
    lines.append(f"  EXERCISE")
    if d["today_exercise"]:
        lines.append("  Today's activity:")
        for name, amount, unit in d["today_exercise"]:
            if unit == "seconds":
                lines.append(f"    {name}: {float(amount):.0f} sec")
            else:
                lines.append(f"    {name}: {int(float(amount))} reps")
    else:
        lines.append("  No exercise logged today.")

    lines.append(f"  Weekly exercise minutes (est.): {d['weekly_minutes']:.0f}")
    lines.append(f"  Exercise days this week: {d['exercise_days']}")
    if d["weekly_minutes"] >= EXERCISE_MIN_PER_WEEK:
        lines.append("  -> You meet the WHO recommendation (150 min/week)!")
    else:
        short = EXERCISE_MIN_PER_WEEK - d["weekly_minutes"]
        lines.append(f"  -> {short:.0f} more minutes this week to hit the 150 min target.")

    # ── Output target-based advice ───────────────────────────────────────
    lines.append("")
    lines.append(f"  COACH'S TIP OF THE DAY")
    if d["steps"] < 5000 and d["steps"] > 0:
        lines.append("  Focus: increase your daily step count. A 15-min walk after")
        lines.append("  each meal adds 4,000+ steps with almost no effort.")
    elif bmi is not None and bmi >= 25 and target and weight > target:
        lines.append("  Focus: calorie deficit + strength training. Even 15 min of")
        lines.append("  daily bodyweight exercise (squats, push-ups) builds momentum.")
    elif bmi is not None and bmi < 18.5 and target and weight < target:
        lines.append("  Focus: nutrient-dense meals + resistance training to build")
        lines.append("  lean mass. Track your protein alongside calories.")
    elif d["exercise_days"] < 3 and d["weekly_minutes"] < 90:
        lines.append("  Focus: start small — three 15-min sessions per week already")
        lines.append("  make a difference. Consistency beats intensity.")
    elif water_pct < 60:
        lines.append("  Focus: hydration first! Keep a water bottle at your desk.")
    elif d["sleep_hours"] < SLEEP_MIN:
        lines.append("  Focus: recovery. Aim for 7+ hours tonight — your next workout")
        lines.append("  will feel noticeably easier.")
    else:
        lines.append("  Keep doing what you're doing. Try adding a new exercise or")
        lines.append("  increasing rep count to keep progressing.")

    lines.append("")
    lines.append(sep)
    lines.append("  This advice is based on your personal data. It is not a")
    lines.append("  substitute for professional medical guidance.")
    lines.append(sep)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tkinter window — called from camera4.py
# ---------------------------------------------------------------------------

def open_ai_coach_window(parent, username: str):
    """Open a scrollable read-only window showing the AI Coach report."""
    import tkinter as tk
    from tkinter import scrolledtext

    window = tk.Toplevel(parent)
    window.title("AI Coach")
    window.geometry("660x580")
    window.resizable(True, True)
    window.configure(bg="#10131a")

    header = tk.Label(
        window,
        text="AI Fitness Coach",
        font=("Arial", 16, "bold"),
        bg="#10131a",
        fg="#f4f7ff",
    )
    header.pack(pady=(14, 6))

    text_area = scrolledtext.ScrolledText(
        window,
        wrap=tk.WORD,
        font=("Consolas", 10),
        bg="#1a2233",
        fg="#e0e8f5",
        insertbackground="#e0e8f5",
        relief="flat",
        bd=0,
        padx=14,
        pady=10,
    )
    text_area.pack(fill="both", expand=True, padx=14, pady=(4, 14))

    report = generate_coach_report(username)
    text_area.insert("1.0", report)
    text_area.configure(state="disabled")  # read-only
