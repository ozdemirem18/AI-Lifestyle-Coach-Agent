import os
import sqlite3
from datetime import date
import tkinter as tk
from tkinter import messagebox

USER_DB_PATH = r"C:\project_database\user_db.db"


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


def _get_weight_kg(username):
    """Fetch the user's weight from user_db for calorie calculation."""
    try:
        with sqlite3.connect(USER_DB_PATH) as conn:
            row = conn.execute(
                "SELECT weight_kg FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        return float(row[0]) if row and row[0] else None
    except (sqlite3.OperationalError, ValueError, TypeError):
        return None


def _calculate_step_calories(steps, weight_kg):
    """
    Estimate calories burned from walking steps.
    Formula: MET (3.0) * weight_kg * (steps / 7000 steps per hour)
    """
    if not weight_kg or weight_kg <= 0 or steps <= 0:
        return 0.0
    duration_hours = steps / 7000.0
    return round(3.0 * weight_kg * duration_hours, 1)


def setup_database():
    db_directory = r"C:\project_database"
    os.makedirs(db_directory, exist_ok=True)
    db_path = os.path.join(db_directory, "step_db.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS step_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL DEFAULT 'legacy',
            record_date TEXT NOT NULL,
            steps INTEGER NOT NULL
        )
        """
    )
    existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(step_records)").fetchall()}
    if "username" not in existing_columns:
        cursor.execute(
            "ALTER TABLE step_records ADD COLUMN username TEXT NOT NULL DEFAULT 'legacy'"
        )
    conn.commit()
    return conn


def start_gui(username):
    if not is_registered_user(username):
        messagebox.showerror("Unauthorized", "Username is not registered in user_db.db.")
        return
    conn = setup_database()
    cursor = conn.cursor()
    today = str(date.today())
    cursor.execute(
        """
        SELECT COALESCE(SUM(steps), 0)
        FROM step_records
        WHERE username = ? AND record_date = ?
        """,
        (username, today),
    )
    row = cursor.fetchone()
    daily_total_steps = row[0] if row else 0
    weight_kg = _get_weight_kg(username)
    has_weight = weight_kg is not None
    record_ids = []

    window = tk.Tk()
    window.title("Step Tracker")
    window.geometry("430x480")
    window.minsize(380, 360)
    window.resizable(True, True)

    title_label = tk.Label(window, text=f"{today} - Step Tracker", font=("Arial", 14, "bold"))
    title_label.pack(pady=(12, 10))

    form_frame = tk.Frame(window)
    form_frame.pack(padx=12, fill="x")

    tk.Label(form_frame, text="Steps:").grid(row=0, column=0, sticky="w", pady=4)
    steps_entry = tk.Entry(form_frame, width=28)
    steps_entry.grid(row=0, column=1, pady=4, padx=6)

    list_frame = tk.Frame(window)
    list_frame.pack(padx=12, pady=10, fill="both", expand=True)

    record_list = tk.Listbox(list_frame, height=10)
    record_list.pack(side="left", fill="both", expand=True)

    scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=record_list.yview)
    scrollbar.pack(side="right", fill="y")
    record_list.config(yscrollcommand=scrollbar.set)

    initial_calories = _calculate_step_calories(daily_total_steps, weight_kg)
    if has_weight:
        total_text = f"Daily Total Steps: {daily_total_steps}  |  ~{initial_calories} kcal burned"
    else:
        total_text = f"Daily Total Steps: {daily_total_steps}"
    total_var = tk.StringVar(value=total_text)
    total_label = tk.Label(window, textvariable=total_var, font=("Arial", 12, "bold"))
    total_label.pack(pady=4)

    if not has_weight:
        weight_warning = tk.Label(
            window,
            text="Set your weight in User Profile for calorie estimates.",
            font=("Arial", 9),
            fg="#ff9944",
        )
        weight_warning.pack()

    def refresh_list():
        nonlocal daily_total_steps, record_ids
        record_list.delete(0, tk.END)
        record_ids = []
        cursor.execute(
            "SELECT id, steps FROM step_records WHERE username = ? AND record_date = ? ORDER BY id ASC",
            (username, today),
        )
        rows = cursor.fetchall()
        total = 0
        for rid, s in rows:
            record_ids.append(rid)
            record_list.insert(tk.END, f"{s} steps")
            total += s
        daily_total_steps = total
        cals = _calculate_step_calories(total, weight_kg)
        if has_weight:
            total_var.set(f"Daily Total Steps: {total}  |  ~{cals} kcal burned")
        else:
            total_var.set(f"Daily Total Steps: {total}")

    def delete_selected():
        sel = record_list.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Select a record to delete.")
            return
        idx = sel[0]
        rid = record_ids[idx]
        if messagebox.askyesno("Confirm", "Delete this record?"):
            cursor.execute("DELETE FROM step_records WHERE id = ?", (rid,))
            conn.commit()
            refresh_list()

    def add_record():
        nonlocal daily_total_steps
        steps_str = steps_entry.get().strip()

        try:
            steps = int(steps_str)
            if steps <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Warning", "Steps must be a positive whole number.")
            return

        cursor.execute(
            """
            INSERT INTO step_records (username, record_date, steps)
            VALUES (?, ?, ?)
            """,
            (username, today, steps),
        )
        conn.commit()
        refresh_list()

        steps_entry.delete(0, tk.END)
        steps_entry.focus_set()

    def exit_app():
        conn.close()
        window.destroy()

    # Load existing records on startup
    cursor.execute(
        "SELECT id, steps FROM step_records WHERE username = ? AND record_date = ? ORDER BY id ASC",
        (username, today),
    )
    for rid, s in cursor.fetchall():
        record_ids.append(rid)
        record_list.insert(tk.END, f"{s} steps")

    button_frame = tk.Frame(window)
    button_frame.pack(pady=(0, 10))

    add_btn = tk.Button(button_frame, text="Add Record", width=12, command=add_record)
    add_btn.grid(row=0, column=0, padx=4)

    delete_btn = tk.Button(button_frame, text="Delete Selected", width=14, command=delete_selected, fg="red")
    delete_btn.grid(row=0, column=1, padx=4)

    exit_btn = tk.Button(button_frame, text="Exit", width=12, command=exit_app)
    exit_btn.grid(row=0, column=2, padx=4)

    window.protocol("WM_DELETE_WINDOW", exit_app)
    steps_entry.focus_set()
    window.mainloop()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", type=str, default=None, help="Username from web login")
    args = parser.parse_args()
    if args.username:
        start_gui(args.username)
    else:
        user = input("Username: ").strip()
        if user:
            start_gui(user)
        else:
            print("Username is required.")
