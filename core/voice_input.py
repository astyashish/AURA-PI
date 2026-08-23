"""
Voice Input — microphone recording + Vosk offline speech-to-text.
Falls back gracefully if mic or Vosk not available.
"""

import os
import queue
import threading
import json
from pathlib import Path


class VoiceInput:
    def __init__(self, model_path="models/vosk-model-small-en-us-0.15", sample_rate=16000):
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.enabled = False
        self._model = None
        self._setup()

    def _setup(self):
        try:
            import vosk
            import pyaudio
            if not Path(self.model_path).exists():
                print(f"[Voice] Vosk model not found at {self.model_path}")
                print("[Voice] Run: python -m setup_voice_models to download")
                return
            self._vosk = vosk
            self._pyaudio = pyaudio
            self._model = vosk.Model(self.model_path)
            self.enabled = True
            print("[Voice] Vosk STT initialized")
        except ImportError:
            print("[Voice] Vosk/PyAudio not installed — voice input disabled")
        except Exception as e:
            print(f"[Voice] Setup failed: {e}")

    def listen_once(self, timeout=10) -> str:
        """Listen for a single utterance and return transcribed text."""
        if not self.enabled:
            return ""

        pa = self._pyaudio.PyAudio()
        rec = self._vosk.KaldiRecognizer(self._model, self.sample_rate)
        stream = pa.open(
            format=self._pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=4096
        )
        stream.start_stream()

        print("[Voice] Listening...")
        result_text = ""
        silence_count = 0
        max_silence = int(timeout * self.sample_rate / 4096)

        try:
            while silence_count < max_silence:
                data = stream.read(4096, exception_on_overflow=False)
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").strip()
                    if text:
                        result_text = text
                        break
                    else:
                        silence_count += 1
                else:
                    partial = json.loads(rec.PartialResult())
                    if partial.get("partial"):
                        silence_count = 0
                    else:
                        silence_count += 1
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

        return result_text

    def detect_wake_word(self, wake_word="jarvis", callback=None):
        """Continuously listen for wake word in background thread."""
        if not self.enabled:
            return

        def _listen_loop():
            pa = self._pyaudio.PyAudio()
            rec = self._vosk.KaldiRecognizer(self._model, self.sample_rate)
            stream = pa.open(
                format=self._pyaudio.paInt16, channels=1,
                rate=self.sample_rate, input=True, frames_per_buffer=4096
            )
            stream.start_stream()
            print(f"[Voice] Wake word detection active — say '{wake_word}'")
            try:
                while True:
                    data = stream.read(4096, exception_on_overflow=False)
                    if rec.AcceptWaveform(data):
                        result = json.loads(rec.Result())
                        text = result.get("text", "").lower()
                        if wake_word.lower() in text:
                            print(f"[Voice] Wake word detected!")
                            if callback:
                                callback()
            finally:
                stream.stop_stream()
                stream.close()
                pa.terminate()

        t = threading.Thread(target=_listen_loop, daemon=True)
        t.start()
        return t
