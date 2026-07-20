import hashlib
import os
import re
import sqlite3
import tkinter as tk
from tkinter import messagebox


DB_FILE = r"C:\project_database\user_db.db"


def get_connection():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    return sqlite3.connect(DB_FILE)


def init_db():
    with get_connection() as conn:
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
                target_weight_kg REAL
            )
            """
        )
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "age" not in existing_columns:
            conn.execute("ALTER TABLE users ADD COLUMN age INTEGER")
        if "height_cm" not in existing_columns:
            conn.execute("ALTER TABLE users ADD COLUMN height_cm REAL")
        if "weight_kg" not in existing_columns:
            conn.execute("ALTER TABLE users ADD COLUMN weight_kg REAL")
        if "bmi" not in existing_columns:
            conn.execute("ALTER TABLE users ADD COLUMN bmi REAL")
        if "ideal_weight_min" not in existing_columns:
            conn.execute("ALTER TABLE users ADD COLUMN ideal_weight_min REAL")
        if "ideal_weight_max" not in existing_columns:
            conn.execute("ALTER TABLE users ADD COLUMN ideal_weight_max REAL")
        if "target_weight_kg" not in existing_columns:
            conn.execute("ALTER TABLE users ADD COLUMN target_weight_kg REAL")
        if "gender" not in existing_columns:
            conn.execute("ALTER TABLE users ADD COLUMN gender TEXT")
        if "cinsiyet" in existing_columns:
            conn.execute(
                """
                UPDATE users
                SET gender = CASE cinsiyet
                    WHEN 'Kadın' THEN 'Female'
                    WHEN 'Erkek' THEN 'Male'
                    WHEN 'Diğer' THEN 'Other'
                    ELSE cinsiyet
                END
                WHERE (gender IS NULL OR gender = '')
                  AND cinsiyet IS NOT NULL
                  AND cinsiyet != ''
                """
            )
        conn.commit()


def user_exists(username):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return row is not None


def create_user(username, password_hash):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        conn.commit()


def get_password_hash(username):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return row[0] if row else None


def get_healthy_bmi_range(age):
    if age >= 65:
        return 22.0, 27.0
    if age < 18:
        return 18.5, 24.0
    return 18.5, 24.9


def calculate_body_metrics(age, height_cm, weight_kg):
    height_m = height_cm / 100.0
    bmi = weight_kg / (height_m * height_m)
    bmi_min, bmi_max = get_healthy_bmi_range(age)
    ideal_min = bmi_min * (height_m * height_m)
    ideal_max = bmi_max * (height_m * height_m)
    return round(bmi, 2), round(ideal_min, 2), round(ideal_max, 2)


def save_user_profile(
    username,
    age,
    height_cm,
    weight_kg,
    bmi,
    ideal_weight_min,
    ideal_weight_max,
    target_weight_kg,
    gender,
):
    with get_connection() as conn:
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
                gender = ?
            WHERE username = ?
            """,
            (
                age,
                height_cm,
                weight_kg,
                bmi,
                ideal_weight_min,
                ideal_weight_max,
                target_weight_kg,
                gender,
                username,
            ),
        )
        conn.commit()


def open_profile_menu(username):
    profile_window = tk.Toplevel()
    profile_window.title("Profile Menu")
    profile_window.geometry("520x420")
    profile_window.minsize(400, 360)
    profile_window.resizable(True, True)
    profile_window.grab_set()

    frame = tk.Frame(profile_window, padx=15, pady=12)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text=f"Welcome, {username}", font=("Arial", 12, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )

    tk.Label(frame, text="Age").grid(row=1, column=0, sticky="w", pady=5)
    age_entry = tk.Entry(frame, width=30)
    age_entry.grid(row=1, column=1, pady=5)

    tk.Label(frame, text="Height (cm)").grid(row=2, column=0, sticky="w", pady=5)
    height_entry = tk.Entry(frame, width=30)
    height_entry.grid(row=2, column=1, pady=5)

    tk.Label(frame, text="Weight (kg)").grid(row=3, column=0, sticky="w", pady=5)
    weight_entry = tk.Entry(frame, width=30)
    weight_entry.grid(row=3, column=1, pady=5)

    tk.Label(frame, text="Gender").grid(row=4, column=0, sticky="w", pady=5)
    gender_var = tk.StringVar(value="Select")
    gender_menu = tk.OptionMenu(frame, gender_var, "Select", "Female", "Male", "Other")
    gender_menu.config(width=27)
    gender_menu.grid(row=4, column=1, pady=5, sticky="w")

    bmi_result_var = tk.StringVar(value="BMI: -")
    ideal_range_var = tk.StringVar(value="Ideal weight range: -")

    tk.Label(frame, textvariable=bmi_result_var, fg="#1f4b99").grid(
        row=5, column=0, columnspan=2, sticky="w", pady=(10, 4)
    )
    tk.Label(frame, textvariable=ideal_range_var, fg="#1f4b99").grid(
        row=6, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )

    tk.Label(frame, text="Target Weight (kg)").grid(row=7, column=0, sticky="w", pady=5)
    target_weight_entry = tk.Entry(frame, width=30)
    target_weight_entry.grid(row=7, column=1, pady=5)

    calculated_metrics = {"bmi": None, "ideal_min": None, "ideal_max": None}

    def read_profile_inputs():
        age_value = age_entry.get().strip()
        height_value = height_entry.get().strip()
        weight_value = weight_entry.get().strip()

        if not age_value or not height_value or not weight_value:
            messagebox.showwarning("Warning", "Please fill in age, height and weight.")
            return None

        try:
            age = int(age_value)
            height_cm = float(height_value)
            weight_kg = float(weight_value)
        except ValueError:
            messagebox.showwarning(
                "Warning", "Age must be integer, height/weight must be numeric."
            )
            return None

        if age <= 0 or height_cm <= 0 or weight_kg <= 0:
            messagebox.showwarning("Warning", "Age, height and weight must be positive.")
            return None

        return age, height_cm, weight_kg

    def calculate_and_show():
        parsed = read_profile_inputs()
        if parsed is None:
            return

        age, height_cm, weight_kg = parsed
        bmi, ideal_min, ideal_max = calculate_body_metrics(age, height_cm, weight_kg)
        calculated_metrics["bmi"] = bmi
        calculated_metrics["ideal_min"] = ideal_min
        calculated_metrics["ideal_max"] = ideal_max

        bmi_result_var.set(f"BMI: {bmi:.2f}")
        ideal_range_var.set(
            f"Ideal weight range (age + height): {ideal_min:.2f} kg - {ideal_max:.2f} kg"
        )

    calculate_button = tk.Button(
        frame, text="Calculate BMI & Ideal Range", width=26, command=calculate_and_show
    )
    calculate_button.grid(row=8, column=1, sticky="w", pady=8)

    def submit_profile():
        parsed = read_profile_inputs()
        if parsed is None:
            return

        target_value = target_weight_entry.get().strip()
        if not target_value:
            messagebox.showwarning("Warning", "Please enter your target weight.")
            return

        try:
            target_weight_kg = float(target_value)
        except ValueError:
            messagebox.showwarning("Warning", "Target weight must be numeric.")
            return

        if target_weight_kg <= 0:
            messagebox.showwarning("Warning", "Target weight must be positive.")
            return

        gender = gender_var.get().strip()
        if gender == "Select":
            messagebox.showwarning("Warning", "Please select your gender.")
            return

        age, height_cm, weight_kg = parsed
        if calculated_metrics["bmi"] is None:
            bmi, ideal_min, ideal_max = calculate_body_metrics(age, height_cm, weight_kg)
        else:
            bmi = calculated_metrics["bmi"]
            ideal_min = calculated_metrics["ideal_min"]
            ideal_max = calculated_metrics["ideal_max"]

        save_user_profile(
            username,
            age,
            height_cm,
            weight_kg,
            bmi,
            ideal_min,
            ideal_max,
            target_weight_kg,
            gender,
        )
        messagebox.showinfo(
            "Success",
            (
                f"Saved.\nBMI: {bmi:.2f}\n"
                f"Ideal range: {ideal_min:.2f}-{ideal_max:.2f} kg\n"
                f"Target weight: {target_weight_kg:.2f} kg\n"
                f"Gender: {gender}"
            ),
        )
        profile_window.destroy()

    save_button = tk.Button(
        frame, text="Save All", width=18, command=submit_profile
    )
    save_button.grid(row=9, column=1, sticky="w", pady=14)


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def validate_password(password):
    rules = []
    if len(password) < 8:
        rules.append("Must be at least 8 characters.")
    if not re.search(r"[A-Z]", password):
        rules.append("Must include at least 1 uppercase letter.")
    if not re.search(r"[a-z]", password):
        rules.append("Must include at least 1 lowercase letter.")
    if not re.search(r"[0-9]", password):
        rules.append("Must include at least 1 digit.")
    return rules


def register_user(username_entry, password_entry, confirm_entry, register_window):
    username = username_entry.get().strip()
    password = password_entry.get()
    confirm_password = confirm_entry.get()

    if not username:
        messagebox.showwarning("Warning", "Username cannot be empty.")
        return

    if user_exists(username):
        messagebox.showwarning("Warning", "This username is already registered.")
        return

    password_errors = validate_password(password)
    if password_errors:
        messagebox.showwarning("Password Error", "\n".join(password_errors))
        return

    if password != confirm_password:
        messagebox.showwarning("Warning", "Passwords do not match.")
        return

    create_user(username, hash_password(password))
    messagebox.showinfo("Success", f"{username}, registration completed!")

    username_entry.delete(0, tk.END)
    password_entry.delete(0, tk.END)
    confirm_entry.delete(0, tk.END)
    register_window.destroy()

    # Auto-login and force profile setup immediately after registration
    open_profile_menu(username)


def login_user(username_entry, password_entry):
    username = username_entry.get().strip()
    password = password_entry.get()
    stored_password_hash = get_password_hash(username)

    if stored_password_hash is None:
        messagebox.showerror("Error", "User not found.")
        return

    if stored_password_hash != hash_password(password):
        messagebox.showerror("Error", "Incorrect password.")
        return

    messagebox.showinfo("Welcome", f"{username}, login successful!")
    open_profile_menu(username)
    username_entry.delete(0, tk.END)
    password_entry.delete(0, tk.END)


def open_register_window(root):
    register_window = tk.Toplevel(root)
    register_window.title("Sign Up")
    register_window.geometry("420x280")
    register_window.minsize(360, 240)
    register_window.resizable(True, True)
    register_window.grab_set()

    frame = tk.Frame(register_window, padx=15, pady=10)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="New Username").grid(row=0, column=0, sticky="w", pady=5)
    username_entry = tk.Entry(frame, width=35)
    username_entry.grid(row=0, column=1, pady=5)

    tk.Label(frame, text="Password").grid(row=1, column=0, sticky="w", pady=5)
    password_entry = tk.Entry(frame, width=35, show="*")
    password_entry.grid(row=1, column=1, pady=5)

    tk.Label(frame, text="Confirm Password").grid(row=2, column=0, sticky="w", pady=5)
    confirm_entry = tk.Entry(frame, width=35, show="*")
    confirm_entry.grid(row=2, column=1, pady=5)

    register_button = tk.Button(
        frame,
        text="Complete Registration",
        width=18,
        command=lambda: register_user(username_entry, password_entry, confirm_entry, register_window),
    )
    register_button.grid(row=3, column=1, pady=14, sticky="w")

    info_text = (
        "Password rules:\n"
        "- At least 8 characters\n"
        "- At least 1 uppercase letter\n"
        "- At least 1 lowercase letter\n"
        "- At least 1 digit"
    )
    tk.Label(frame, text=info_text, justify="left", fg="#333").grid(row=4, column=0, columnspan=2, sticky="w")


def build_ui():
    init_db()
    root = tk.Tk()
    root.title("User Login Screen")
    root.geometry("420x220")
    root.minsize(360, 200)
    root.resizable(True, True)

    title_label = tk.Label(root, text="Login", font=("Arial", 16, "bold"))
    title_label.pack(pady=10)

    frame = tk.Frame(root, padx=15, pady=10)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="Username").grid(row=0, column=0, sticky="w", pady=5)
    username_entry = tk.Entry(frame, width=35)
    username_entry.grid(row=0, column=1, pady=5)

    tk.Label(frame, text="Password").grid(row=1, column=0, sticky="w", pady=5)
    password_entry = tk.Entry(frame, width=35, show="*")
    password_entry.grid(row=1, column=1, pady=5)

    login_button = tk.Button(
        frame,
        text="Login",
        width=16,
        command=lambda: login_user(username_entry, password_entry),
    )
    login_button.grid(row=2, column=0, pady=16)

    register_button = tk.Button(
        frame,
        text="Sign Up",
        width=16,
        command=lambda: open_register_window(root),
    )
    register_button.grid(row=2, column=1, pady=16, sticky="w")

    root.mainloop()


if __name__ == "__main__":
    build_ui()
