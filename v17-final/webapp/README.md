# Web Migration Starter

This folder contains the first web version of your project.

## Current scope

- FastAPI backend
- Web page served from backend
- User register/login APIs
- Reuses existing SQLite `users` table shape

## Run

1. Open terminal in `webapp/backend`
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start server:

```bash
uvicorn main:app --reload
```

4. Open:

`http://127.0.0.1:8000`

## Environment variables

- `USER_DB_PATH` (optional): path to user SQLite db.
  - Default: `C:\project_database\user_db.db`

## Next steps

- Add profile CRUD APIs
- Add sleep/water/calorie endpoints
- Add camera pose detection in browser with MediaPipe JS
- Replace plain SHA-256 with bcrypt/argon2
