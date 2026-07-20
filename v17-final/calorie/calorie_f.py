import sqlite3
import requests
from datetime import date
import os
import time
import re
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


# --- 1. DATABASE SETUP ---
def setup_database():
    # Create database directory if it does not exist
    db_folder = r"C:\project_database"
    os.makedirs(db_folder, exist_ok=True)

    # Connect to the database file
    db_path = os.path.join(db_folder, "calorie_db.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table if it does not exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL DEFAULT 'legacy',
            record_date TEXT,
            food_name TEXT,
            weight_grams REAL,
            calories REAL
        )
    ''')
    existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(daily_records)").fetchall()}
    if "username" not in existing_columns:
        cursor.execute(
            "ALTER TABLE daily_records ADD COLUMN username TEXT NOT NULL DEFAULT 'legacy'"
        )
    conn.commit()
    return conn

# --- 2. FETCH DATA FROM API ---
def fetch_calories(food_name):
    print(f"Searching for '{food_name}'...")
    headers = {"User-Agent": "AI-Fitness-Trainer/1.0 (local desktop app)"}
    searched = food_name.strip().lower()
    searched_words = [w for w in re.split(r"\s+", searched) if w]

    # 1) Try USDA FoodData Central first (if API key exists)
    usda_api_key = os.getenv("USDA_API_KEY", "").strip()
    if usda_api_key:
        usda_url = "https://api.nal.usda.gov/fdc/v1/foods/search"
        usda_params = {
            "api_key": usda_api_key,
            "query": food_name,
            "pageSize": 25,
        }
        try:
            response = requests.get(usda_url, params=usda_params, timeout=15)
            response.raise_for_status()
            data = response.json()

            best_calories = None
            best_score = -1

            for food in data.get("foods", []):
                description = str(food.get("description", "")).lower()

                # Basic match score: increase score if searched words appear
                score = 0
                if description == searched:
                    score += 100
                for word in searched_words:
                    if word in description:
                        score += 10

                # Small bonus for more reliable data types
                data_type = str(food.get("dataType", "")).lower()
                if "foundation" in data_type or "survey" in data_type:
                    score += 3

                for nutrient in food.get("foodNutrients", []):
                    nutrient_name = str(nutrient.get("nutrientName", "")).lower()
                    unit_name = str(nutrient.get("unitName", "")).lower()
                    nutrient_number = str(nutrient.get("nutrientNumber", ""))
                    value = nutrient.get("value")
                    if value is None:
                        continue

                    # USDA energy (kcal) indicator: nutrientNumber 1008
                    if nutrient_number == "1008" or ("energy" in nutrient_name and ("kcal" in unit_name or "kilocalorie" in unit_name)):
                        kcal = float(value)
                        if score > best_score:
                            best_score = score
                            best_calories = kcal
                        break

            if best_calories is not None:
                return best_calories
        except Exception as e:
            print(f"USDA API error: {e}")
    else:
        print("USDA API key not found. Define USDA_API_KEY environment variable to use USDA.")

    # 2) Try Open Food Facts (if USDA unavailable/failed)
    off_urls = [
        "https://world.openfoodfacts.org/api/v2/search",
        "https://tr.openfoodfacts.org/api/v2/search",
    ]
    off_params = {
        "search_terms": food_name,
        "fields": "product_name,nutriments",
        "page_size": 25,
    }

    for url in off_urls:
        for attempt in range(3):
            try:
                response = requests.get(url, params=off_params, headers=headers, timeout=15)
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt < 2:
                        time.sleep(1.2 * (attempt + 1))
                        continue
                    break

                response.raise_for_status()
                data = response.json()
                products = data.get("products", [])
                best_calories = None
                best_score = -1

                for product in products:
                    product_name = str(product.get("product_name", "")).lower()
                    score = 0
                    if product_name == searched:
                        score += 100
                    for word in searched_words:
                        if word in product_name:
                            score += 10

                    nutrition_values = product.get("nutriments", {})
                    kcal_100g = nutrition_values.get("energy-kcal_100g")
                    if kcal_100g is None:
                        kcal_100g = nutrition_values.get("energy-kcal")
                    if kcal_100g is None:
                        kcal_100g = nutrition_values.get("energy_100g")
                        if kcal_100g is not None:
                            kcal_100g = float(kcal_100g) / 4.184

                    if kcal_100g is not None and score > best_score:
                        best_score = score
                        best_calories = float(kcal_100g)

                if best_calories is not None:
                    return best_calories
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(1.2 * (attempt + 1))
                else:
                    print(f"Open Food Facts error ({url}): {e}")

    return None

# --- 3. MAIN PROGRAM LOOP ---
def main_program(username):
    if not is_registered_user(username):
        print("Error: Username is not registered in user_db.db.")
        return
    conn = setup_database()
    cursor = conn.cursor()

    # Get today's date (e.g., 2023-10-25)
    today = str(date.today())
    cursor.execute(
        """
        SELECT COALESCE(SUM(calories), 0)
        FROM daily_records
        WHERE username = ? AND record_date = ?
        """,
        (username, today),
    )
    row = cursor.fetchone()
    daily_total_calories = row[0] if row else 0.0

    print(f"\n=== Welcome to the {today} Calorie Tracker ===")
    print("Type 'done' or 'q' to exit and see the total.\n")

    while True:
        food = input("What did you eat?: ").strip()

        # Exit check
        if food.lower() in ['done', 'q', 'exit']:
            break

        if not food:
            continue

        # Fetch calories per 100g from API
        kcal_100g = fetch_calories(food)

        if kcal_100g is None:
            print(f"Warning: Calorie info for '{food}' was not found. Try an English name (e.g., apple) or a clearer product/brand name.\n")
            continue

        # Get weight
        try:
            weight_str = input(f"How many grams of {food} did you eat?: ")
            weight_grams = float(weight_str)
        except ValueError:
            print("Warning: Please enter a valid number.\n")
            continue

        # Calculate consumed calories
        consumed_calories = (kcal_100g / 100) * weight_grams
        daily_total_calories += consumed_calories

        # Save to database
        cursor.execute('''
            INSERT INTO daily_records (username, record_date, food_name, weight_grams, calories)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, today, food, weight_grams, consumed_calories))
        conn.commit()

        print(f"Added: {weight_grams}g {food} = {consumed_calories:.2f} kcal")
        print(f"Current daily total: {daily_total_calories:.2f} kcal\n")

    print("\n" + "="*40)
    print(f"DAY SUMMARY ({today})")
    print(f"Total Calories Consumed: {daily_total_calories:.2f} kcal")
    print("="*40)

    # Close connection
    conn.close()


def start_gui(username):
    if not is_registered_user(username):
        messagebox.showerror("Unauthorized", "Username is not registered in user_db.db.")
        return
    conn = setup_database()
    cursor = conn.cursor()
    today = str(date.today())
    cursor.execute(
        """
        SELECT COALESCE(SUM(calories), 0)
        FROM daily_records
        WHERE username = ? AND record_date = ?
        """,
        (username, today),
    )
    row = cursor.fetchone()
    daily_total_calories = row[0] if row else 0.0
    record_ids = []

    window = tk.Tk()
    window.title("Calorie Tracker")
    window.geometry("520x480")
    window.minsize(420, 380)
    window.resizable(True, True)

    title_label = tk.Label(window, text=f"{today} - Calorie Tracker", font=("Arial", 14, "bold"))
    title_label.pack(pady=(12, 10))

    form_frame = tk.Frame(window)
    form_frame.pack(padx=12, fill="x")

    tk.Label(form_frame, text="Food Name:").grid(row=0, column=0, sticky="w", pady=4)
    food_entry = tk.Entry(form_frame, width=30)
    food_entry.grid(row=0, column=1, pady=4, padx=6)

    tk.Label(form_frame, text="Weight (g):").grid(row=1, column=0, sticky="w", pady=4)
    weight_entry = tk.Entry(form_frame, width=30)
    weight_entry.grid(row=1, column=1, pady=4, padx=6)

    list_frame = tk.Frame(window)
    list_frame.pack(padx=12, pady=10, fill="both", expand=True)

    record_list = tk.Listbox(list_frame, height=10)
    record_list.pack(side="left", fill="both", expand=True)

    scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=record_list.yview)
    scrollbar.pack(side="right", fill="y")
    record_list.config(yscrollcommand=scrollbar.set)

    total_var = tk.StringVar(value=f"Daily Total: {daily_total_calories:.2f} kcal")
    total_label = tk.Label(window, textvariable=total_var, font=("Arial", 12, "bold"))
    total_label.pack(pady=4)

    def refresh_list():
        nonlocal daily_total_calories, record_ids
        record_list.delete(0, tk.END)
        record_ids = []
        cursor.execute(
            "SELECT id, food_name, weight_grams, calories FROM daily_records WHERE username = ? AND record_date = ? ORDER BY id ASC",
            (username, today),
        )
        rows = cursor.fetchall()
        total = 0.0
        for rid, fname, wg, cal in rows:
            record_ids.append(rid)
            record_list.insert(tk.END, f"{fname} - {wg:.0f}g - {cal:.2f} kcal")
            total += cal
        daily_total_calories = total
        total_var.set(f"Daily Total: {daily_total_calories:.2f} kcal")

    def delete_selected():
        sel = record_list.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Select a record to delete.")
            return
        idx = sel[0]
        rid = record_ids[idx]
        if messagebox.askyesno("Confirm", "Delete this record?"):
            cursor.execute("DELETE FROM daily_records WHERE id = ?", (rid,))
            conn.commit()
            refresh_list()

    def add_record():
        nonlocal daily_total_calories

        food = food_entry.get().strip()
        weight_str = weight_entry.get().strip()

        if not food:
            messagebox.showwarning("Warning", "Please enter a food name.")
            return

        try:
            weight_grams = float(weight_str)
            if weight_grams <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Warning", "Weight must be a positive number.")
            return

        kcal_100g = fetch_calories(food)
        if kcal_100g is None:
            messagebox.showwarning(
                "Not Found",
                (
                    f"Could not fetch calorie info for '{food}'.\n\n"
                    "Sources: Open Food Facts and USDA FoodData Central (if available).\n"
                    "To use USDA, define the USDA_API_KEY environment variable."
                ),
            )
            return

        consumed_calories = (kcal_100g / 100) * weight_grams

        cursor.execute(
            '''
            INSERT INTO daily_records (username, record_date, food_name, weight_grams, calories)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (username, today, food, weight_grams, consumed_calories),
        )
        conn.commit()
        refresh_list()

        food_entry.delete(0, tk.END)
        weight_entry.delete(0, tk.END)
        food_entry.focus_set()

    def exit_app():
        conn.close()
        window.destroy()

    # Load existing records on startup
    cursor.execute(
        "SELECT id, food_name, weight_grams, calories FROM daily_records WHERE username = ? AND record_date = ? ORDER BY id ASC",
        (username, today),
    )
    for rid, fname, wg, cal in cursor.fetchall():
        record_ids.append(rid)
        record_list.insert(tk.END, f"{fname} - {wg:.0f}g - {cal:.2f} kcal")

    button_frame = tk.Frame(window)
    button_frame.pack(pady=(0, 10))

    add_btn = tk.Button(button_frame, text="Add Record", width=12, command=add_record)
    add_btn.grid(row=0, column=0, padx=4)

    delete_btn = tk.Button(button_frame, text="Delete Selected", width=14, command=delete_selected, fg="red")
    delete_btn.grid(row=0, column=1, padx=4)

    exit_btn = tk.Button(button_frame, text="Exit", width=12, command=exit_app)
    exit_btn.grid(row=0, column=2, padx=4)

    window.protocol("WM_DELETE_WINDOW", exit_app)
    food_entry.focus_set()
    window.mainloop()

# Run program
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
