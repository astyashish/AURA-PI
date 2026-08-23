"""
Vision Engine — captures from camera and sends to LLaVA for image analysis.
"""

from hardware.camera_handler import CameraHandler
from core.llm_engine import LLMEngine


class VisionEngine:
    def __init__(self, camera: CameraHandler, llm: LLMEngine):
        self.camera = camera
        self.llm = llm

    def describe_scene(self, custom_prompt: str = None) -> dict:
        """Capture a frame and describe it using LLaVA."""
        frame = self.camera.capture_frame()
        if not frame["success"]:
            return {"success": False, "description": "Camera not available", "image_path": None}

        prompt = custom_prompt or "Describe what you see in this image in detail. What objects, people, or text are present?"
        description = self.llm.analyze_image(frame["base64"], prompt)

        return {
            "success": True,
            "description": description,
            "image_path": frame["path"],
            "timestamp": frame["timestamp"]
        }

    def identify_objects(self) -> dict:
        return self.describe_scene("List all objects you can identify in this image.")

    def read_text(self) -> dict:
        return self.describe_scene("Read and transcribe any text visible in this image.")
