import cv2
import os
import time
import threading
from datetime import datetime
from PIL import Image
import torch
import json
import numpy as np
import pygame


MOTION_PIXEL_THRESHOLD = 2500  # tuned for a full frame; auto-scaled down for a smaller ROI
DETECT_INTERVAL_SEC = 5
DISPLAY_WIDTH = 960  # on-screen window width; source stays full-res for YOLO/saved images
INFERENCE_SIZE = 640  # YOLO input resolution — higher = sees more detail, slower
REMEMBER_ROI = False  # True = reuse the last drawn ROI on restart; False = draw it every run
ALERT_SOUND = r"C:\Users\chpsh\OneDrive\Desktop\sekai\garbage\GARBAGE-DETECTION\Backend\audio\ElevenLabs_2026-07-01T11_14_56_David - Deep, Warm, Narration_pvc_s50_m2.mp3"

pygame.mixer.init()

base_path = os.path.dirname(os.path.abspath(__file__))
os.chdir(base_path)

DETECTIONS_DIR = os.path.join(base_path, 'detections')
os.makedirs(DETECTIONS_DIR, exist_ok=True)

ROI_FILE = os.path.join(base_path, 'roi.json')  # remembers the drawn ROI between runs


def play_alert():
    def _play():
        try:
            pygame.mixer.music.load(ALERT_SOUND)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
        except Exception as e:
            print(f"Audio error: {e}")
    threading.Thread(target=_play, daemon=True).start()


MODEL_DIR = os.path.join(base_path, 'model')
MODEL_FILE = 'best1000.pt'  # weights to start with; 'm' cycles through every .pt in model/
CONFIDENCE = 0.50

_model_cache = {}


def get_yolov5(filename):
    """Loads (and caches) one of the .pt files in model/. Cached so cycling back
    to a model with 'm' doesn't pay the load cost again."""
    if filename not in _model_cache:
        print(f"Loading model: {filename}")
        model = torch.hub.load('yolov5', 'custom',
                               path=os.path.join(MODEL_DIR, filename), source='local')
        model.conf = CONFIDENCE
        _model_cache[filename] = model
    return _model_cache[filename]


MODEL_FILES = sorted(f for f in os.listdir(MODEL_DIR) if f.lower().endswith('.pt'))
if not MODEL_FILES:
    raise SystemExit(f"No .pt weights found in {MODEL_DIR}")
model_index = MODEL_FILES.index(MODEL_FILE) if MODEL_FILE in MODEL_FILES else 0
model1 = get_yolov5(MODEL_FILES[model_index])

# Force RTSP over TCP — UDP (the default) drops packets on this camera and
# causes HEVC decode errors. Must be set before cv2.VideoCapture is created.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# Camera settings come from the environment, falling back to Backend/.env
# (gitignored — copy .env.example). Real environment variables win over .env.
_env_file = os.path.join(base_path, '.env')
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

RTSP_USER = os.environ.get("RTSP_USER", "admin")
RTSP_PASS = os.environ.get("RTSP_PASS", "")
RTSP_IP   = os.environ.get("RTSP_IP", "169.254.5.71")
# Channel 101 is the full-res main stream. The background reader thread below
# keeps FPS smooth by always dropping stale frames instead of buffering them.
RTSP_URL  = f"rtsp://{RTSP_USER}:{RTSP_PASS}@{RTSP_IP}:554/Streaming/Channels/101"

# Set to True to use the local webcam instead of the Hikvision RTSP camera.
USE_WEBCAM = False
WEBCAM_INDEX = 0

# Set to True to feed still images instead of any live camera (takes precedence
# over USE_WEBCAM). IMAGE_SOURCE may be a single image file or a folder.
USE_IMAGES = False
if not (USE_IMAGES or USE_WEBCAM) and not RTSP_PASS:
    print("WARNING: RTSP_PASS is not set — create Backend/.env from .env.example")
IMAGE_SOURCE = os.path.join(base_path, 'test_images')
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')


def open_stream():
    if USE_WEBCAM:
        return cv2.VideoCapture(WEBCAM_INDEX)
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


class FreshestFrame(threading.Thread):
    """Reads the RTSP stream in a background thread and always keeps only the
    latest decoded frame. The main loop never blocks on decode, and stale
    buffered frames are discarded instead of piling up as latency."""

    def __init__(self):
        super().__init__(daemon=True)
        self.cap = open_stream()
        self.lock = threading.Lock()
        self.frame = None
        self.running = True
        self.start()

    def run(self):
        while self.running:
            ok, img = self.cap.read()
            if not ok:
                print('Frame read failed — reconnecting...')
                self.cap.release()
                time.sleep(2)
                self.cap = open_stream()
                continue
            with self.lock:
                self.frame = img

    def read(self):
        with self.lock:
            if self.frame is None:
                return False, None
            return True, self.frame.copy()

    def release(self):
        self.running = False
        time.sleep(0.2)
        self.cap.release()


class ImageSource:
    """Stand-in for FreshestFrame that serves still images instead of a stream.
    Same read()/release() interface, plus next()/prev() to step through a folder.
    `new_image` is True until the main loop has run detection on the current one."""

    def __init__(self, path):
        if os.path.isdir(path):
            self.paths = sorted(os.path.join(path, f) for f in os.listdir(path)
                                if f.lower().endswith(IMAGE_EXTS))
        elif os.path.isfile(path):
            self.paths = [path]
        else:
            self.paths = []
        if not self.paths:
            raise SystemExit(f"No images found at {path} (expected {', '.join(IMAGE_EXTS)})")
        self.index = 0
        self.frame = None
        self.new_image = False
        self._load()

    def _load(self, direction=1):
        # Skip past anything OpenCV can't decode rather than stalling on it.
        for _ in range(len(self.paths)):
            img = cv2.imread(self.paths[self.index])
            if img is not None:
                self.frame = img
                self.new_image = True
                print(f"[{self.index + 1}/{len(self.paths)}] {self.name()}")
                return
            print(f"Could not read {self.paths[self.index]} — skipping.")
            self.index = (self.index + direction) % len(self.paths)
        raise SystemExit(f"None of the {len(self.paths)} images could be decoded.")

    def step(self, delta):
        self.index = (self.index + delta) % len(self.paths)
        self._load(1 if delta >= 0 else -1)

    def name(self):
        return os.path.basename(self.paths[self.index])

    def read(self):
        if self.frame is None:
            return False, None
        return True, self.frame.copy()

    def release(self):
        pass


def load_roi():
    """Returns a saved (x, y, w, h) in full-res coords, or None."""
    try:
        with open(ROI_FILE) as f:
            r = json.load(f)
        return int(r['x']), int(r['y']), int(r['w']), int(r['h'])
    except Exception:
        return None


def save_roi(roi):
    x, y, w, h = roi
    with open(ROI_FILE, 'w') as f:
        json.dump({'x': x, 'y': y, 'w': w, 'h': h}, f)


def select_roi(frame):
    """Let the user drag a rectangle on a downscaled preview, then map it back
    to full-res coords. ENTER/SPACE confirms, 'c' or ESC = whole frame."""
    h, w = frame.shape[:2]
    scale = DISPLAY_WIDTH / w
    preview = cv2.resize(frame, (DISPLAY_WIDTH, int(h * scale)))
    print("Drag a box over the area to monitor, then press ENTER. Press 'c' to use the whole frame.")
    x, y, rw, rh = cv2.selectROI('Select ROI (ENTER = confirm, c = whole frame)', preview,
                                 showCrosshair=True, fromCenter=False)
    cv2.destroyWindow('Select ROI (ENTER = confirm, c = whole frame)')
    if rw == 0 or rh == 0:
        return None
    return int(x / scale), int(y / scale), int(rw / scale), int(rh / scale)


def clamp_roi(roi, frame):
    """Keeps a saved ROI inside the frame in case the resolution changed."""
    if roi is None:
        return None
    h, w = frame.shape[:2]
    x, y, rw, rh = roi
    x, y = max(0, min(x, w - 1)), max(0, min(y, h - 1))
    rw, rh = max(1, min(rw, w - x)), max(1, min(rh, h - y))
    return x, y, rw, rh


def crop(img, roi):
    if roi is None:
        return img
    x, y, w, h = roi
    return img[y:y + h, x:x + w]


def motion_threshold(roi, frame):
    """Scales the pixel threshold to the ROI's share of the frame, so a small
    ROI doesn't need an implausible number of moving pixels to trigger."""
    if roi is None:
        return MOTION_PIXEL_THRESHOLD
    h, w = frame.shape[:2]
    ratio = (roi[2] * roi[3]) / float(w * h)
    return max(300, int(MOTION_PIXEL_THRESHOLD * ratio))


video = ImageSource(IMAGE_SOURCE) if USE_IMAGES else FreshestFrame()

# Wait for the first frame so the ROI can be drawn on a real image.
print('Waiting for first frame...')
while True:
    ret, first = video.read()
    if ret:
        break
    time.sleep(0.05)

roi = clamp_roi(load_roi(), first) if REMEMBER_ROI else None
if roi is None:
    roi = select_roi(first)
    if roi is not None:
        save_roi(roi)
    elif os.path.exists(ROI_FILE):
        os.remove(ROI_FILE)  # 'c' at startup means: whole frame, forget the old box
else:
    print(f"Loaded saved ROI {roi} from {ROI_FILE} — press 'r' to redraw it.")

bg_sub = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=25, detectShadows=True)
kernel = np.ones((3, 3), np.uint8)

last_detection = time.time()
last_boxes = []  # most recent detection's boxes, drawn on the live window until next cycle

print(f"Saving detections to: {DETECTIONS_DIR}")
print(f"Models available ('m' to cycle): {', '.join(MODEL_FILES)}")
if USE_IMAGES:
    print("Image mode. Press 'n'/SPACE for the next image, 'p' for the previous, "
          "'d' to re-run detection, 'r' to redraw the ROI, 'm' to switch model, 'q' to quit.")
else:
    print("Running. Press 'q' to quit, 'r' to redraw the ROI, 'm' to switch model.")

while True:
    ret, img = video.read()
    if not ret:
        # Reader thread is still connecting / reconnecting — wait for a frame.
        time.sleep(0.05)
        continue

    if USE_IMAGES:
        # Still images have no motion — detect once per newly loaded image.
        motion_pixels = 0
        motion_present = False
        run_detect = video.new_image
    else:
        # Motion detection — only inside the ROI, so movement elsewhere is ignored
        # and the subtractor works over far fewer pixels.
        fg = bg_sub.apply(crop(img, roi))
        _, th = cv2.threshold(fg, 200, 255, cv2.THRESH_BINARY)
        th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel)
        th = cv2.dilate(th, kernel, iterations=2)
        motion_pixels = cv2.countNonZero(th)
        motion_present = motion_pixels > motion_threshold(roi, img)
        run_detect = motion_present and (time.time() - last_detection >= DETECT_INTERVAL_SEC)

    # Snapshot clean pixels before the HUD is drawn over them, so inference and
    # the saved image never see the overlay text.
    det_input = crop(img, roi).copy() if run_detect else None
    clean = img.copy() if run_detect else None

    # HUD
    font = cv2.FONT_HERSHEY_PLAIN
    cv2.putText(img, str(datetime.now()), (20, 40), font, 2, (255, 255, 255), 2, cv2.LINE_AA)
    if USE_IMAGES:
        status = f"[{video.index + 1}/{len(video.paths)}] {video.name()}"
        colour = (0, 255, 255)
    else:
        status = f"Motion: {'YES' if motion_present else 'NO'} ({motion_pixels}px)"
        colour = (0, 255, 0) if motion_present else (100, 100, 100)
    cv2.putText(img, status, (20, 70), font, 1.5, colour, 2, cv2.LINE_AA)
    cv2.putText(img, f"model: {MODEL_FILES[model_index]}", (20, 100), font, 1.5,
                (255, 200, 0), 2, cv2.LINE_AA)

    if roi is not None:
        rx, ry, rw, rh = roi
        cv2.rectangle(img, (rx, ry), (rx + rw, ry + rh), (0, 255, 255), 2)
        cv2.putText(img, 'ROI', (rx + 5, ry + 25), font, 1.5, (0, 255, 255), 2, cv2.LINE_AA)

    # Draw bounding boxes from the most recent detection on the live window
    for box in last_boxes:
        x1, y1 = int(box['xmin']), int(box['ymin'])
        x2, y2 = int(box['xmax']), int(box['ymax'])
        label = f"{box['name']} {box['confidence']:.2f}"
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(img, label, (x1, max(y1 - 8, 15)), font, 1.3, (0, 0, 255), 2, cv2.LINE_AA)

    # Resize only the displayed frame (source img stays full-res for YOLO/saving)
    h, w = img.shape[:2]
    disp = cv2.resize(img, (DISPLAY_WIDTH, int(h * DISPLAY_WIDTH / w)))
    cv2.imshow('live video', disp)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    if key == ord('m') and len(MODEL_FILES) > 1:
        model_index = (model_index + 1) % len(MODEL_FILES)
        model1 = get_yolov5(MODEL_FILES[model_index])
        last_boxes = []
        if USE_IMAGES:
            video.new_image = True  # re-run the current image through the new model
        continue
    if USE_IMAGES and key in (ord('n'), ord(' '), ord('p'), ord('d')):
        if key == ord('d'):
            video.new_image = True  # re-run detection on the current image
        else:
            video.step(-1 if key == ord('p') else 1)
            last_boxes = []
        continue
    if key == ord('r'):
        ok, fresh = video.read()
        if not ok:
            continue
        roi = select_roi(fresh)
        if roi is not None:
            save_roi(roi)
        elif os.path.exists(ROI_FILE):
            os.remove(ROI_FILE)  # 'c' during redraw means: go back to whole frame
        # The subtractor's background model is tied to the old crop size.
        bg_sub = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=25, detectShadows=True)
        last_boxes = []
        if USE_IMAGES:
            video.new_image = True  # re-detect the current image inside the new ROI
        continue

    # Run YOLO only when motion is detected and interval has passed
    if run_detect:
        if USE_IMAGES:
            video.new_image = False  # one pass per image until 'n'/'p'/'d'
        img_pil = Image.fromarray(cv2.cvtColor(det_input, cv2.COLOR_BGR2RGB))
        results = model1(img_pil, size=INFERENCE_SIZE)
        data = json.loads(results.pandas().xyxy[0].to_json(orient="records"))

        # Boxes come back in ROI-crop coords — shift them into full-frame coords.
        ox, oy = (roi[0], roi[1]) if roi is not None else (0, 0)
        for box in data:
            box['xmin'] += ox
            box['xmax'] += ox
            box['ymin'] += oy
            box['ymax'] += oy
        last_boxes = data  # refresh live-window overlay (empty list clears old boxes)

        if len(data) != 0:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(DETECTIONS_DIR, f"garbage_{timestamp}.jpg")
            # Save the full frame (context around the ROI) with boxes drawn on it.
            for box in data:
                x1, y1 = int(box['xmin']), int(box['ymin'])
                x2, y2 = int(box['xmax']), int(box['ymax'])
                cv2.rectangle(clean, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(clean, f"{box['name']} {box['confidence']:.2f}",
                            (x1, max(y1 - 8, 15)), font, 1.3, (0, 0, 255), 2, cv2.LINE_AA)
            cv2.imwrite(save_path, clean)
            print(f"Garbage detected — saved: {save_path}")
            play_alert()
        else:
            print('Motion detected, no garbage')

        last_detection = time.time()

video.release()
cv2.destroyAllWindows()
