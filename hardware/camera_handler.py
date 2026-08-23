"""
Camera Handler — captures frames from Pi Camera or USB webcam.
Saves to file for LLaVA vision analysis.
"""

import base64
import os
import time
from pathlib import Path
from datetime import datetime

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("[Camera] OpenCV not installed — camera disabled")


class CameraHandler:
    def __init__(self, capture_dir="captured_images"):
        self.capture_dir = Path(capture_dir)
        self.capture_dir.mkdir(exist_ok=True)
        self.cap = None
        self.enabled = False

    def start(self) -> bool:
        if not CV2_AVAILABLE:
            return False
        try:
            self.cap = cv2.VideoCapture(0)
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.enabled = True
                print("[Camera] Camera started on index 0")
                return True
            else:
                print("[Camera] No camera found")
                return False
        except Exception as e:
            print(f"[Camera] Failed to start: {e}")
            return False

    def capture_frame(self) -> dict:
        """Capture a single frame and return as base64 + save to disk."""
        if not self.enabled or not self.cap:
            return {"success": False, "error": "Camera not available"}

        ret, frame = self.cap.read()
        if not ret:
            return {"success": False, "error": "Failed to capture frame"}

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.capture_dir / f"capture_{timestamp}.jpg"
        cv2.imwrite(str(filename), frame)

        _, buffer = cv2.imencode(".jpg", frame)
        img_base64 = base64.b64encode(buffer).decode("utf-8")

        return {
            "success": True,
            "path": str(filename),
            "base64": img_base64,
            "timestamp": timestamp
        }

    def get_preview_frame(self):
        """Get a base64 JPEG for the web dashboard live preview."""
        if not self.enabled or not self.cap:
            return None
        ret, frame = self.cap.read()
        if not ret:
            return None
        frame_small = cv2.resize(frame, (320, 240))
        _, buffer = cv2.imencode(".jpg", frame_small, [cv2.IMWRITE_JPEG_QUALITY, 60])
        return base64.b64encode(buffer).decode("utf-8")

    def stop(self):
        if self.cap:
            self.cap.release()
            self.enabled = False
