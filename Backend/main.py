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


MOTION_PIXEL_THRESHOLD = 2500
DETECT_INTERVAL_SEC = 5
ALERT_SOUND = r"C:\Users\chpsh\OneDrive\Desktop\sekai\garbage\GARBAGE-DETECTION\Backend\audio\ElevenLabs_2026-07-01T11_14_56_David - Deep, Warm, Narration_pvc_s50_m2.mp3"

pygame.mixer.init()

base_path = os.path.dirname(os.path.abspath(__file__))
os.chdir(base_path)

DETECTIONS_DIR = os.path.join(base_path, 'detections')
os.makedirs(DETECTIONS_DIR, exist_ok=True)


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


def get_yolov5():
    model = torch.hub.load('yolov5', 'custom', path='model/best1000.pt', source='local')
    model.conf = 0.50
    return model


model1 = get_yolov5()

# Force RTSP over TCP — UDP (the default) drops packets on this camera and
# causes HEVC decode errors. Must be set before cv2.VideoCapture is created.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

RTSP_USER = "admin"
RTSP_PASS = "Ap09bx5625"
RTSP_IP   = "169.254.5.71"
RTSP_URL  = f"rtsp://{RTSP_USER}:{RTSP_PASS}@{RTSP_IP}:554/Streaming/Channels/101"


def open_stream():
    cap = cv2.VideoCapture(RTSP_URL)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


video = open_stream()

bg_sub = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=25, detectShadows=True)
kernel = np.ones((3, 3), np.uint8)

last_detection = time.time()

print(f"Saving detections to: {DETECTIONS_DIR}")
print("Running. Press 'q' to quit.")

while True:
    ret, img = video.read()
    if not ret:
        print('Frame read failed — reconnecting...')
        video.release()
        time.sleep(2)
        video = open_stream()
        continue

    # Motion detection
    fg = bg_sub.apply(img)
    _, th = cv2.threshold(fg, 200, 255, cv2.THRESH_BINARY)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel)
    th = cv2.dilate(th, kernel, iterations=2)
    motion_pixels = cv2.countNonZero(th)
    motion_present = motion_pixels > MOTION_PIXEL_THRESHOLD

    # HUD
    font = cv2.FONT_HERSHEY_PLAIN
    cv2.putText(img, str(datetime.now()), (20, 40), font, 2, (255, 255, 255), 2, cv2.LINE_AA)
    status = f"Motion: {'YES' if motion_present else 'NO'} ({motion_pixels}px)"
    cv2.putText(img, status, (20, 70), font, 1.5, (0, 255, 0) if motion_present else (100, 100, 100), 2, cv2.LINE_AA)

    cv2.imshow('live video', img)

    if cv2.waitKey(1) == ord('q'):
        break

    # Run YOLO only when motion is detected and interval has passed
    if motion_present and (time.time() - last_detection >= DETECT_INTERVAL_SEC):
        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        results = model1(img_pil, size=320)
        data = json.loads(results.pandas().xyxy[0].to_json(orient="records"))

        if len(data) != 0:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(DETECTIONS_DIR, f"garbage_{timestamp}.jpg")
            annotated = Image.fromarray(results.render()[0])
            annotated.save(save_path)
            print(f"Garbage detected — saved: {save_path}")
            play_alert()
        else:
            print('Motion detected, no garbage')

        last_detection = time.time()

video.release()
cv2.destroyAllWindows()
