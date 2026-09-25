import os

# Force RTSP over TCP.
# This must be set before cv2.VideoCapture() is created.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

import time
import threading
import winsound
from datetime import datetime

import cv2
import numpy as np
from ultralytics import YOLO


# ============================================================
# HIKVISION CAMERA CONFIGURATION
# ============================================================

RTSP_USER = "admin"
RTSP_PASS = "PUT_CAMERA_PASSWORD_HERE"
RTSP_IP = "169.254.5.71"
RTSP_PORT = 554

# Hikvision channel:
# 101 = Main stream, higher resolution
# 102 = Substream, lower resolution and lower CPU usage
RTSP_CHANNEL = "101"

RTSP_URL = (
    f"rtsp://{RTSP_USER}:{RTSP_PASS}@{RTSP_IP}:{RTSP_PORT}"
    f"/Streaming/Channels/{RTSP_CHANNEL}"
)

RECONNECT_DELAY_SEC = 2
FIRST_FRAME_TIMEOUT_SEC = 15


# ============================================================
# YOLO CONFIGURATION
# ============================================================

MODEL_PATH = "yolov8n.pt"
IMG_SIZE = 640
CONF_THRESHOLD = 0.25


# ============================================================
# MOTION DETECTION CONFIGURATION
# ============================================================

MOTION_PIXEL_THRESHOLD = 2500
DETECT_INTERVAL_SEC = 0.7


# ============================================================
# EVENT CONFIGURATION
# ============================================================

PERSISTENCE_HITS_REQUIRED = 2
EVENT_COOLDOWN_SEC = 10

ALERT_WAV = r"C:\Uday\alert.wav"
ALERT_REPEAT = 4

# Pretrained COCO classes used only for testing.
# Replace these later after training your garbage model.
TARGET_CLASSES = {"bottle", "cup"}

CONTEXT_CLASSES = {
    "person",
    "car",
    "motorcycle",
    "bus",
    "truck",
    "bicycle",
}

EVENT_DIR = "events"
os.makedirs(EVENT_DIR, exist_ok=True)


# ============================================================
# DISPLAY FUNCTIONS
# ============================================================

def draw_text(
    img,
    text,
    x,
    y,
    scale=0.6,
    color=(0, 255, 0),
    thickness=2,
):
    cv2.putText(
        img,
        text,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        color,
        thickness,
        cv2.LINE_AA,
    )


def draw_detections(frame, detections):
    for det in detections:
        x1, y1, x2, y2 = det["box"]
        label = det["label"]
        confidence = det["conf"]

        if label in TARGET_CLASSES:
            color = (0, 0, 255)          # Red
        elif label in CONTEXT_CLASSES:
            color = (255, 255, 0)        # Cyan
        else:
            color = (0, 255, 0)          # Green

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            color,
            2,
        )

        draw_text(
            frame,
            f"{label} {confidence:.2f}",
            x1,
            max(20, y1 - 8),
            scale=0.55,
            color=color,
            thickness=2,
        )


# ============================================================
# AUDIO AND EVENT FUNCTIONS
# ============================================================

def play_alert_sound():
    try:
        if not os.path.exists(ALERT_WAV):
            print(f"WARNING: Audio file not found: {ALERT_WAV}")
            return

        for _ in range(ALERT_REPEAT):
            winsound.PlaySound(
                ALERT_WAV,
                winsound.SND_FILENAME,
            )

    except Exception as error:
        print(f"Audio playback error: {error}")


def save_event_image(frame, detections, roi, reason):
    event_frame = frame.copy()

    x, y, w, h = roi

    cv2.rectangle(
        event_frame,
        (x, y),
        (x + w, y + h),
        (255, 0, 255),
        2,
    )

    draw_detections(event_frame, detections)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(
        EVENT_DIR,
        f"event_{timestamp}.jpg",
    )

    draw_text(
        event_frame,
        f"EVENT: {reason}",
        20,
        30,
        scale=0.8,
        color=(0, 0, 255),
        thickness=2,
    )

    saved = cv2.imwrite(path, event_frame)

    if not saved:
        print(f"WARNING: Could not save event image: {path}")

    # Audio plays in the background so that video processing continues.
    threading.Thread(
        target=play_alert_sound,
        daemon=True,
    ).start()

    return path


# ============================================================
# YOLO DETECTION FUNCTION
# ============================================================

def run_yolo_on_roi(model, frame, roi):
    x, y, w, h = roi

    crop = frame[y:y + h, x:x + w]

    if crop.size == 0:
        return []

    results = model.predict(
        source=crop,
        imgsz=IMG_SIZE,
        conf=CONF_THRESHOLD,
        device="cpu",
        verbose=False,
    )

    detections = []

    for result in results:
        if result.boxes is None:
            continue

        for box in result.boxes:
            class_id = int(box.cls[0].item())
            confidence = float(box.conf[0].item())
            label = model.names[class_id]

            x1, y1, x2, y2 = map(
                int,
                box.xyxy[0].tolist(),
            )

            # Convert ROI coordinates to complete-frame coordinates.
            detections.append(
                {
                    "label": label,
                    "conf": confidence,
                    "box": (
                        x1 + x,
                        y1 + y,
                        x2 + x,
                        y2 + y,
                    ),
                }
            )

    return detections


# ============================================================
# HIKVISION RTSP FUNCTIONS
# ============================================================

def open_stream():
    """
    Open the Hikvision RTSP stream using FFmpeg and RTSP over TCP.
    """

    print("Connecting to Hikvision camera...")

    cap = cv2.VideoCapture(
        RTSP_URL,
        cv2.CAP_FFMPEG,
    )

    # Fallback if explicit FFmpeg backend does not work.
    if not cap.isOpened():
        print("FFmpeg backend failed. Trying default OpenCV backend...")

        cap.release()

        cap = cv2.VideoCapture(RTSP_URL)

    # Keep the video buffer small to reduce delayed frames.
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    return cap


def read_first_frame(cap, timeout_sec=15):
    """
    Wait until the RTSP camera sends a valid frame.
    """

    deadline = time.time() + timeout_sec

    while time.time() < deadline:
        ok, frame = cap.read()

        if (
            ok
            and frame is not None
            and frame.size > 0
        ):
            return True, frame

        time.sleep(0.1)

    return False, None


def reconnect_stream():
    """
    Repeatedly attempt to reconnect to the Hikvision camera.
    """

    while True:
        print("Attempting RTSP reconnection...")

        cap = open_stream()

        if cap.isOpened():
            ok, frame = read_first_frame(
                cap,
                timeout_sec=10,
            )

            if ok:
                print("RTSP reconnection successful.")
                return cap, frame

        cap.release()

        print(
            f"Reconnection failed. Retrying in "
            f"{RECONNECT_DELAY_SEC} seconds..."
        )

        time.sleep(RECONNECT_DELAY_SEC)


# ============================================================
# MAIN PROGRAM
# ============================================================

def main():
    print("Loading YOLO model...")
    model = YOLO(MODEL_PATH)

    print(
        f"Opening Hikvision camera at {RTSP_IP}, "
        f"channel {RTSP_CHANNEL}..."
    )

    cap = open_stream()

    if not cap.isOpened():
        print("ERROR: Could not open Hikvision RTSP stream.")
        print("Check:")
        print("1. Camera IP address")
        print("2. Username and password")
        print("3. Ethernet connection")
        print("4. RTSP service enabled in camera")
        print("5. Laptop Ethernet IP configuration")
        return

    ok, frame = read_first_frame(
        cap,
        timeout_sec=FIRST_FRAME_TIMEOUT_SEC,
    )

    if not ok:
        print(
            "ERROR: Camera connection opened, "
            "but no valid frame was received."
        )

        cap.release()
        return

    print(
        "Select dumping zone ROI and press ENTER or SPACE. "
        "Press C to cancel."
    )

    roi = cv2.selectROI(
        "Select ROI",
        frame,
        fromCenter=False,
        showCrosshair=True,
    )

    cv2.destroyWindow("Select ROI")

    x, y, w, h = map(int, roi)

    if w == 0 or h == 0:
        print("No ROI selected. Exiting.")
        cap.release()
        cv2.destroyAllWindows()
        return

    print(f"Selected ROI: x={x}, y={y}, width={w}, height={h}")

    # Reopen the RTSP stream after ROI selection.
    # This removes any old frames accumulated while selecting the ROI.
    cap.release()
    time.sleep(0.5)

    cap = open_stream()

    if not cap.isOpened():
        print("ERROR: Could not reopen camera after ROI selection.")
        return

    ok, frame = read_first_frame(
        cap,
        timeout_sec=FIRST_FRAME_TIMEOUT_SEC,
    )

    if not ok:
        print("ERROR: No video received after reopening camera.")
        cap.release()
        return

    background_subtractor = (
        cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=25,
            detectShadows=True,
        )
    )

    last_detect_time = 0
    last_event_time = 0

    cached_detections = []
    persistence_hits = 0
    event_count = 0

    print("Program running.")
    print("Press q in the video window to stop.")

    while True:
        ok, frame = cap.read()

        if not ok or frame is None or frame.size == 0:
            print("RTSP frame lost.")

            cap.release()

            cap, frame = reconnect_stream()

            # Reset motion model after reconnection.
            background_subtractor = (
                cv2.createBackgroundSubtractorMOG2(
                    history=500,
                    varThreshold=25,
                    detectShadows=True,
                )
            )

            cached_detections = []
            persistence_hits = 0

        display = frame.copy()

        # Draw the selected ROI.
        cv2.rectangle(
            display,
            (x, y),
            (x + w, y + h),
            (255, 0, 255),
            2,
        )

        draw_text(
            display,
            "ROI",
            x,
            max(20, y - 10),
            scale=0.6,
            color=(255, 0, 255),
            thickness=2,
        )

        roi_frame = frame[y:y + h, x:x + w]

        if roi_frame.size == 0:
            draw_text(
                display,
                "Invalid ROI",
                20,
                30,
                scale=0.8,
                color=(0, 0, 255),
                thickness=2,
            )

            cv2.imshow(
                "Trash Detection - Hikvision",
                display,
            )

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            continue

        # ----------------------------------------------------
        # Motion detection
        # ----------------------------------------------------

        foreground_mask = background_subtractor.apply(
            roi_frame
        )

        _, threshold_mask = cv2.threshold(
            foreground_mask,
            200,
            255,
            cv2.THRESH_BINARY,
        )

        kernel = np.ones(
            (3, 3),
            np.uint8,
        )

        threshold_mask = cv2.morphologyEx(
            threshold_mask,
            cv2.MORPH_OPEN,
            kernel,
        )

        threshold_mask = cv2.dilate(
            threshold_mask,
            kernel,
            iterations=2,
        )

        motion_pixels = cv2.countNonZero(
            threshold_mask
        )

        motion_present = (
            motion_pixels > MOTION_PIXEL_THRESHOLD
        )

        # ----------------------------------------------------
        # YOLO inference
        # ----------------------------------------------------

        now = time.time()

        if (
            motion_present
            and now - last_detect_time >= DETECT_INTERVAL_SEC
        ):
            cached_detections = run_yolo_on_roi(
                model,
                frame,
                (x, y, w, h),
            )

            last_detect_time = now

        draw_detections(
            display,
            cached_detections,
        )

        target_detections = [
            detection
            for detection in cached_detections
            if detection["label"] in TARGET_CLASSES
        ]

        context_detections = [
            detection
            for detection in cached_detections
            if detection["label"] in CONTEXT_CLASSES
        ]

        # ----------------------------------------------------
        # Persistence logic
        # ----------------------------------------------------

        if motion_present and len(target_detections) > 0:
            persistence_hits += 1
        else:
            persistence_hits = max(
                0,
                persistence_hits - 1,
            )

        # ----------------------------------------------------
        # Event logic
        # ----------------------------------------------------

        if (
            persistence_hits >= PERSISTENCE_HITS_REQUIRED
            and now - last_event_time >= EVENT_COOLDOWN_SEC
        ):
            detected_target_names = sorted(
                {
                    detection["label"]
                    for detection in target_detections
                }
            )

            reason = (
                "target="
                + ",".join(detected_target_names)
            )

            event_path = save_event_image(
                frame,
                cached_detections,
                (x, y, w, h),
                reason,
            )

            event_count += 1
            last_event_time = now
            persistence_hits = 0

            print(f"[EVENT] Saved: {event_path}")

        # ----------------------------------------------------
        # Screen information
        # ----------------------------------------------------

        draw_text(
            display,
            f"Motion pixels: {motion_pixels}",
            20,
            30,
            scale=0.7,
            color=(
                (0, 255, 0)
                if motion_present
                else (200, 200, 200)
            ),
            thickness=2,
        )

        draw_text(
            display,
            f"Motion: {'YES' if motion_present else 'NO'}",
            20,
            60,
            scale=0.7,
            color=(
                (0, 255, 0)
                if motion_present
                else (200, 200, 200)
            ),
            thickness=2,
        )

        draw_text(
            display,
            f"Targets: {[d['label'] for d in target_detections]}",
            20,
            90,
            scale=0.7,
            color=(0, 0, 255),
            thickness=2,
        )

        draw_text(
            display,
            f"Context: {[d['label'] for d in context_detections]}",
            20,
            120,
            scale=0.7,
            color=(255, 255, 0),
            thickness=2,
        )

        draw_text(
            display,
            f"Persistence hits: {persistence_hits}",
            20,
            150,
            scale=0.7,
            color=(255, 255, 255),
            thickness=2,
        )

        draw_text(
            display,
            f"Events saved: {event_count}",
            20,
            180,
            scale=0.7,
            color=(255, 255, 255),
            thickness=2,
        )

        draw_text(
            display,
            "Press q to quit",
            20,
            210,
            scale=0.7,
            color=(255, 255, 255),
            thickness=2,
        )

        cv2.imshow(
            "Trash Detection - Hikvision",
            display,
        )

        # This black-and-white window shows motion pixels.
        cv2.imshow(
            "ROI Motion Mask",
            threshold_mask,
        )

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
