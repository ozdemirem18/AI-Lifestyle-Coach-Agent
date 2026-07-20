[README.md](https://github.com/user-attachments/files/30192215/README.md)

# 🏋️ AI Fitness Trainer

<div align="center">

**Real-time AI-powered fitness companion with pose correction, health tracking, and personalized coaching — all in one system.**

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.1.0-009688.svg)](https://fastapi.tiangolo.com/)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10.14-orange.svg)](https://ai.google.dev/edge/mediapipe)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

---

## 📖 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Supported Exercises](#-supported-exercises)
- [Tech Stack](#-tech-stack)
- [System Architecture](#-system-architecture)
- [Screenshots](#-screenshots)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Usage](#-usage)
- [API Reference](#-api-reference)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [Testing](#-testing)
- [Research](#-research)
- [License](#-license)
- [Acknowledgements](#-acknowledgements)

---

## 🔍 Overview

**AI Fitness Trainer** is an all-in-one fitness companion that uses computer vision to track your exercise form in real-time via webcam, monitors five health domains daily, and provides personalized AI coaching.

**The Problem:** People struggle to maintain proper exercise form, track health metrics (sleep, water, steps, calories), and get personalized guidance — especially when juggling disconnected tools.

**Our Solution:** A single integrated system that:
- Uses **MediaPipe + OpenCV** for real-time body landmark tracking (33 landmarks) via webcam
- Runs **7 exercise-specific state-machine engines** that count reps using joint-angle thresholds with temporal smoothing
- Persists user data across **6 SQLite databases**
- Estimates calorie burn via **MET-based formulas** and **Mifflin-St Jeor BMR equation**
- Delivers **rule-based coaching reports** and optional **conversational AI chat** via Ollama (local LLM)
- Provides both a **Tkinter desktop GUI** and a **FastAPI-powered web dashboard**

---

## ✨ Features

### 🎥 Real-Time Exercise Tracking
- Webcam-based pose detection with **33 body landmarks**
- Real-time rep counting across **7 exercises**
- **Form quality feedback** — detects common errors (piked hips, forward lean, core collapse)
- Visual feedback overlay: **progress bars**, **joint angle displays**, **corrective text cues**
- Exercise session summary with calorie burn estimates

### 📊 Comprehensive Health Monitoring
Track all five health domains from a single dashboard:

| Domain | What It Tracks |
|--------|---------------|
| 🏃 **Exercise** | Reps, duration, form quality, exercise calories |
| 💤 **Sleep** | Daily sleep hours, weekly trends |
| 💧 **Water** | Daily water intake in ml |
| 🍎 **Calories** | Food intake with USDA + Open Food Facts API lookup |
| 👣 **Steps** | Daily step count with calorie conversion |

### 🧠 AI Coach
- **Rule-based report** — analyzes data across all 6 databases, provides personalized recommendations for exercise, nutrition, hydration, and sleep
- **Conversational chat** — chat with an AI coach powered by **Ollama** (local LLM — `llama3.2`), with live access to your health data
- **Chat history** — conversations are saved and can be resumed later
- Falls back to rule-based coach when Ollama is unavailable

### 🌐 Multi-Platform
- **Desktop GUI** (Tkinter) — for camera-based exercise tracking
- **Web Dashboard** (FastAPI + SPA) — responsive Apple-inspired design with Chart.js analytics
- **20+ REST API endpoints** — full backend for web and mobile integration

### 📈 Analytics
- Weekly and monthly trend views across all metrics
- Exercise volume tracking, calorie balance charts, sleep pattern graphs
- Monthly exercise calendar heatmap

---

## 🏃 Supported Exercises

| Exercise | Tracking Method | Form Checks |
|----------|----------------|-------------|
| **Push-ups** | Elbow angle + body alignment | Piked hips, asymmetric arms, incomplete range |
| **Squats** | Knee angle + torso lean | Forward lean, shallow depth, knee valgus |
| **Plank** | Shoulder-hip-ankle alignment | Core collapse, hip sag, hip pike |
| **Sit-ups** | Torso angle + knee position | Incomplete range, momentum reliance |
| **Arm Raises** | Shoulder abduction angle | Asymmetric movement, incomplete lift |
| **Marching** | Knee lift height + arm swing | Low knees, poor coordination |
| **Jumps** | Hip extension + landing depth | Hard landings, shallow jump height |

---

## 🛠 Tech Stack

### Core
| Technology | Purpose |
|-----------|---------|
| **Python 3.10+** | Main programming language |
| **OpenCV** | Webcam capture, image rendering |
| **MediaPipe 0.10.14** | Pose landmark detection (33 landmarks) |
| **NumPy** | Numerical operations, angle calculations |

### Backend
| Technology | Purpose |
|-----------|---------|
| **FastAPI** | REST API framework |
| **Uvicorn** | ASGI server |
| **Pydantic** | Request/response validation |
| **SQLite** | 6 databases for data persistence |
| **Requests** | External API calls (USDA, Ollama) |

### Frontend
| Technology | Purpose |
|-----------|---------|
| **Tkinter** | Desktop GUI (exercise + tracker windows) |
| **HTML5 / CSS3 / JavaScript** | Web dashboard (SPA) |
| **Chart.js** | Interactive analytics charts |

### AI / ML
| Technology | Purpose |
|-----------|---------|
| **MediaPipe Pose Landmarker** | Real-time pose estimation (Lite model, ~5.5 MB) |
| **Ollama** | Local LLM for conversational AI coaching |

---

## 🏗 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     USER INTERFACES                          │
│  ┌──────────────────┐    ┌──────────────────────────────┐   │
│  │  Tkinter Desktop  │    │   Web Dashboard (FastAPI)    │   │
│  │  (camera4.py)     │    │   (index.html + Chart.js)    │   │
│  └───────┬──────────┘    └──────────────┬───────────────┘   │
└──────────┼──────────────────────────────┼───────────────────┘
           │                              │
┌──────────┼──────────────────────────────┼───────────────────┐
│          │       CORE ENGINE            │                    │
│  ┌───────┴──────────┐    ┌─────────────┴────────────────┐   │
│  │  Pose Detector    │    │     FastAPI REST Server      │   │
│  │  (PoseModule.py)  │    │     (webapp/backend/main.py) │   │
│  └───────┬──────────┘    └─────────────┬────────────────┘   │
│          │                              │                    │
│  ┌───────┴──────────────────────────────┴────────────────┐   │
│  │                 EXERCISE ENGINES                       │   │
│  │  7 state machines (joint-angle thresholds + EMA)      │   │
│  │  Push-up | Squat | Plank | Sit-up | March |           │   │
│  │  Arm Raise | Jump                                      │   │
│  └───────────────────────────┬───────────────────────────┘   │
└──────────────────────────────┼───────────────────────────────┘
                               │
┌──────────────────────────────┼───────────────────────────────┐
│                    DATA & AI LAYER                            │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐   │
│  │  🏃 Spor │  💤 Sleep│  💧 Water│  🍎 Cal  │  👣 Step │   │
│  │    DB    │    DB    │    DB    │    DB    │    DB    │   │
│  └────┬─────┴─────┬────┴────┬─────┴────┬─────┴────┬─────┘   │
│       └───────────┴─────────┴───────────┴───────────┘        │
│                          │                                    │
│  ┌───────────────────────┴───────────────────────────────┐   │
│  │                   AI COACH ENGINE                      │   │
│  │  ┌──────────────────┐  ┌──────────────────────────┐   │   │
│  │  │ Rule-Based Coach │  │  Ollama LLM Chat          │   │   │
│  │  │ (always available)│  │  (optional, local LLM)    │   │   │
│  │  └──────────────────┘  └──────────────────────────┘   │   │
│  └───────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### Data Flow
1. **Webcam** → `PoseModule.py` extracts 33 landmarks via MediaPipe
2. **Landmark data** → `camera4.py` exercise engines analyze joint angles
3. **Reps + form data** → Saved to `spor_db.db`
4. **Health modules** (sleep, water, calories, steps) → Write to respective SQLite DBs
5. **AI Coach** → Reads all 6 databases, generates personalized report
6. **Web backend** → FastAPI serves data to web dashboard and handles chat

---

## 📸 Screenshots

> **Note:** Add your screenshots here! Create a `screenshots/` directory and add images of:
> - The exercise tracking view (`camera4.py` in action)
> - The web dashboard
> - The AI Coach chat interface
> - Each health tracker window (sleep, water, steps, calories)
>
> Then reference them like:
> ```markdown
> ![Exercise Tracking](screenshots/exercise.png)
> ![Web Dashboard](screenshots/dashboard.png)
> ```

---

## 📋 Prerequisites

### Required
- **Python 3.10 or higher** — [Download](https://www.python.org/downloads/)
- **A webcam** — built-in or USB, for exercise tracking
- **Windows / macOS / Linux** — tested primarily on Windows

### Optional (but recommended)
- **Ollama** — for conversational AI Coach (runs entirely locally)
  - [Download Ollama](https://ollama.ai/)
  - After installing, pull the model: `ollama pull llama3.2`
  - Without Ollama, the rule-based AI Coach still works

---

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/ai-fitness-trainer.git
cd ai-fitness-trainer
```

### 2. Create a Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
# Core dependencies (exercise tracking + health modules)
pip install -r requirements.txt

# Web backend dependencies
pip install -r webapp/backend/requirements.txt
```

**What gets installed:**
- `opencv-python` — webcam capture and image processing
- `numpy` — numerical computations
- `mediapipe==0.10.14` — pose landmark detection
- `protobuf==4.25.3` — required MediaPipe dependency
- `fastapi` — REST API framework
- `uvicorn` — ASGI web server
- `requests` — HTTP client (USDA API, Ollama)
- `pydantic` — data validation (included with FastAPI)

> **💡 Note:** The MediaPipe Pose Landmarker model (~5.5 MB) is **auto-downloaded** on first run — no manual download needed.

### 4. Set Up Ollama (Optional — for AI Chat)

```bash
# Install Ollama from https://ollama.ai/
ollama pull llama3.2

# Verify it's running
ollama list
```

Ollama runs on `http://localhost:11434` by default. The app will auto-detect it.

---

## 📘 Usage

### 🖥 Starting the Desktop App (Exercise Tracking)

The main application launches the webcam-based exercise tracker with a Tkinter GUI menu for all health modules:

```bash
python camera4.py
```

**What you'll see:**
1. A **login/register window** (or pass `--username YOUR_USERNAME` to skip)
2. The **main menu** — launch exercise tracking, health modules, or AI Coach
3. When you start an exercise, the **webcam feed** opens with real-time landmark overlay
4. **Live feedback** — rep count, form cues, angle displays

**Command-line options:**
```bash
# With pre-filled username (from web login)
python camera4.py --username john_doe

# The camera resolution auto-adjusts to 1920x1080
# Press 'q' to quit any exercise, 'r' to reset the current exercise
```

### 🧩 Standalone Health Tracker GUIs

Each tracker can run independently with a username:

```bash
python water/water_f.py --username john_doe      # Water intake tracker
python sleep/sleep_f.py --username john_doe      # Sleep hours tracker
python step/step_f.py --username john_doe        # Step counter
python calorie/calorie_f.py --username john_doe  # Food calorie tracker
```

### 🌐 Starting the Web Backend

```bash
cd webapp/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Then open your browser:**
- **Web Dashboard:** [http://localhost:8000](http://localhost:8000)
- **API Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Docs (ReDoc):** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

### 🧠 Using the AI Coach

**From the Web Dashboard:**
1. Log in on the web app
2. Navigate to the **AI Coach** section
3. View your **personalized report** (rule-based analysis)
4. **Chat** with the AI Coach if Ollama is running

**From the Desktop App:**
- Click the **AI Coach** button in the main menu to open the coach window

### 📱 Typical Workflow

1. **Register** an account (web or desktop)
2. **Set up your profile** — age, height, weight, gender, goals
3. **Log health data** — sleep, water, food throughout the day
4. **Exercise** — launch the webcam tracker and do your workout
5. **Review** — check the web dashboard for daily summary and trends
6. **Get coaching** — open the AI Coach for personalized recommendations

---

## 📡 API Reference

The FastAPI backend exposes **20+ endpoints** organized by domain:

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/register` | Register a new user |
| `POST` | `/api/auth/login` | Login with username/password |

### Profile
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/profile/{username}` | Get user profile + BMI |
| `POST` | `/api/profile/update` | Update profile (age, weight, height, goals) |

### Health Tracking
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sleep/add` | Log sleep hours |
| `GET` | `/api/sleep/logs/{username}` | Get today's sleep logs |
| `DELETE` | `/api/sleep/logs/{log_id}` | Delete a sleep record |
| `POST` | `/api/water/add` | Log water intake |
| `GET` | `/api/water/logs/{username}` | Get today's water logs |
| `DELETE` | `/api/water/logs/{log_id}` | Delete a water record |
| `POST` | `/api/calories/add` | Log food calories |
| `GET` | `/api/calories/logs/{username}` | Get today's calorie logs |
| `DELETE` | `/api/calories/logs/{log_id}` | Delete a calorie record |
| `POST` | `/api/steps/add` | Log step count |
| `GET` | `/api/steps/logs/{username}` | Get today's step logs |
| `DELETE` | `/api/steps/logs/{log_id}` | Delete a step record |

### Exercise
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/exercise/add` | Log exercise reps/seconds |
| `GET` | `/api/exercise/logs/{username}` | Get today's exercise logs |
| `DELETE` | `/api/exercise/logs/{log_id}` | Delete an exercise record |
| `GET` | `/api/exercise-stats/{username}` | Get all-time exercise totals |
| `GET` | `/api/exercise-history/{username}?days=7` | Weekly exercise history |
| `GET` | `/api/daily-summary/{username}` | Full daily health summary |

### Launchers (Desktop App Triggers)
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/launch-pose-detection` | Launch camera4.py exercise tracker |
| `POST` | `/api/launch-calorie` | Launch calorie tracker GUI |
| `POST` | `/api/launch-sleep` | Launch sleep tracker GUI |
| `POST` | `/api/launch-water` | Launch water tracker GUI |
| `POST` | `/api/launch-step` | Launch step tracker GUI |

### Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/monthly-stats/{username}?year=&month=` | Monthly exercise + calorie calendar |
| `GET` | `/api/steps/{username}?days=7` | Weekly step history |

### AI Coach
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/ai-coach/{username}` | Get rule-based AI Coach report |
| `POST` | `/api/ai-coach/chat` | Chat with AI Coach (Ollama LLM) |
| `GET` | `/api/ai-coach/chats/{username}` | List saved chat sessions |
| `POST` | `/api/ai-coach/chats` | Create a new chat session |
| `GET` | `/api/ai-coach/chats/{chat_id}/messages` | Get chat messages |
| `POST` | `/api/ai-coach/chats/{chat_id}/messages` | Add message to chat |
| `PUT` | `/api/ai-coach/chats/{chat_id}/title` | Update chat title |
| `DELETE` | `/api/ai-coach/chats/{chat_id}` | Delete a chat session |

> **📚 Full interactive API docs:** Run the server and visit `/docs` for Swagger UI with request/response schemas.

---

## 📁 Project Structure

```
ai-fitness-trainer/
│
├── camera4.py                  # 🎥 Main exercise app (webcam + 7 exercise engines + Tkinter menu)
├── PoseModule.py               # 🦴 MediaPipe pose detector wrapper (auto-downloads model)
│
├── ai_coach/                   # 🧠 AI Coach
│   ├── __init__.py
│   └── ai_coach.py             # Rule-based report generator + Ollama chat integration
│
├── calorie/                    # 🍎 Calorie tracking
│   ├── calorie_f.py            # Food tracker GUI (USDA + Open Food Facts API)
│   └── spor_calorie_f.py       # Exercise calorie estimation (MET + BMR)
│
├── water/                      # 💧 Water tracking
│   └── water_f.py              # Water intake Tkinter GUI
│
├── sleep/                      # 💤 Sleep tracking
│   └── sleep_f.py              # Sleep hours Tkinter GUI
│
├── step/                       # 👣 Step tracking
│   ├── __init__.py
│   └── step_f.py               # Step count Tkinter GUI
│
├── user/                       # 👤 User management
│   └── user_f.py               # Registration, login, profile Tkinter GUI
│
├── webapp/                     # 🌐 Web application
│   ├── README.md               # Web-specific migration guide
│   ├── backend/
│   │   ├── main.py             # FastAPI server (20+ endpoints)
│   │   └── requirements.txt    # Web backend dependencies
│   └── frontend/
│       └── websitedesign/
│           └── index.html      # SPA web dashboard (Apple-inspired design)
│
├── tests/                      # 🧪 Test suite
│   ├── test_exercise.py        # Exercise engine unit tests
│   ├── test_ai_coach.py        # AI Coach unit tests
│   ├── test_calorie.py         # Calorie module tests
│   ├── test_sleep.py           # Sleep module tests
│   ├── test_water.py           # Water module tests
│   ├── test_step.py            # Step module tests
│   ├── test_user.py            # User module tests
│   ├── test_spor_calorie.py    # Exercise calorie tests
│   ├── test_hci.py             # HCI usability heuristic tests
│   └── integration_test_register.py  # Registration integration tests
│
├── appendix_report.md          # 📄 Database schemas, test results, UML docs
├── class_diagram.puml          # 📊 PlantUML class diagram
├── sequence_diagram.puml       # 📊 PlantUML sequence diagram
├── use_case_diagram.puml       # 📊 PlantUML use case diagram
├── REFERENCES.md               # 📚 Academic/scientific references
│
├── requirements.txt            # Core Python dependencies
├── .gitignore
├── LICENSE                     # MIT License
└── README.md                   # You are here 📍
```

---

## ⚙️ Configuration

### Database Paths

Databases are created automatically at `C:\project_database\` on Windows. You can override paths via environment variables:

| Variable | Default | Database |
|----------|---------|----------|
| `USER_DB_PATH` | `C:\project_database\user_db.db` | User profiles |
| `SLEEP_DB_PATH` | `C:\project_database\sleep_db.db` | Sleep records |
| `WATER_DB_PATH` | `C:\project_database\water_db.db` | Water intake |
| `CALORIE_DB_PATH` | `C:\project_database\calorie_db.db` | Food calories |
| `SPOR_DB_PATH` | `C:\project_database\spor_db.db` | Exercise logs |
| `STEP_DB_PATH` | `C:\project_database\step_db.db` | Step counts |
| `COACH_DB_PATH` | `C:\project_database\coach_db.db` | AI Coach chats |

### API Keys

| Variable | Purpose | Required? |
|----------|---------|-----------|
| `USDA_API_KEY` | USDA FoodData Central API (calorie lookup) | Optional — falls back to Open Food Facts |

### Ollama Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2` | Model to use for AI chat |

> These are defined at the top of `webapp/backend/main.py`. Change them directly in the source, or set up environment variable support.

---

## 🧪 Testing

The project includes a comprehensive test suite covering all modules:

```bash
# Run all tests
python -m pytest tests/

# Run a specific test file
python -m pytest tests/test_exercise.py

# Run with verbose output
python -m pytest tests/ -v

# Run a specific test class
python -m pytest tests/test_exercise.py::TestPushUpCounter
```

### Test Coverage

| Test File | What It Tests |
|-----------|--------------|
| `test_exercise.py` | Exercise state machines, rep counting, form detection |
| `test_ai_coach.py` | AI Coach report generation, data collection |
| `test_calorie.py` | Calorie tracker logic, food API integration |
| `test_sleep.py` | Sleep tracker logic, database operations |
| `test_water.py` | Water tracker logic, database operations |
| `test_step.py` | Step tracker logic, database operations |
| `test_user.py` | User registration, login, profile management |
| `test_spor_calorie.py` | Exercise MET/BMR calorie calculations |
| `test_hci.py` | Usability heuristics, UI error handling |
| `integration_test_register.py` | End-to-end registration flow |

---

## 🔬 Research

This project was developed as part of a **graduation thesis (bitirme projesi)**. The research investigated:

- **RQ1:** Accuracy of single-webcam MediaPipe form error detection vs. expert observation
- **RQ2:** Reliability of joint-angle state machines for rep counting across body types
- **RQ3:** Adherence impact of consolidated health tracking
- **RQ4:** Effectiveness of combined rule-based + LLM coaching
- **RQ5:** Validity of MET-based calorie estimates

Key hypotheses include ≥90% rep counting accuracy and ≥80% form deviation detection compared to certified trainer review. See `appendix_report.md` for detailed research methodology, database schemas, and results.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgements

- **[MediaPipe](https://ai.google.dev/edge/mediapipe)** — Google's on-device ML framework for pose estimation
- **[OpenCV](https://opencv.org/)** — Open source computer vision library
- **[FastAPI](https://fastapi.tiangolo.com/)** — High-performance Python web framework
- **[Ollama](https://ollama.ai/)** — Local LLM runtime
- **[Chart.js](https://www.chartjs.org/)** — Beautiful charting for the web dashboard
- **[USDA FoodData Central](https://fdc.nal.usda.gov/)** — Food nutrition data API
- **[Open Food Facts](https://world.openfoodfacts.org/)** — Open food database
- **Compendium of Physical Activities** — MET value reference data
- **Mifflin-St Jeor equation** — BMR estimation methodology

---

<div align="center">

**Made with ❤️ for better fitness, everywhere.**

⭐ **Star this repo** if you find it useful!

</div>
