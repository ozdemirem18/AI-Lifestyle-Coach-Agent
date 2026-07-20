# Appendix

## Appendix A — Database Schemas

The application uses **seven SQLite databases** stored in `C:\project_database\`. Each tracker module owns its own database file. All schemas follow the same pattern: an auto-increment integer primary key, a `username` field (added via migration to legacy tables), a date field, and a numeric value field.

### A.1 User Database (`user_db.db`)

```sql
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
);
```

Migration columns (added if missing via `ALTER TABLE`): `age`, `height_cm`, `weight_kg`, `bmi`, `ideal_weight_min`, `ideal_weight_max`, `target_weight_kg`, `gender`. Legacy `cinsiyet` column is migrated to `gender` with Turkish-to-English mapping (Kadın→Female, Erkek→Male, Diğer→Other).

### A.2 Exercise Database (`spor_db.db`)

```sql
CREATE TABLE IF NOT EXISTS exercise_daily_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    exercise_name TEXT NOT NULL,
    log_date TEXT NOT NULL,
    total_amount REAL NOT NULL DEFAULT 0,
    unit TEXT NOT NULL,              -- 'reps' or 'seconds'
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(username, exercise_name, log_date, unit)
);
```

### A.3 Calorie Database (`calorie_db.db`)

```sql
-- Food intake records
CREATE TABLE IF NOT EXISTS daily_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL DEFAULT 'legacy',
    record_date TEXT,
    food_name TEXT,
    weight_grams REAL,
    calories REAL
);

-- Exercise calorie logs (from spor_calorie_f.py)
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
);

-- Daily exercise calorie summary (from spor_calorie_f.py)
CREATE TABLE IF NOT EXISTS exercise_calorie_daily_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    log_date TEXT NOT NULL,
    total_exercise_kcal REAL NOT NULL DEFAULT 0,
    bmr_kcal_per_day REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE(username, log_date)
);
```

### A.4 Water Database (`water_db.db`)

```sql
CREATE TABLE IF NOT EXISTS water_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL DEFAULT 'legacy',
    record_date TEXT NOT NULL,
    water_ml REAL NOT NULL
);
```

### A.5 Sleep Database (`sleep_db.db`)

```sql
CREATE TABLE IF NOT EXISTS sleep_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL DEFAULT 'legacy',
    record_date TEXT NOT NULL,
    sleep_hours REAL NOT NULL
);
```

### A.6 Step Database (`step_db.db`)

```sql
CREATE TABLE IF NOT EXISTS step_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL DEFAULT 'legacy',
    record_date TEXT NOT NULL,
    steps INTEGER NOT NULL
);
```

### A.7 AI Coach Database (`coach_db.db`)

```sql
CREATE TABLE IF NOT EXISTS ai_coach_chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT 'New Chat',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_coach_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES ai_coach_chats(id)
);
```

---

## Appendix B — Exercise Angle Thresholds and Rep Counting Logic

All seven exercises use the **MediaPipe Pose 33-landmark topology**. Angles are computed using `math.atan2` on landmark pixel coordinates and smoothed with an exponential moving average (smoothing factor = 0.6) via the `ExerciseTracker` class. Rep counting follows a state-machine pattern: each exercise transitions between an "up" and "down" (or "ground" and "air") state; one full cycle counts as one rep.

| Exercise | Tracked Landmarks | Angle / Metric | Up Threshold | Down Threshold | Form Checks |
|---|---|---|---|---|---|
| **Push-up** | 11–13–15 (left elbow), 12–14–16 (right elbow) | Bilateral elbow angle (averaged) | > 136° | < 104° | Body straightness: shoulder–hip–knee > 155°; arm symmetry: difference < 25° |
| **Squat** | 24–26–28 (right knee) | Knee angle | > 155° | < 105° | Torso uprightness: shoulder–hip–knee > 145° |
| **Plank** | 11–23–27 / 12–24–28 (body), 23–25–27 / 24–26–28 (knee) | Body angle (shoulder–hip–ankle) and knee straightness | Hold timer (accumulated seconds) while form is correct | N/A | Body angle within [143°, 217°]; knees > 168°; body must be horizontal (shoulder Y ≈ hip Y) |
| **Sit-up** | 12–24–26 / 11–23–25 (hip angle) | Hip angle (shoulder–hip–knee) | < 115° (sitting up) | > 145° (lying down) | None (single-angle monotonic tracking) |
| **March** | 23–25–27 (left knee), 24–26–28 (right knee) | Knee angle per leg, independent state machines | < 140° (knee lifted) | > 160° (leg extended) | None |
| **Arm Raise** | 15, 16 (wrists), 11, 12 (shoulders) | Wrist Y vs shoulder Y (pixel positions) | Wrist above shoulder by > 10% of frame height | Wrist below shoulder by > 12% of frame height | Arm symmetry: wrist Y gap < 20% of frame height; stability window: 6 frames |
| **Jump** | 23, 24 (hip center Y) | Hip vertical oscillation relative to adaptive baseline | Hip rises > 4% frame height above baseline | Hip returns within 2% frame height of baseline | Adaptive baseline drift correction (EMA alpha = 0.04) |

Tolerance constants used across exercises: `PUSHUP_ANGLE_TOLERANCE = 14`, `PLANK_ANGLE_TOLERANCE = 12`, `ANGLE_TOLERANCE = 20`, `SQUAT_TOLERANCE = 10`.

---

## Appendix C — Test Results

Three test suites were implemented covering unit, integration, and HCI (Human–Computer Interaction) testing.

### C.1 Unit Tests — `tests/test_water.py`

**Scope**: `water/water_f.py` — user validation, database setup, schema migration, and core SQL operations.

```
Ran 17 tests in 24.889s
OK
```

| Test Class | Tests | Coverage |
|---|---|---|
| `TestIsRegisteredUser` | 5 | Registered/unregistered/empty/None/whitespace-trimmed lookup |
| `TestSetupDatabase` | 6 | Directory creation, table schema, column types, auto-increment PK, idempotency, legacy migration |
| `TestStartGuiValidation` | 2 | Unregistered user guard |
| `TestDatabaseOperations` | 4 | Insert, sum, zero-sum for empty day, delete, multi-user isolation |

### C.2 Integration Tests — `tests/integration_test_register.py`

**Scope**: `user/user_f.py` — full registration flow against a real SQLite database in a temp directory. Only `DB_FILE` is patched; no database-layer mocks.

```
Ran 25 tests in 0.518s
OK
```

| Category | Tests | Coverage |
|---|---|---|
| Schema | 2 | Table creation, idempotency |
| Register flow | 3 | Create → exists → hash persists → count increments |
| Duplicates | 1 | IntegrityError on duplicate username |
| Password hashing | 4 | SHA-256 hex, deterministic, diff-input diff-output, Unicode |
| Password validation | 6 | 8-char minimum, uppercase, lowercase, digit, valid empty, multiple issues |
| Hash edge cases | 1 | None for nonexistent user |
| Login round-trip | 1 | Register hash matches login hash |
| Profile save | 2 | All fields persist, partial overwrite |
| Body metrics | 3 | Adult (18.5–24.9), senior (22–27), under-18 (18.5–24.0) BMI ranges |
| User exists edge cases | 2 | Empty string, case sensitivity |

### C.3 HCI Tests — `tests/test_hci.py`

**Scope**: All user-facing modules evaluated against Jakob Nielsen's 10 usability heuristics. Tests validate UI strings, validation logic, feedback messages, interaction patterns, and cross-module consistency.

```
Ran 60 tests in 0.036s
OK
```

| Heuristic | Tests | Focus |
|---|---|---|
| H1 — Visibility of system status | 3 | Exercise feedback messages, result count+unit, daily totals |
| H2 — Match system and real world | 4 | Plain window titles, standard exercise names, real-world units, inclusive gender |
| H3 — User control and freedom | 4 | Delete + confirm on all trackers, minimize/restore, Exit buttons |
| H4 — Consistency and standards | 5 | Window geometry, button title case, uniform error wording, dark theme |
| H5 — Error prevention | 7 | Password rules pre-submit, confirmation field, empty/zero rejection, default exercise |
| H6 — Recognition over recall | 4 | Dropdowns, OptionMenu, descriptive titles, date in header |
| H7 — Flexibility and efficiency | 2 | CLI --username flag, 'q' key to quit |
| H8 — Aesthetic and minimalist | 2 | Window sizes ≤1200px, titles ≤4 words |
| H9 — Error recovery | 5 | Plain language (no tracebacks), actionable warnings, camera fix suggestion, field-specific errors |
| H10 — Help and documentation | 3 | Password rules inline, subtitle hint, daily total prominent |
| Cross-tracker consistency | 5 | Registration check, add/delete, confirmation, number validation |
| Exercise feedback language | 5 | Positive wording, body-part specificity, readable length, angle display |
| Accessibility basics | 5 | Resizable windows, minimum sizes, font ≥10pt, focus on open, contrast |
| AI Coach report readability | 6 | Non-empty, section headers, recommendations, Turkish, dated, under 800 words |

---

## Appendix D — UML Diagrams

### D.1 Use Case Diagram

The use case diagram models 20 use cases across three actors: **User**, **Webcam** (real-time pose input), **Ollama** (local LLM for AI Coach chat), and **USDA / Open Food Facts** (external food API).

![Use Case Diagram](use_case_diagram.puml)

**Package: AI Fitness Trainer**
- Account management: Register, Login, Manage Profile (age/height/weight/BMI/gender/target)
- Exercise tracking (7): Push-up, Squat, Plank, Sit-up, March in Place, Arm Raise, Jump
- Health logging (4): Food & Calories, Sleep, Water, Steps
- AI Coach (2): View Report, Chat
- Analytics (2): Daily Summary, Monthly Statistics
- Integration (1): Launch Desktop App from Web Browser

### D.2 Class Diagram

The class diagram shows six main packages:

1. **Pose Detection** — `poseDetector` (findPose, findPosition, finfAngle)
2. **Exercise App** — `ExerciseTracker` (angle smoothing, stability), `ExerciseFunctions` (7 exercise logics), `CameraApp` (Tkinter GUI + camera loop)
3. **Trackers** — `UserManager`, `SporCalorie` (MET + BMR), `CalorieTracker` (food lookup), `SleepTracker`, `WaterTracker`, `StepTracker`
4. **AI Coach** — `DataCollector` (reads all user DBs), `ReportGenerator` (rule-based), `OllamaClient` (llama3.2)
5. **Web API** — `FastAPI` (REST endpoints), `WebFrontend` (SPA)
6. **Databases** (7) — user_db, spor_db, calorie_db, sleep_db, water_db, step_db, coach_db

### D.3 Sequence Diagram

The sequence diagram captures four interaction flows:

1. **Login & Launch**: User → Browser → FastAPI → authentication → desktop subprocess launch
2. **Exercise Session**: CameraApp ↔ poseDetector (per-frame loop) → rep counting + overlay
3. **Save & Calculate**: Exercise log → spor_db → weight lookup → MET/BMR calorie calculation → calorie_db
4. **AI Coach (optional)**: Data collection from all DBs → rule-based report → Ollama chat (LLM)

---

## Appendix E — Configuration and Requirements

### E.1 Runtime Requirements

| Component | Dependencies |
|---|---|
| Desktop app | `opencv-python`, `numpy`, `mediapipe==0.10.14`, `protobuf==4.25.3` |
| Web backend | `fastapi`, `uvicorn` (see `webapp/backend/requirements.txt`) |
| AI Coach (optional) | Ollama server running `llama3.2` model locally |

### E.2 Database Configuration

All databases are stored at `C:\project_database\`. The following files are created automatically on first use:

| File | Purpose |
|---|---|
| `user_db.db` | User accounts and profiles |
| `spor_db.db` | Exercise logs (reps/seconds per day) |
| `calorie_db.db` | Food intake and exercise calorie calculations |
| `sleep_db.db` | Sleep hour records |
| `water_db.db` | Water intake records |
| `step_db.db` | Step count records |
| `coach_db.db` | AI Coach chat history |

### E.3 Environment Variables

| Variable | Default | Used By |
|---|---|---|
| `USER_DB_PATH` | `C:\project_database\user_db.db` | Web backend |
| `USDA_API_KEY` | (none) | Calorie tracker: USDA FoodData Central API |

### E.4 MediaPipe Model

The pose landmarker model is auto-downloaded on first run:

- **URL**: `https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task`
- **Local path**: `.mediapipe_models/pose_landmarker_lite.task`
- **Model**: PoseLandmarker Lite (float16), ~5 MB

---

## Appendix F — User Interface Screenshots

> **Note**: Screenshots should be captured from a live session and inserted here. The following windows are available:

1. **Main Menu** — AI Fitness Trainer window with exercise dropdown, Start Exercise button, username field, and daily log display
2. **Exercise Session** — Camera view with skeleton overlay, angle labels, progress bar, and real-time form-correction feedback
3. **Water Tracker** — Add/delete water records, daily total display
4. **Sleep Tracker** — Log sleep hours per day
5. **Step Tracker** — Record daily steps with calorie estimate
6. **Calorie Tracker** — Search food by name (USDA/Open Food Facts API), log weight and calories
7. **Registration / Login** — Sign Up window with password rules, Login screen
8. **Profile Editor** — Age, height, weight, gender, target weight, BMI calculator
9. **AI Coach Report** — Scrolled text window with personalized fitness, nutrition, hydration, and sleep recommendations
10. **AI Coach Chat** — Conversational interface powered by local Ollama LLM

---

## Appendix G — MediaPipe Pose Landmarks Reference

The application uses the **MediaPipe Pose Landmarker** model detecting 33 landmarks. Below is the standard landmark topology, with the connections used for exercise tracking.

### Landmark Indices

```
 0 — nose                   11 — left shoulder       23 — left hip
 1 — left eye (inner)       12 — right shoulder      24 — right hip
 2 — left eye               13 — left elbow          25 — left knee
 3 — left eye (outer)       14 — right elbow         26 — right knee
 4 — right eye (inner)      15 — left wrist          27 — left ankle
 5 — right eye              16 — right wrist         28 — right ankle
 6 — right eye (outer)      17 — left pinky          29 — left heel
 7 — left ear               18 — right pinky         30 — right heel
 8 — right ear              19 — left index          31 — left foot index
 9 — mouth (left)           20 — right index         32 — right foot index
10 — mouth (right)          21 — left thumb
                            22 — right thumb
```

### Skeleton Connections Used

The `POSE_CONNECTIONS` set defines the drawn skeleton:

- **Face**: 0–1–2–3–7, 0–4–5–6–8, 9–10
- **Shoulders**: 11–12
- **Left arm**: 11–13–15
- **Right arm**: 12–14–16
- **Torso**: 11–23, 12–24, 23–24
- **Left leg**: 23–25–27, 27–29–31
- **Right leg**: 24–26–28, 28–30–32

### Key Angles per Exercise

| Exercise | Angle 1 (landmarks) | Angle 2 (landmarks) |
|---|---|---|
| Push-up | Elbow (12–14–16, 11–13–15) | Body alignment (11–23–25, 12–24–26) |
| Squat | Knee (24–26–28) | Torso lean (12–24–26) |
| Plank | Body (11–23–27, 12–24–28) | Knee straightness (23–25–27, 24–26–28) |
| Sit-up | Hip (12–24–26, 11–23–25) | — |
| March | Knee per leg (23–25–27, 24–26–28) | — |
| Arm Raise | Wrist Y vs shoulder Y (15 vs 11, 16 vs 12) | — |
| Jump | Hip center Y oscillation (23, 24) | — |

---

**End of Appendix**
