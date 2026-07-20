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


def setup_database():
    db_directory = r"C:\project_database"
    os.makedirs(db_directory, exist_ok=True)
    db_path = os.path.join(db_directory, "water_db.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS water_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL DEFAULT 'legacy',
            record_date TEXT NOT NULL,
            water_ml REAL NOT NULL
        )
        """
    )
    existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(water_records)").fetchall()}
    if "username" not in existing_columns:
        cursor.execute(
            "ALTER TABLE water_records ADD COLUMN username TEXT NOT NULL DEFAULT 'legacy'"
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
        SELECT COALESCE(SUM(water_ml), 0)
        FROM water_records
        WHERE username = ? AND record_date = ?
        """,
        (username, today),
    )
    row = cursor.fetchone()
    daily_total_water = row[0] if row else 0.0
    record_ids = []

    window = tk.Tk()
    window.title("Water Tracker")
    window.geometry("430x460")
    window.minsize(380, 360)
    window.resizable(True, True)

    title_label = tk.Label(window, text=f"{today} - Water Tracker", font=("Arial", 14, "bold"))
    title_label.pack(pady=(12, 10))

    form_frame = tk.Frame(window)
    form_frame.pack(padx=12, fill="x")

    tk.Label(form_frame, text="Water Amount (ml):").grid(row=0, column=0, sticky="w", pady=4)
    water_entry = tk.Entry(form_frame, width=28)
    water_entry.grid(row=0, column=1, pady=4, padx=6)

    list_frame = tk.Frame(window)
    list_frame.pack(padx=12, pady=10, fill="both", expand=True)

    record_list = tk.Listbox(list_frame, height=10)
    record_list.pack(side="left", fill="both", expand=True)

    scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=record_list.yview)
    scrollbar.pack(side="right", fill="y")
    record_list.config(yscrollcommand=scrollbar.set)

    total_var = tk.StringVar(value=f"Daily Total Water: {daily_total_water:.0f} ml")
    total_label = tk.Label(window, textvariable=total_var, font=("Arial", 12, "bold"))
    total_label.pack(pady=4)

    def refresh_list():
        nonlocal daily_total_water, record_ids
        record_list.delete(0, tk.END)
        record_ids = []
        cursor.execute(
            "SELECT id, water_ml FROM water_records WHERE username = ? AND record_date = ? ORDER BY id ASC",
            (username, today),
        )
        rows = cursor.fetchall()
        total = 0.0
        for rid, wml in rows:
            record_ids.append(rid)
            record_list.insert(tk.END, f"{wml:.0f} ml")
            total += wml
        daily_total_water = total
        total_var.set(f"Daily Total Water: {daily_total_water:.0f} ml")

    def delete_selected():
        sel = record_list.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Select a record to delete.")
            return
        idx = sel[0]
        rid = record_ids[idx]
        if messagebox.askyesno("Confirm", "Delete this record?"):
            cursor.execute("DELETE FROM water_records WHERE id = ?", (rid,))
            conn.commit()
            refresh_list()

    def add_record():
        nonlocal daily_total_water
        water_str = water_entry.get().strip()

        try:
            water_ml = float(water_str)
            if water_ml <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Warning", "Water amount must be a positive number.")
            return

        cursor.execute(
            """
            INSERT INTO water_records (username, record_date, water_ml)
            VALUES (?, ?, ?)
            """,
            (username, today, water_ml),
        )
        conn.commit()
        refresh_list()
        water_entry.delete(0, tk.END)
        water_entry.focus_set()

    def exit_app():
        conn.close()
        window.destroy()

    # Load existing records on startup
    cursor.execute(
        "SELECT id, water_ml FROM water_records WHERE username = ? AND record_date = ? ORDER BY id ASC",
        (username, today),
    )
    for rid, wml in cursor.fetchall():
        record_ids.append(rid)
        record_list.insert(tk.END, f"{wml:.0f} ml")

    button_frame = tk.Frame(window)
    button_frame.pack(pady=(0, 10))

    add_btn = tk.Button(button_frame, text="Add Record", width=12, command=add_record)
    add_btn.grid(row=0, column=0, padx=4)

    delete_btn = tk.Button(button_frame, text="Delete Selected", width=14, command=delete_selected, fg="red")
    delete_btn.grid(row=0, column=1, padx=4)

    exit_btn = tk.Button(button_frame, text="Exit", width=12, command=exit_app)
    exit_btn.grid(row=0, column=2, padx=4)

    window.protocol("WM_DELETE_WINDOW", exit_app)
    water_entry.focus_set()
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
