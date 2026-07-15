# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Three independent sub-projects, each with its own toolchain. They communicate over HTTP, not via shared code.

- `Backend/` — Python. Two distinct processes:
  - `main.py`: OpenCV capture loop that connects to a Hikvision RTSP camera (`rtsp://admin:<pass>@169.254.5.71:554/Streaming/Channels/101`), runs YOLOv5 inference every 5 seconds, and POSTs detected-garbage images to the Flask API at `http://127.0.0.1:5000/add/<addr>/<mac>`. The RTSP credentials (`RTSP_USER`, `RTSP_PASS`, `RTSP_IP`) are hardcoded near the top of the file — update them for each deployment. The working directory is set to the script's own directory via `os.chdir(os.path.dirname(os.path.abspath(__file__)))`.
  - `api.py`: Flask + flask-cors REST server (port 5000) backed by SQLite. See "Key API surface" below.
  - `host/` is a stale duplicate of the top-level Backend (older copy with its own DB + `fake_garbage.xlsx`); don't propagate edits there unless asked.
- `Frontend/` — React (CRA, `Frontend/src/`). Routes: `/` (Login), `/Table` (live detections), `/Verified`, `/Delete`, `/History`, `/Logout`. Key deps: antd, axios, react-router-dom v6, react-toastify, react-bootstrap.
- `App/` — Android (Kotlin + Jetpack Compose, Hilt, Retrofit/OkHttp, Room) for the garbage-collector mobile client. Gradle multi-module: root `App/build.gradle` + `App/app/`. The Flask base URL is hardcoded in `App/app/src/main/java/garbagedetection/utils/Constants.kt` (`http://192.168.1.100:5000/`) — update this if the server IP changes.

## Common commands

Backend (from `Backend/`):
```
pip install -r requirements.txt        # repo-root requirements file
python api.py                          # Flask API on :5000
python main.py                         # RTSP capture + YOLO inference loop
```

Frontend (from `Frontend/`):
```
npm install
npm start                              # CRA dev server
npm test                               # Jest via react-scripts
npm test -- -t "<name>"                # single test by name
npm run build                          # production build
```

Android (from `App/`): `./gradlew :app:assembleDebug`, `./gradlew :app:testDebugUnitTest`.

## Key API surface (Flask, `Backend/api.py`)

Routes are area- and MAC-scoped and mostly path-parameterized (no JSON bodies):
- `POST /add/<addr>/<mac>` — multipart `file` upload from `main.py`; inserts a `yolo` row with `is_verified=0`.
- `GET /fetch/<area>`, `GET /fetch_all`, `GET /fetchv/<area>` (verified), `GET /fetch_delete/<area>` (soft-deleted) — listings consumed by the React tables.
- `GET /count/<area>` — aggregate counts used by the dashboard.
- `POST /verify/<id>/<area>`, `POST /temp_delete/<id>`, `DELETE /delete_row/<id>`, `DELETE /delete_all` — state transitions on detections.
- `/add_user/<name>/<email>/<passw>`, `/valid/<name>/<passw>`, `/fetch_login`, `/delete_user/<username>` — auth (plaintext path params; not production-safe).
- `GET /media/<path>` — serves uploaded images out of `UPLOAD_FOLDER` (`Backend/core/media/`).

When adding routes, mirror the existing pattern (path params, `sqlite3` connection opened inside the handler) rather than introducing request bodies or an ORM.

## Things to know before editing

**`is_verified` state machine** — the `yolo` table uses an integer column with three states: `0` = pending (shown in Table), `1` = verified (shown in Verified), `2` = soft-deleted (shown in Delete queue). `verify` toggles between 0↔1; `temp_delete` toggles between 0↔2; `delete_row`/`delete_all` permanently remove rows with `is_verified=2`.

**Two SQLite files** — `config.py` creates `garbage.db.sqlite` (side effect on import), but every route handler in `api.py` opens `car.db.sqlite`. The `yolo` schema is identical in both; `car.db.sqlite` is the live database. Don't rely on `garbage.db.sqlite` for anything — it's a leftover from an earlier version.

**Schema created on import** — both `config.py` and `api.py` run `CREATE TABLE IF NOT EXISTS` at module import time, opening a DB connection as a side effect. Don't import `config` from test code without expecting this.

**YOLO model** — `Backend/model/best1000.pt` is the trained weights file. `torch.hub.load('yolov5', 'custom', path='model/best1000.pt', source='local')` requires a local `yolov5/` checkout in `Backend/`. Inference runs at `model.conf = 0.50`, image size 320.

**`host/` is a stale duplicate** — kept in-tree; don't propagate edits there unless asked.

**`SECRET_KEY`** — read from env (`os.environ.get('SECRET_KEY')`); unset by default.

**SQL injection** — all DB queries in `api.py` use f-string interpolation, not parameterized queries. Be aware of this when adding or modifying routes.
