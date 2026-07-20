import argparse
import cv2
import numpy as np
import time
import tkinter as tk
from tkinter import messagebox
import PoseModule as pm
from collections import deque
import sqlite3
from datetime import datetime
from calorie.spor_calorie_f import (
    calculate_daily_exercise_report,
    save_daily_exercise_report_to_calorie_db,
)
from ai_coach import open_ai_coach_window

# Parse command-line arguments (username from web login)
parser = argparse.ArgumentParser()
parser.add_argument("--username", type=str, default=None, help="Pre-filled username from web login")
args = parser.parse_args()

# Initialize video capture and pose detector
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
# Set higher camera resolution for better fullscreen quality
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
cap.set(cv2.CAP_PROP_FPS, 30)
# Read back actual resolution the camera supports
CAM_W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
CAM_H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
# Increase thresholds slightly for less noisy landmark detection
detector = pm.poseDetector(detectionCon=0.8, trackCon=0.8)
ANGLE_TOLERANCE = 20
SQUAT_TOLERANCE = 10
DB_PATH = r"C:\project_database\spor_db.db"
USER_DB_PATH = r"C:\project_database\user_db.db"

# Stricter thresholds to reduce false positives (counting without real movement).
PUSHUP_ANGLE_TOLERANCE = 14
PLANK_ANGLE_TOLERANCE = 12
ARM_RAISE_DOWN_MARGIN_RATIO = 0.12
ARM_RAISE_UP_MARGIN_RATIO = 0.10
ARM_RAISE_STABLE_WINDOW = 6


def is_registered_user(username):
    normalized = str(username or "").strip()
    if not normalized:
        return False
    conn = sqlite3.connect(USER_DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM users WHERE username = ? LIMIT 1",
        (normalized,),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='exercise_daily_logs'"
    )
    table_exists = cursor.fetchone() is not None
    if table_exists:
        columns = {
            row[1] for row in cursor.execute("PRAGMA table_info(exercise_daily_logs)").fetchall()
        }
        if "username" not in columns:
            # Legacy schema had no username and merged all users into same daily rows.
            cursor.execute("ALTER TABLE exercise_daily_logs RENAME TO exercise_daily_logs_legacy")
            cursor.execute(
                """
                CREATE TABLE exercise_daily_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    exercise_name TEXT NOT NULL,
                    log_date TEXT NOT NULL,
                    total_amount REAL NOT NULL DEFAULT 0,
                    unit TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(username, exercise_name, log_date, unit)
                )
                """
            )
            cursor.execute(
                """
                INSERT INTO exercise_daily_logs
                (username, exercise_name, log_date, total_amount, unit, created_at, updated_at)
                SELECT 'legacy', exercise_name, log_date, total_amount, unit, created_at, updated_at
                FROM exercise_daily_logs_legacy
                """
            )
            cursor.execute("DROP TABLE exercise_daily_logs_legacy")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS exercise_daily_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            exercise_name TEXT NOT NULL,
            log_date TEXT NOT NULL,
            total_amount REAL NOT NULL DEFAULT 0,
            unit TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, exercise_name, log_date, unit)
        )
        """
    )
    conn.commit()
    conn.close()


def save_exercise_log(username, exercise_name, amount, unit):
    if not is_registered_user(username):
        raise ValueError("Sadece kayitli kullanicilar veri kaydedebilir.")
    today = datetime.now().strftime("%Y-%m-%d")
    now_iso = datetime.now().isoformat(timespec="seconds")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO exercise_daily_logs
        (username, exercise_name, log_date, total_amount, unit, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(username, exercise_name, log_date, unit)
        DO UPDATE SET
            total_amount = total_amount + excluded.total_amount,
            updated_at = excluded.updated_at
        """,
        (username, exercise_name, today, float(amount), unit, now_iso, now_iso),
    )
    conn.commit()
    conn.close()


def get_daily_logs(username, log_date=None):
    if not is_registered_user(username):
        return []
    if log_date is None:
        log_date = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT exercise_name, total_amount, unit
        FROM exercise_daily_logs
        WHERE username = ? AND log_date = ?
        ORDER BY exercise_name ASC
        """,
        (username, log_date),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def format_daily_logs_text(username=None):
    if not username:
        return "Gunluk kayitlarinizi gormek icin username girin."
    if not is_registered_user(username):
        return "Bu username user_db.db icinde kayitli degil."
    today = datetime.now().strftime("%Y-%m-%d")
    rows = get_daily_logs(username, today)
    if not rows:
        return f"Bugun ({today}) kayit yok."

    lines = [f"Bugun ({today}) yaptiklarin:"]
    for exercise_name, total_amount, unit in rows:
        if unit == "seconds":
            amount_text = f"{total_amount:.1f} sn"
        else:
            amount_text = f"{int(total_amount)} tekrar"
        lines.append(f"- {exercise_name}: {amount_text}")

    if username:
        try:
            report = calculate_daily_exercise_report(username, today)
            lines.append("")
            lines.append("Kalori ozeti:")
            has_calorie_data = False
            for row in report.get("exercise_breakdown", []):
                if row.get("status") != "ok":
                    continue
                has_calorie_data = True
                lines.append(f"- {row['exercise_name']}: {row['calories']} kcal")
            if has_calorie_data:
                lines.append(f"Toplam: {report.get('total_exercise_kcal', 0)} kcal")
            else:
                lines.append("- Kalori hesabi icin hareket eslestirmesi bulunamadi.")
        except Exception as e:
            lines.append("")
            lines.append(f"Kalori hesabi yapilamadi: {e}")
    return "\n".join(lines)


class ExerciseTracker:
    """
    Shared helper for simple, consistent rep counting:
    - Applies mild temporal smoothing to angles.
    - Tracks whether specific positions are stable over frames.
    """

    def __init__(self, smoothing=0.6):
        self.prev_angles = {}  # key -> last smoothed angle
        self.smoothing = smoothing
        self.stability = {}  # key -> deque of recent boolean states
        self.current_lmlist = []
        self.img_w = 0
        self.img_h = 0

    def update_landmarks(self, lmlist, img):
        self.current_lmlist = lmlist
        self.img_h, self.img_w = img.shape[:2]

    def _is_landmark_visible(self, idx):
        if not self.current_lmlist or idx >= len(self.current_lmlist):
            return False
        x, y = self.current_lmlist[idx][1], self.current_lmlist[idx][2]
        # Require the landmark to be inside the image bounds.
        return 0 <= x < self.img_w and 0 <= y < self.img_h

    def has_visible_landmarks(self, *indices):
        return all(self._is_landmark_visible(i) for i in indices)

    def _smooth_angle(self, key, raw_angle):
        if key in self.prev_angles:
            angle = self.smoothing * raw_angle + (1 - self.smoothing) * self.prev_angles[key]
        else:
            angle = raw_angle
        self.prev_angles[key] = angle
        return angle

    def get_angle(self, img, p1, p2, p3, key):
        """
        Computes a single angle and applies temporal smoothing.
        """
        if not self.has_visible_landmarks(p1, p2, p3):
            return None
        try:
            raw_angle = detector.finfAngle(img, p1, p2, p3)
        except Exception:
            return None

        return self._smooth_angle(key, raw_angle)

    def calculate_bilateral_angles(self, img, lmlist, point_dict):
        """
        Shared helper for bilateral angles (left/right).
        point_dict: {'left': (p1, p2, p3), 'right': (p1, p2, p3)}
        """
        angles = {}
        for side, (p1, p2, p3) in point_dict.items():
            key = f"{side}_{p1}_{p2}_{p3}"
            try:
                raw_angle = detector.finfAngle(img, p1, p2, p3)
            except Exception:
                raw_angle = self.prev_angles.get(key, 0)

            angles[side] = self._smooth_angle(key, raw_angle)
        return angles

    def is_stable(self, key, state, window=5):
        """
        Returns whether a given state is stable over recent frames.
        Example: has open/closed position been held for at least `window` frames?
        """
        if key not in self.stability:
            self.stability[key] = deque(maxlen=window)

        dq = self.stability[key]
        dq.append(bool(state))
        return len(dq) == dq.maxlen and all(dq)

def exercise_logic(exercise_func):
    count = 0
    dir = 0
    start_time = time.time()
    tracker = ExerciseTracker()
    is_plank = exercise_func == plank_logic

    if not cap.isOpened():
        messagebox.showerror("Camera Error", "Unable to access the camera. Please make sure your camera is connected.")
        return

    # --- Fullscreen setup ---
    cv2.namedWindow("Exercise Detection", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("Exercise Detection", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    # --- Preparation countdown ---
    prep_seconds = 10
    prep_start = time.time()
    while True:
        success, img = cap.read()
        if not success:
            break
        img = cv2.resize(img, (CAM_W, CAM_H))

        elapsed = time.time() - prep_start
        remaining = max(0, prep_seconds - int(elapsed))
        if remaining == 0:
            break

        # Darken the frame with a semi-transparent black overlay
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (img.shape[1], img.shape[0]), (0, 0, 0), -1)
        img = cv2.addWeighted(overlay, 0.4, img, 0.6, 0)

        # "GET READY" text
        cv2.putText(
            img, "GET READY",
            (img.shape[1] // 2 - 200, img.shape[0] // 2 - 80),
            cv2.FONT_HERSHEY_DUPLEX, 3, (255, 255, 255), 4,
        )
        # Countdown number
        cv2.putText(
            img, str(remaining),
            (img.shape[1] // 2 - 60, img.shape[0] // 2 + 60),
            cv2.FONT_HERSHEY_DUPLEX, 5, (46, 204, 113), 5,
        )
        cv2.putText(
            img, "Get into position!",
            (img.shape[1] // 2 - 150, img.shape[0] // 2 + 130),
            cv2.FONT_HERSHEY_PLAIN, 2, (200, 200, 200), 2,
        )

        cv2.imshow("Exercise Detection", img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            cap.release()
            cv2.destroyAllWindows()
            return count

    # --- Main exercise loop ---
    try:
        while True:
            success, img = cap.read()
            if not success:
                # Stop loop if a frame cannot be read from camera
                break

            img = cv2.resize(img, (CAM_W, CAM_H))
            img = detector.findPose(img, False)
            lmlist = detector.findPosition(img, False)

            if len(lmlist) != 0:
                tracker.update_landmarks(lmlist, img)
                count, dir = exercise_func(img, lmlist, count, dir, tracker)

                if is_plank:
                    # For plank, show only the accumulated valid hold duration.
                    cv2.putText(
                        img,
                        f'Plank Time: {count:.1f} sec',
                        (50, 100),
                        cv2.FONT_HERSHEY_PLAIN,
                        3,
                        (255, 0, 0),
                        3,
                    )
                else:
                    # Show repetition and elapsed time
                    cv2.putText(
                        img,
                        f'Reps: {int(count)}',
                        (50, 100),
                        cv2.FONT_HERSHEY_PLAIN,
                        3,
                        (255, 0, 0),
                        3,
                    )
                    cv2.putText(
                        img,
                        f'Time: {int(time.time() - start_time)} sec',
                        (50, 150),
                        cv2.FONT_HERSHEY_PLAIN,
                        3,
                        (255, 0, 0),
                        3,
                    )

            cv2.imshow("Exercise Detection", img)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        cv2.destroyWindow("Exercise Detection")
    return count

def push_up_logic(img, lmlist, count, dir, tracker):
    """
    Push-up:
    - Uses bilateral elbow angles (averaged) for rep counting.
    - Checks body alignment via shoulder-hip-knee to prevent piked/sagging form.
    - Provides real-time angle feedback and arm-symmetry warnings.
    Logic:
      - Down: elbows bend past ~90° (angle < bottom_threshold)
      - Up: arms nearly straight (angle > top_threshold)
      - Up -> Down -> Up transition counts as 1 rep.
    """
    # Bilateral arm visibility
    right_ok = tracker.has_visible_landmarks(12, 14, 16)
    left_ok  = tracker.has_visible_landmarks(11, 13, 15)

    if not right_ok and not left_ok:
        cv2.putText(img, "Keep your arms visible in the frame!", (50, 200),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)
        return count, dir

    # --- Bilateral elbow angle (average both arms when both visible) ---
    elbow_angles = []
    for side, p1, p2, p3, key in [
        ("right", 12, 14, 16, "pushup_elbow_right"),
        ("left",  11, 13, 15, "pushup_elbow_left"),
    ]:
        a = tracker.get_angle(img, p1, p2, p3, key)
        if a is not None:
            elbow_angles.append(a)
    if not elbow_angles:
        return count, dir

    angle_elbow = sum(elbow_angles) / len(elbow_angles)

    # --- Body alignment: shoulder-hip-knee (both sides averaged) ---
    body_angles = []
    for p1, p2, p3, key in [
        (11, 23, 25, "pushup_body_left"),   # left shoulder-hip-knee
        (12, 24, 26, "pushup_body_right"),  # right shoulder-hip-knee
    ]:
        a = tracker.get_angle(img, p1, p2, p3, key)
        if a is not None:
            body_angles.append(a)

    body_ok = True  # default: don't block counting when form can't be assessed
    if body_angles:
        body_angle = sum(body_angles) / len(body_angles)
        # Perfect straight line = 180°, allow deviation based on tolerance
        body_ok = body_angle > (155 - PUSHUP_ANGLE_TOLERANCE)

    # --- Adjusted thresholds for realistic push-up range ---
    # Most people's elbow reaches ~90° at the bottom of a push-up
    top_angle = 150 - PUSHUP_ANGLE_TOLERANCE       # 136 — arm "up" above this
    bottom_angle = 90 + PUSHUP_ANGLE_TOLERANCE      # 104 — arm "down" below this

    at_top = angle_elbow > top_angle
    at_bottom = angle_elbow < bottom_angle

    # Count reps only when body form is acceptable
    if at_bottom and dir == 0 and body_ok:
        count += 0.5
        dir = 1
    if at_top and dir == 1 and body_ok:
        count += 0.5
        dir = 0

    # --- Visual feedback ---
    w = img.shape[1]

    # Progress bar: maps realistic elbow range (80°–150°) to screen width
    per = np.interp(angle_elbow, (80, 150), (0, 100))
    per = np.clip(per, 0, 100)
    bar_width = int(np.interp(per, (0, 100), (0, w)))
    cv2.rectangle(img, (50, 50), (bar_width, 100), (0, 255, 0), -1)

    # Show live elbow angle
    cv2.putText(img, f"Elbow: {int(angle_elbow)}", (50, 190),
                cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 255), 2)

    # Form feedback
    y_offset = 240
    if not body_ok:
        cv2.putText(img, "Keep your body straight (engage your core)!", (50, y_offset),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)
        y_offset += 40

    # Arm symmetry
    if len(elbow_angles) == 2:
        arm_diff = abs(elbow_angles[0] - elbow_angles[1])
        if arm_diff > 25:
            cv2.putText(img, "Keep both arms moving together!", (50, y_offset),
                        cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)

    return count, dir

def squats_logic(img, lmlist, count, dir, tracker):
    """
    Squat:
    - Uses right knee angle for rep counting (hip-knee-ankle: 24,26,28).
    - Checks torso uprightness via shoulder-hip-knee (12,24,26); reps are not
      counted if you lean too far forward.
    Logic:
      - Knee angle near ~85-90° is considered the "down" position,
      - Knee angle near ~165-170° is considered the "up" position.
      - Up -> Down -> Up transition counts as 1 rep.
    """
    # Right leg: hip, knee, ankle
    if not tracker.has_visible_landmarks(12, 24, 26, 28):
        cv2.putText(img, "Bring your full body into camera view!", (50, 200),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)
        return count, dir
    hip_r, knee_r, ankle_r = 24, 26, 28
    knee_angle = tracker.get_angle(img, hip_r, knee_r, ankle_r, "squat_knee")

    # Torso angle: shoulder, hip, knee
    shoulder_r, hip_r2, knee_r2 = 12, 24, 26
    torso_angle = tracker.get_angle(img, shoulder_r, hip_r2, knee_r2, "squat_torso")
    if knee_angle is None or torso_angle is None:
        return count, dir

    # Torso uprightness: ideal is ~180°; slight tolerance
    torso_ok = torso_angle > (155 - SQUAT_TOLERANCE)

    # Knee angle thresholds (in degrees)
    top_angle = 165 - SQUAT_TOLERANCE
    bottom_angle = 95 + SQUAT_TOLERANCE

    at_top = knee_angle > top_angle
    at_bottom = knee_angle < bottom_angle

    # Count reps only when torso form is acceptable
    if at_bottom and dir == 0 and torso_ok:
        count += 0.5
        dir = 1
    if at_top and dir == 1 and torso_ok:
        count += 0.5
        dir = 0

    # Visual progress bar (0: standing, 100: deep squat)
    depth_per = np.interp(knee_angle, (top_angle, bottom_angle), (0, 100))
    depth_per = np.clip(depth_per, 0, 100)
    progress_bar = np.interp(depth_per, (0, 100), (0, img.shape[1]))
    cv2.rectangle(img, (50, 50), (int(progress_bar), 100), (0, 255, 0), -1)

    # Form feedback
    if not torso_ok:
        cv2.putText(img, "Keep your torso more upright!", (50, 200),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)

    return count, dir

def plank_logic(img, lmlist, count, dir, tracker):
    """
    Plank:
    - Tracks accumulated hold time while form is correct.
    - Body must form a straight line (shoulder-hip-ankle ~180°).
    - Body must be horizontal (not standing/upright).
    - Arms must be engaged (shoulders elevated off the ground — prevents
      counting time while lying flat to rest).
    - Timer pauses when form breaks and resumes when form returns.
    """
    # Bilateral visibility check — require at least one full body side
    left_visible = tracker.has_visible_landmarks(11, 23, 27)
    right_visible = tracker.has_visible_landmarks(12, 24, 28)

    if not left_visible and not right_visible:
        cv2.putText(img, "Bring your full body into camera view!", (50, 200),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)
        return count, dir

    # Body angle from whichever side(s) are visible
    body_angles = []
    if left_visible:
        a = tracker.get_angle(img, 11, 23, 27, "plank_left_body")
        if a is not None:
            body_angles.append(a)
    if right_visible:
        a = tracker.get_angle(img, 12, 24, 28, "plank_right_body")
        if a is not None:
            body_angles.append(a)
    if not body_angles:
        return count, dir

    body_angle = sum(body_angles) / len(body_angles)

    # Good plank form is close to a straight line (~180 degrees)
    angle_ok = (155 - PLANK_ANGLE_TOLERANCE) <= body_angle <= (205 + PLANK_ANGLE_TOLERANCE)

    # Knee angle from whichever side(s) are visible — straight legs are required for plank
    knee_angles = []
    knee_left = tracker.has_visible_landmarks(23, 25, 27)
    knee_right = tracker.has_visible_landmarks(24, 26, 28)
    if knee_left:
        a = tracker.get_angle(img, 23, 25, 27, "plank_knee_left")
        if a is not None:
            knee_angles.append(a)
    if knee_right:
        a = tracker.get_angle(img, 24, 26, 28, "plank_knee_right")
        if a is not None:
            knee_angles.append(a)

    knee_angle = sum(knee_angles) / len(knee_angles) if knee_angles else 180
    knees_straight = not knee_angles or knee_angle > (180 - PLANK_ANGLE_TOLERANCE)

    # Body orientation: in a plank, shoulders and hips are at similar height in the frame.
    # In a standing position, shoulders are significantly above hips.
    # This is more robust than absolute Y proximity since it relies on relative body orientation.
    img_h = img.shape[0]
    img_w = img.shape[1]
    shoulder_avg_y = (lmlist[11][2] + lmlist[12][2]) / 2
    hip_avg_y = (lmlist[23][2] + lmlist[24][2]) / 2
    # If shoulders are significantly above hips, the person is standing, not planking
    is_horizontal = abs(shoulder_avg_y - hip_avg_y) < img_h * 0.15

    # Arms-engaged check: prevents timer counting when lying flat on the ground.
    # Uses two independent signals to confirm the body is actively supported:
    #
    # Signal A — shoulder-to-hand depth separation:
    #   In a plank, shoulders are elevated while hands stay on the ground,
    #   creating a clear Y gap in the image. When lying flat with arms by the
    #   sides or tucked near the body, that gap nearly disappears.
    #
    # Signal B — hip-to-ankle depth separation:
    #   In a plank the core is lifted, so hips sit at a noticeably different
    #   Y from the ankles. When lying flat everything is on the ground, so
    #   hips and ankles land at nearly the same Y regardless of arm position.
    #
    # Both signals must be present — this eliminates false positives from
    # lying-flat positions with arms stretched forward (Signal A alone
    # would see a big Y gap, but Signal B catches that the core isn't lifted).
    support_y = None
    if tracker.has_visible_landmarks(15, 16):
        support_y = (lmlist[15][2] + lmlist[16][2]) / 2   # wrist midpoint
    elif tracker.has_visible_landmarks(13, 14):
        support_y = (lmlist[13][2] + lmlist[14][2]) / 2   # elbow midpoint as fallback

    hip_mid_y = (lmlist[23][2] + lmlist[24][2]) / 2
    ankle_avg_y = (lmlist[27][2] + lmlist[28][2]) / 2

    arms_engaged = True  # default pass if we can't assess
    if support_y is not None:
        depth_arm = abs(shoulder_avg_y - support_y) > img_h * 0.06
        depth_core = abs(hip_mid_y - ankle_avg_y) > img_h * 0.06
        arms_engaged = depth_arm and depth_core

    form_ok = angle_ok and is_horizontal and arms_engaged and knees_straight

    # Timer: track accumulated hold time, properly pausing during bad form
    if not hasattr(tracker, "runtime"):
        tracker.runtime = {}

    if form_ok:
        now = time.time()
        last_ts = tracker.runtime.get("plank_last_ts", now)
        delta = max(0.0, now - last_ts)
        count += delta
        tracker.runtime["plank_last_ts"] = now
    else:
        # Reset reference so the next good-form frame starts from a clean timestamp,
        # preventing bad-form time gaps from leaking into the count.
        tracker.runtime["plank_last_ts"] = time.time()

    # Progress bar: maps body angle toward ideal 180°
    angle_score = np.interp(body_angle, (140, 180), (0, 100))
    angle_score = np.clip(angle_score, 0, 100)
    bar_width = int(np.interp(angle_score, (0, 100), (0, img.shape[1])))
    cv2.rectangle(img, (50, 50), (bar_width, 100), (0, 255, 0), -1)

    # Live body angle display
    cv2.putText(img, f"Body: {int(body_angle)}  Knee: {int(knee_angle)}", (50, 180),
                cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 255), 2)

    # Specific form feedback
    feedback_y = 220
    if not arms_engaged:
        cv2.putText(img, "Lift your body up! You're lying flat.", (50, feedback_y),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)
        feedback_y += 40
    elif not knees_straight:
        cv2.putText(img, "Straighten your legs — don't bend your knees!", (50, feedback_y),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)
        feedback_y += 40
    elif not angle_ok:
        cv2.putText(img, "Keep your body straight (engage your core)!", (50, feedback_y),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)
        feedback_y += 40
    elif not is_horizontal:
        cv2.putText(img, "Get into a horizontal plank position!", (50, feedback_y),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)

    return count, dir

def arm_raise_logic(img, lmlist, count, dir, tracker):
    """
    Arm Raise (Standing):
    - A simple movement for camera tracking:
      arms start down at the sides, then move above shoulders/head, then back down.
    - Uses wrist and shoulder Y positions (image coordinates) for robust counting.
    Logic:
      - DOWN: wrists are clearly below shoulders
      - UP: wrists are clearly above shoulders
      - Down -> Up -> Down transition counts as 1 rep.
    """
    img_h = img.shape[0]

    # Landmark Y positions (smaller Y = higher on the image)
    if not tracker.has_visible_landmarks(11, 12, 15, 16):
        cv2.putText(img, "Keep shoulders and wrists visible!", (50, 200),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)
        return count, dir
    left_wrist_y = lmlist[15][2]
    right_wrist_y = lmlist[16][2]
    left_shoulder_y = lmlist[11][2]
    right_shoulder_y = lmlist[12][2]

    wrist_avg_y = (left_wrist_y + right_wrist_y) / 2
    shoulder_avg_y = (left_shoulder_y + right_shoulder_y) / 2

    # Pixel margins scaled with image height for better robustness
    down_margin = img_h * ARM_RAISE_DOWN_MARGIN_RATIO
    up_margin = img_h * ARM_RAISE_UP_MARGIN_RATIO

    wrists_up = wrist_avg_y < (shoulder_avg_y - up_margin)
    wrists_down = wrist_avg_y > (shoulder_avg_y + down_margin)

    # Stabilize transitions to avoid noisy frame-to-frame jumps
    stable_up = tracker.is_stable("arm_raise_up", wrists_up, window=ARM_RAISE_STABLE_WINDOW)
    stable_down = tracker.is_stable("arm_raise_down", wrists_down, window=ARM_RAISE_STABLE_WINDOW)

    if stable_up and dir == 0:
        count += 0.5
        dir = 1
    if stable_down and dir == 1:
        count += 0.5
        dir = 0

    # Progress: higher wrists => higher percentage
    per = np.interp(wrist_avg_y, (img_h * 0.85, img_h * 0.20), (0, 100))
    per = np.clip(per, 0, 100)
    progress_bar = np.interp(per, (0, 100), (0, img.shape[1]))
    cv2.rectangle(img, (50, 50), (int(progress_bar), 100), (0, 255, 0), -1)

    # Basic form cue: keep both arms moving together
    wrist_gap = abs(left_wrist_y - right_wrist_y)
    if wrist_gap > img_h * 0.20:
        cv2.putText(img, "Raise both arms together!", (50, 200),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)

    return count, dir


def sit_up_logic(img, lmlist, count, dir, tracker):
    """
    Sit-up:
    - Uses hip angle (shoulder-hip-knee) which changes MONOTONICALLY
      during a sit-up — only decreases when sitting up, only increases
      when lying back down. This eliminates the V-shaped double-counting
      problem from nose-shoulder-hip angle.
    Logic:
      - Lying down: shoulder, hip, knee in a line → angle near 180
      - Sitting up: body folds at hip → angle decreases to ~70-90
      - Down -> Up -> Down transition counts as 1 rep.
    """
    # Bilateral hip angle: at least one side visible
    right_ok = tracker.has_visible_landmarks(12, 24, 26)
    left_ok = tracker.has_visible_landmarks(11, 23, 25)

    if not right_ok and not left_ok:
        cv2.putText(img, "Position so your shoulders, hips and knees are visible!", (50, 200),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)
        return count, dir

    # Bilateral hip angle
    body_angles = []
    if right_ok:
        a = tracker.get_angle(img, 12, 24, 26, "situp_hip_right")
        if a is not None:
            body_angles.append(a)
    if left_ok:
        a = tracker.get_angle(img, 11, 23, 25, "situp_hip_left")
        if a is not None:
            body_angles.append(a)
    if not body_angles:
        return count, dir

    body_angle = sum(body_angles) / len(body_angles)

    TOLERANCE = 15
    TOP = 100      # sitting up = body folded at hip
    BOTTOM = 160   # lying down = body straight

    at_top = body_angle < (TOP + TOLERANCE)        # < 115
    at_bottom = body_angle > (BOTTOM - TOLERANCE)  # > 145

    # State-machine initialisation: skip the free half-rep when starting lying flat
    if not hasattr(tracker, "situp_ready"):
        tracker.situp_ready = True
        if at_bottom:
            dir = 1  # Already lying down → expect an "up" movement first

    if at_bottom and dir == 0:
        count += 0.5
        dir = 1
    if at_top and dir == 1:
        count += 0.5
        dir = 0

    # Progress bar
    per = np.interp(body_angle, (TOP, BOTTOM), (0, 100))
    per = np.clip(per, 0, 100)
    bar_width = int(np.interp(per, (0, 100), (0, img.shape[1])))
    cv2.rectangle(img, (50, 50), (bar_width, 100), (0, 255, 0), -1)

    # Angle display
    cv2.putText(img, f"Hip: {int(body_angle)}", (50, 180),
                cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 255), 2)

    return count, dir


def march_in_place_logic(img, lmlist, count, dir, tracker):
    """
    March in Place:
    - Each leg has its own state machine: down -> up -> down = 1 rep per leg.
    - Uses KNEE ANGLE (hip-knee-ankle), not Y-position, so it works
      regardless of camera angle or how high the knee is lifted.
    Logic:
      - Standing: knee straight → angle near 180
      - Marching: knee bent → angle drops to ~90-130
      - Straight -> Bent -> Straight = 1 rep per leg.
    """
    left_ok = tracker.has_visible_landmarks(23, 25, 27)
    right_ok = tracker.has_visible_landmarks(24, 26, 28)

    if not left_ok and not right_ok:
        cv2.putText(img, "Position so your hips, knees and ankles are visible!", (50, 200),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)
        return count, dir

    # Per-leg state machine
    if not hasattr(tracker, "march_state"):
        tracker.march_state = {"left": 0, "right": 0}
    ms = tracker.march_state

    LEFT_UP = 140    # knee angle below this = lifted
    LEFT_DOWN = 160  # knee angle above this = extended

    left_angle = None
    right_angle = None

    # --- Left leg ---
    if left_ok:
        a = tracker.get_angle(img, 23, 25, 27, "march_knee_left")
        if a is not None:
            left_angle = a
            if a < LEFT_UP and ms["left"] == 0:
                count += 1
                ms["left"] = 1
            elif a > LEFT_DOWN and ms["left"] == 1:
                ms["left"] = 0

    # --- Right leg ---
    if right_ok:
        a = tracker.get_angle(img, 24, 26, 28, "march_knee_right")
        if a is not None:
            right_angle = a
            if a < LEFT_UP and ms["right"] == 0:
                count += 1
                ms["right"] = 1
            elif a > LEFT_DOWN and ms["right"] == 1:
                ms["right"] = 0

    # Progress bar
    both_up = ms["left"] + ms["right"]
    per = np.interp(both_up, (0, 2), (0, 100))
    per = np.clip(per, 0, 100)
    bar_width = int(np.interp(per, (0, 100), (0, img.shape[1])))
    cv2.rectangle(img, (50, 50), (bar_width, 100), (0, 255, 0), -1)

    # Knee angle display
    if left_angle is not None and right_angle is not None:
        cv2.putText(img, f"L: {int(left_angle)}  R: {int(right_angle)}", (50, 190),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 255), 2)
    elif left_angle is not None:
        cv2.putText(img, f"Left knee: {int(left_angle)}", (50, 190),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 255), 2)
    elif right_angle is not None:
        cv2.putText(img, f"Right knee: {int(right_angle)}", (50, 190),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 255), 2)

    return count, dir


def jump_logic(img, lmlist, count, dir, tracker):
    """
    Jump (vertical jump in place):
    - Tracks the hip center vertical oscillation relative to an adaptive baseline.
    - When hips rise significantly above the baseline → jumped.
    - When hips return to baseline → landed.
    - Landed → Jumped → Landed = 1 rep.

    The baseline snap-resets on landing so the next jump starts from a clean
    reference regardless of drift during the air phase.
    """
    img_h = img.shape[0]

    if not tracker.has_visible_landmarks(23, 24):
        cv2.putText(img, "Position so your hips are visible!", (50, 200),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 255), 2)
        return count, dir

    hip_center_y = (lmlist[23][2] + lmlist[24][2]) / 2

    # Initialise baseline on first frame
    if not hasattr(tracker, "jump_baseline"):
        tracker.jump_baseline = hip_center_y
        tracker.jump_landed_y = hip_center_y

    # ── thresholds (proportion of frame height) ──────────────────────────
    UP_MARGIN = 0.04    # 4 % above baseline → jumped
    DOWN_MARGIN = 0.02  # within 2 % of baseline → landed
    RISE = UP_MARGIN * img_h

    jumped = (tracker.jump_baseline - hip_center_y) > RISE
    landed = abs(hip_center_y - tracker.jump_baseline) < DOWN_MARGIN * img_h

    # ── count state machine ─────────────────────────────────────────────
    if jumped and dir == 0:
        count += 0.5
        dir = 1
    if landed and dir == 1:
        count += 0.5
        dir = 0
        # Snap baseline to current landing position to avoid drift,
        # then let the slow EMA keep it stable between reps.
        tracker.jump_baseline = hip_center_y

    # ── baseline drift correction (only on ground) ──────────────────────
    if dir == 0:
        alpha = 0.04
        tracker.jump_baseline = (1 - alpha) * tracker.jump_baseline + alpha * hip_center_y

    # ── visual feedback ─────────────────────────────────────────────────
    # Live hip offset display
    offset_px = tracker.jump_baseline - hip_center_y
    offset_pct = offset_px / RISE * 100
    cv2.putText(img, f"Hip offset: {offset_px:+.0f}px  ({offset_pct:+.0f}%)", (50, 180),
                cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 255), 2)
    cv2.putText(img, f"State: {'AIR' if dir else 'GROUND'}", (50, 210),
                cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 255), 2)

    # Progress bar: empty at baseline, full at UP_MARGIN rise
    per = np.clip(offset_px / RISE * 100, 0, 100)
    bar_width = int(np.interp(per, (0, 100), (0, img.shape[1])))
    color = (0, 255, 0) if per >= 100 else (100, 100, 255)
    cv2.rectangle(img, (50, 50), (bar_width, 100), color, -1)

    return count, dir


def open_exercise_logs_window(parent, username):
    """Open a window showing today's exercise logs with delete buttons."""
    if not username:
        messagebox.showwarning("Warning", "Please enter your username first.")
        return
    if not is_registered_user(username):
        messagebox.showerror("Unauthorized", "Bu username kayitli degil.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")

    window = tk.Toplevel(parent)
    window.title("Exercise Logs")
    window.geometry("480x400")
    window.resizable(True, True)
    window.configure(bg="#10131a")

    header = tk.Label(
        window,
        text=f"Today's Exercise Logs",
        font=("Arial", 14, "bold"),
        bg="#10131a",
        fg="#f4f7ff",
    )
    header.pack(pady=(14, 6))

    list_frame = tk.Frame(window, bg="#10131a")
    list_frame.pack(padx=14, pady=6, fill="both", expand=True)

    record_list = tk.Listbox(list_frame, height=14, font=("Consolas", 11))
    record_list.pack(side="left", fill="both", expand=True)

    scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=record_list.yview)
    scrollbar.pack(side="right", fill="y")
    record_list.config(yscrollcommand=scrollbar.set, bg="#1a2233", fg="#e0e8f5", selectbackground="#2997ff")

    record_ids = []

    def refresh():
        record_list.delete(0, tk.END)
        record_ids.clear()
        cursor.execute(
            "SELECT id, exercise_name, total_amount, unit FROM exercise_daily_logs "
            "WHERE username = ? AND log_date = ? ORDER BY id ASC",
            (username, today),
        )
        for rid, name, amount, unit in cursor.fetchall():
            record_ids.append(rid)
            label = f"{amount:.0f} sec" if unit == "seconds" else f"{int(amount)} reps"
            record_list.insert(tk.END, f"{name:20s}  {label}")

    def delete_selected():
        sel = record_list.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Select a log to delete.")
            return
        rid = record_ids[sel[0]]
        if messagebox.askyesno("Confirm", "Delete this log entry?"):
            cursor.execute("DELETE FROM exercise_daily_logs WHERE id = ?", (rid,))
            conn.commit()
            refresh()

    refresh()

    btn_frame = tk.Frame(window, bg="#10131a")
    btn_frame.pack(pady=(4, 14))

    delete_btn = tk.Button(
        btn_frame, text="Delete Selected", width=16,
        command=delete_selected, bg="#ff5f5f", fg="white",
        relief="flat", bd=0, cursor="hand2",
    )
    delete_btn.pack(side="left", padx=6)

    close_btn = tk.Button(
        btn_frame, text="Close", width=12,
        command=window.destroy, bg="#24314a", fg="#f4f7ff",
        relief="flat", bd=0, cursor="hand2",
    )
    close_btn.pack(side="left", padx=6)

    window.protocol("WM_DELETE_WINDOW", lambda: (conn.close(), window.destroy()))


# Create the GUI window
root = tk.Tk()
root.title("AI Fitness Trainer")
root.geometry("460x620")
root.minsize(400, 500)
root.resizable(True, True)

# UI theme colors
BG_COLOR = "#10131a"
CARD_COLOR = "#1a2233"
TEXT_PRIMARY = "#f4f7ff"
TEXT_SECONDARY = "#a8b3cc"
ACCENT_GREEN = "#2ecc71"
ACCENT_GREEN_HOVER = "#29b866"
ACCENT_RED = "#ff5f5f"
ACCENT_RED_HOVER = "#e45454"
FIELD_BG = "#24314a"

# Style the window
root.configure(bg=BG_COLOR)

main_frame = tk.Frame(root, bg=BG_COLOR)
main_frame.pack(fill="both", expand=True, padx=22, pady=22)

card = tk.Frame(main_frame, bg=CARD_COLOR, bd=0, highlightthickness=0)
card.pack(fill="both", expand=True)

title_label = tk.Label(
    card,
    text="AI FITNESS TRAINER",
    font=("Arial", 18, "bold"),
    bg=CARD_COLOR,
    fg=TEXT_PRIMARY,
)
title_label.pack(pady=(26, 6))

subtitle_label = tk.Label(
    card,
    text="Choose an exercise and start your session",
    font=("Arial", 10),
    bg=CARD_COLOR,
    fg=TEXT_SECONDARY,
)
subtitle_label.pack(pady=(0, 20))

# Username input (required for calorie calculation with user profile)
username_label = tk.Label(
    card,
    text="Username",
    font=("Arial", 11, "bold"),
    bg=CARD_COLOR,
    fg=TEXT_PRIMARY,
)
username_label.pack(anchor="w", padx=36)

username_entry = tk.Entry(
    card,
    width=28,
    font=("Arial", 11),
    bg=FIELD_BG,
    fg=TEXT_PRIMARY,
    insertbackground=TEXT_PRIMARY,
    relief="flat",
)
if args.username:
    username_entry.insert(0, args.username)
    username_entry.config(state="readonly", fg="#2997ff")
username_entry.pack(pady=(8, 18))

# Exercise selection
exercise_var = tk.StringVar()
exercise_var.set("Push-up")

exercises = {
    "Push-up": push_up_logic,
    "Squat": squats_logic,
    "Plank": plank_logic,
    "Sit-up": sit_up_logic,
    "March": march_in_place_logic,
    "Arm Raise": arm_raise_logic,
    "Jump": jump_logic,
}

# Exercise selection label
exercise_label = tk.Label(
    card,
    text="Exercise",
    font=("Arial", 11, "bold"),
    bg=CARD_COLOR,
    fg=TEXT_PRIMARY,
)
exercise_label.pack(anchor="w", padx=36)

# Create styled option menu
exercise_menu = tk.OptionMenu(card, exercise_var, *exercises.keys())
exercise_menu.configure(
    width=22,
    font=("Arial", 11),
    bg=FIELD_BG,
    fg=TEXT_PRIMARY,
    activebackground="#2d3d5e",
    activeforeground=TEXT_PRIMARY,
    relief="flat",
    highlightthickness=0,
    bd=0,
)
exercise_menu["menu"].configure(
    bg=FIELD_BG,
    fg=TEXT_PRIMARY,
    activebackground="#2d3d5e",
    activeforeground=TEXT_PRIMARY,
    bd=0,
    relief="flat",
)
exercise_menu.pack(pady=(10, 28))

# Function to start exercise
def start_exercise():
    selected_exercise = exercise_var.get()
    username = username_entry.get().strip()
    if not username:
        messagebox.showwarning("Eksik Bilgi", "Kalori hesabi icin lutfen username girin.")
        return
    if not is_registered_user(username):
        messagebox.showerror("Yetkisiz", "Bu username user_db.db icinde kayitli degil.")
        return

    root.iconify()  # Minimize window during exercise
    result = exercise_logic(exercises[selected_exercise])
    root.deiconify()  # Restore window after exercise
    try:
        unit = "seconds" if selected_exercise == "Plank" else "reps"
        save_exercise_log(username, selected_exercise, result, unit)
        daily_logs_label.config(text=format_daily_logs_text(username))
        if unit == "seconds":
            result_text = f"{result:.1f} saniye"
        else:
            result_text = f"{int(result)} tekrar"

        calorie_text = "Kalori hesabi yapilamadi."
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            report = calculate_daily_exercise_report(username, today)
            save_daily_exercise_report_to_calorie_db(report)
            current_exercise = next(
                (
                    row
                    for row in report.get("exercise_breakdown", [])
                    if row.get("status") == "ok"
                    and row.get("exercise_name", "").strip().lower()
                    == selected_exercise.strip().lower()
                ),
                None,
            )
            if current_exercise:
                calorie_text = (
                    f"{selected_exercise} bugun toplam: {current_exercise['calories']} kcal\n"
                    f"Gunluk egzersiz toplam: {report.get('total_exercise_kcal', 0)} kcal"
                )
            else:
                calorie_text = (
                    f"Gunluk egzersiz toplam: {report.get('total_exercise_kcal', 0)} kcal"
                )
        except Exception as calorie_error:
            calorie_text = f"Kalori hesabi yapilamadi: {calorie_error}"

        messagebox.showinfo(
            "Kaydedildi",
            (
                f"{selected_exercise}: {result_text}\n"
                f"Tarih: {datetime.now().strftime('%Y-%m-%d')}\n"
                f"{calorie_text}"
            ),
        )
    except Exception as e:
        messagebox.showerror("Database Error", f"Kayıt sırasında hata oluştu:\n{e}")

# Create styled button
start_button = tk.Button(
    card,
    text="Start Exercise",
    command=start_exercise,
    font=("Arial", 12, "bold"),
    bg=ACCENT_GREEN,
    fg="white",
    activebackground=ACCENT_GREEN_HOVER,
    activeforeground="white",
    width=20,
    height=2,
    relief="flat",
    bd=0,
    cursor="hand2",
)
start_button.pack(pady=(4, 14))

# Add quit button
quit_button = tk.Button(
    card,
    text="Quit",
    command=root.quit,
    font=("Arial", 11, "bold"),
    bg=ACCENT_RED,
    fg="white",
    activebackground=ACCENT_RED_HOVER,
    activeforeground="white",
    width=20,
    height=1,
    relief="flat",
    bd=0,
    cursor="hand2",
)
quit_button.pack(pady=(0, 6))

# AI Coach button
ai_coach_button = tk.Button(
    card,
    text="AI Coach",
    command=lambda: open_ai_coach_window(root, username_entry.get().strip()),
    font=("Arial", 11, "bold"),
    bg="#6c63ff",
    fg="white",
    activebackground="#5a52e0",
    activeforeground="white",
    width=20,
    height=1,
    relief="flat",
    bd=0,
    cursor="hand2",
)
ai_coach_button.pack(pady=(0, 10))

# Exercise Logs button
exercise_logs_button = tk.Button(
    card,
    text="Exercise Logs",
    command=lambda: open_exercise_logs_window(root, username_entry.get().strip()),
    font=("Arial", 11, "bold"),
    bg="#2997ff",
    fg="white",
    activebackground="#1a7ae0",
    activeforeground="white",
    width=20,
    height=1,
    relief="flat",
    bd=0,
    cursor="hand2",
)
exercise_logs_button.pack(pady=(0, 24))

hint_label = tk.Label(
    card,
    text="Tip: Press 'q' to exit camera mode quickly",
    font=("Arial", 9),
    bg=CARD_COLOR,
    fg=TEXT_SECONDARY,
)
hint_label.pack()

daily_logs_label = tk.Label(
    card,
    text="",
    font=("Arial", 10),
    bg=CARD_COLOR,
    fg=TEXT_SECONDARY,
    justify="left",
    anchor="w",
)
daily_logs_label.pack(fill="x", padx=36, pady=(14, 10))

# Prepare database table on app start
init_database()
daily_logs_label.config(text=format_daily_logs_text(username_entry.get().strip()))

# Run the application
root.mainloop()

# Clean up
cap.release()
cv2.destroyAllWindows()