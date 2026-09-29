# Field deployment — CPU-only laptop

Checklist for moving GARBAGE-DETECTION to a second machine with **no NVIDIA
GPU**. `clone.txt` covers generic first-time setup; this file covers what is
different about a field box, and specifically **what a `git clone` will not
give you**.

---

## 0. The short version

CUDA is **not** required. It changes inference *speed* only, never accuracy.
The weights (`Backend/model/best1000.pt`, 3.9 MB — YOLOv5n) are small, and
`main.py` only runs inference when motion is seen inside the ROI *and* at most
once every `DETECT_INTERVAL_SEC = 5` seconds (`Backend/main.py:14`, `:298`).
That is a single-digit CPU duty cycle. The real continuous cost on the field
laptop is HEVC decoding of the RTSP stream, which is identical with or
without a GPU.

No code change is needed to run on CPU — see section 4.

---

## 1. Files you must carry over by hand

**Do not assume `git clone` is enough.** Two separate problems:

### 1a. Ignored by `.gitignore` — will never be in the repo

| Path | Size | Carry over? | Why |
|---|---|---|---|
| `Backend/yolov5/` | 21 MB | **Re-clone, don't copy** | Third-party checkout. `main.py` loads with `source='local'`, so without it `torch.hub.load` fails instantly. |
| `Backend/core/media/` | 652 KB | **Create empty** | `Config.UPLOAD_FOLDER`. Nothing creates it. If missing, every `POST /add` throws on `file.save()` and detections are silently lost. |
| `Backend/car.db.sqlite` | — | **Start fresh** | Live database. Schema is auto-created on import. Copy only if you want existing detections on the field box. |
| `Backend/garbage.db.sqlite` | — | No | Leftover from an earlier version; nothing reads it. |

### 1b. NOT ignored, but never committed — `git status` shows them as `??`

These are the ones that will actually surprise you:

| Path | Size | Carry over? | Why |
|---|---|---|---|
| `Web/` | — | **YES — critical** | This is the *current* dashboard, and it has **zero tracked files** (`git ls-files Web` returns nothing). A clone on the field laptop gives you no dashboard at all. Either `git add Web/` and commit before you travel, or copy the folder manually (excluding `node_modules/` and `dist/`). |
| `Backend/.env` | — | **Recreate** | Camera user/password/IP. Copy `Backend/.env.example` and fill it in — see §5. |
| `Backend/roi.json` | 4 B | **NO — see §5** | Saved ROI in *source-pixel* coordinates for the current camera mounting. Wrong at a new site. |
| `Backend/detections/` | 13 MB | No | Local detection output from testing. |
| `Backend/test_images/` | 4.5 MB | Only if using `USE_IMAGES` mode | Still-image test fixtures. |

> `Backend/host/` is a stale duplicate of the backend — do not deploy it.

---

## 2. Setup on the field laptop

```bash
git clone <repo-url> GARBAGE-DETECTION
cd GARBAGE-DETECTION

# YOLOv5 source (gitignored — must be fetched separately)
cd Backend
git clone https://github.com/ultralytics/yolov5.git yolov5
mkdir -p core/media          # gitignored, nothing creates it
cd ..

python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate           # macOS/Linux
```

Then install — **order matters**, see next section.

---

## 3. Installing without CUDA

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

**Install torch first, in its own command.** `requirements.txt` needs
`ultralytics` (YOLOv5's `hubconf.py` and `models/common.py` import it
directly), and `ultralytics` declares `torch` as a dependency. If torch is not
already installed, pip resolves it from PyPI and downloads the **CUDA build —
roughly 2.5 GB of GPU libraries that will never load** on a machine with no
NVIDIA card. Installing the CPU wheel first makes that requirement
already-satisfied and nothing CUDA is fetched.

Verify you got the CPU build:

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Expect something like `2.6.0+cpu False`. A `+cu124` suffix means the CUDA
wheel slipped in — `pip uninstall torch torchvision` and redo the first
command.

> `requirements.txt` now includes `ultralytics`, `GitPython`, `thop`,
> `matplotlib`, `seaborn`, `scipy` and `psutil`. These are not optional
> extras: they are imported by the YOLOv5 load path at startup. The previous
> version of the file omitted them, which meant a fresh install crashed on
> `torch.hub.load` before reading a single frame.

---

## 4. Switching the model to CPU

**No code change is required.** YOLOv5's loader calls `select_device()`, which
falls back to CPU automatically when `torch.cuda.is_available()` is `False`.
On a machine with no NVIDIA driver that is always the case, so
`get_yolov5()` (`Backend/main.py:50`) yields a CPU model as-is.

Optional — if you want it explicit and reproducible rather than
environment-dependent, force it in `get_yolov5()`:

```python
model = torch.hub.load('yolov5', 'custom',
                       path=os.path.join(MODEL_DIR, filename),
                       source='local', device='cpu')
```

Optional — cap thread count if the preview stutters because inference is
saturating every core. Add once, near the top of `main.py`:

```python
torch.set_num_threads(4)   # leave headroom for RTSP decode + UI
```

If the preview is still choppy on a weak CPU, lower `INFERENCE_SIZE` from 640
to 416 (`Backend/main.py:16`). **This one does cost accuracy** on small or
distant piles — change it only if you actually observe a problem, not
preemptively.

---

## 5. Camera and ROI at the new site

These are the two things most likely to kill the field test — far more likely
than anything CPU-related.

**RTSP address.** Camera settings are read from environment variables, falling
back to `Backend/.env` (gitignored, so a clone won't have it). Create it from
the template:

```bash
cp Backend/.env.example Backend/.env     # then set RTSP_PASS and RTSP_IP
```

```
RTSP_USER=admin
RTSP_PASS=...
RTSP_IP=169.254.5.71
```

`169.254.x.x` is a **link-local (APIPA) address**. It only works when the
camera is cable-direct to the laptop with no DHCP server, exactly as on the
current machine. On a field network the camera will almost certainly get a
different IP. Find it and update `RTSP_IP` in `Backend/.env`. Check
reachability first:

```bash
ping <camera-ip>
Test-NetConnection <camera-ip> -Port 554     # PowerShell
```

Also confirm `USE_IMAGES = False` in `Backend/main.py` — it is the still-image
test mode, not the camera.

**ROI.** Do **not** copy `Backend/roi.json`. It stores
`{"x": 784, "y": 560, "w": 869, "h": 834}` in source-pixel coordinates for
the current camera mounting, and motion detection only runs inside it. At a new
site with a new camera angle it will mask the wrong region and you will see no
detections at all. Delete it and redraw on-site — press `r` while the app is
running.

---

## 6. Running

Two processes, two terminals, from `Backend/`:

```bash
python api.py      # Flask API on :5000 — start this first
python main.py     # RTSP capture + inference loop
```

Dashboard, from `Web/`:

```bash
npm install
npm run dev        # http://localhost:5173
```

`Web/vite.config.js` proxies `/api/...` to Flask on `127.0.0.1:5000`. If the
API runs on another machine:

```bash
VITE_API_TARGET=http://<ip>:5000 npm run dev
```

---

## 7. Pre-flight check

- [ ] `Backend/yolov5/` exists
- [ ] `Backend/model/best1000.pt` exists (3.9 MB)
- [ ] `Backend/core/media/` exists
- [ ] `Web/` present on the field laptop (**not in git — verify explicitly**)
- [ ] `torch.cuda.is_available()` prints `False` and version ends in `+cpu`
- [ ] `python -c "import pygame, cv2, flask, ultralytics"` succeeds
- [ ] `RTSP_IP` updated for the site network; port 554 reachable
- [ ] `USE_IMAGES = False`
- [ ] `Backend/roi.json` deleted, ROI redrawn on-site with `r`
- [ ] `api.py` up before `main.py`
