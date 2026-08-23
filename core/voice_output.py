"""
Voice Output — text to speech using Piper TTS (offline).
Falls back to espeak if Piper not available, then silent mode.
"""

import os
import subprocess
import tempfile
import threading
from pathlib import Path


class VoiceOutput:
    def __init__(self, piper_path="/usr/local/bin/piper", voice_model_path=None):
        self.piper_path = piper_path
        self.voice_model_path = voice_model_path or "models/voices/en_US-lessac-medium.onnx"
        self.enabled = False
        self.engine = None
        self._setup()

    def _setup(self):
        # Try Piper first
        if Path(self.piper_path).exists() and Path(self.voice_model_path).exists():
            self.engine = "piper"
            self.enabled = True
            print("[TTS] Piper TTS initialized")
            return
        # Try espeak fallback
        try:
            result = subprocess.run(["espeak", "--version"], capture_output=True, timeout=3)
            if result.returncode == 0:
                self.engine = "espeak"
                self.enabled = True
                print("[TTS] Using espeak (fallback)")
                return
        except:
            pass
        # Try pyttsx3 on Windows
        try:
            import pyttsx3
            self._pyttsx3 = pyttsx3.init()
            self.engine = "pyttsx3"
            self.enabled = True
            print("[TTS] Using pyttsx3 (Windows/fallback)")
            return
        except:
            pass
        print("[TTS] No TTS engine available — silent mode")

    def speak(self, text: str, blocking: bool = True):
        """Speak text aloud."""
        if not self.enabled or not text.strip():
            return

        def _do_speak():
            if self.engine == "piper":
                self._speak_piper(text)
            elif self.engine == "espeak":
                subprocess.run(["espeak", "-s", "150", "-p", "50", text], timeout=30)
            elif self.engine == "pyttsx3":
                self._pyttsx3.say(text)
                self._pyttsx3.runAndWait()

        if blocking:
            _do_speak()
        else:
            t = threading.Thread(target=_do_speak, daemon=True)
            t.start()

    def _speak_piper(self, text: str):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
        try:
            cmd = [self.piper_path, "--model", self.voice_model_path, "--output_file", tmp_path]
            subprocess.run(cmd, input=text.encode(), timeout=30, check=True)
            subprocess.run(["aplay", tmp_path], timeout=30)
        except Exception as e:
            print(f"[TTS] Piper error: {e}")
        finally:
            if Path(tmp_path).exists():
                os.unlink(tmp_path)
