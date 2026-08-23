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
        self.whisper_enabled = False
        self._whisper_model = None
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

        # Try initializing Whisper for multilingual support
        try:
            from faster_whisper import WhisperModel
            # Load tiny model. On Pi 5 this runs fast on CPU with int8
            self._whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
            self.whisper_enabled = True
            print("[Voice] Whisper STT initialized (Multilingual)")
        except ImportError:
            print("[Voice] faster-whisper not installed. Multilingual STT disabled.")
        except Exception as e:
            print(f"[Voice] Whisper setup failed: {e}")

    def listen_once(self, timeout=10, use_whisper=False) -> str:
        """Listen for a single utterance and return transcribed text."""
        if not self.enabled:
            return ""

        pa = self._pyaudio.PyAudio()
        rec = self._vosk.KaldiRecognizer(self._model, self.sample_rate)
        try:
            stream = pa.open(
                format=self._pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=4096
            )
        except OSError as e:
            print(f"[Voice] Microphone access failed: {e}")
            return ""
        stream.start_stream()

        print("[Voice] Listening...")
        result_text = ""
        silence_count = 0
        max_silence = int(timeout * self.sample_rate / 4096)

        try:
            audio_buffer = bytearray()
            while silence_count < max_silence:
                data = stream.read(4096, exception_on_overflow=False)
                audio_buffer.extend(data)
                
                if rec.AcceptWaveform(data):
                    if use_whisper and self.whisper_enabled:
                        # Break to process the accumulated audio buffer with whisper
                        break
                        
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

        if use_whisper and self.whisper_enabled and len(audio_buffer) > 0:
            import numpy as np
            print("[Voice] Transcribing with Whisper...")
            # Whisper expects float32 array in [-1.0, 1.0]
            audio_np = np.frombuffer(audio_buffer, dtype=np.int16).astype(np.float32) / 32768.0
            segments, info = self._whisper_model.transcribe(audio_np, beam_size=1)
            result_text = " ".join(segment.text for segment in segments).strip()
            self.last_language = info.language
            print(f"[Voice] Whisper detected language '{info.language}'")

        return result_text

    def wait_for_wake_word(self, wake_word="aura"):
        """Block and listen until wake word is detected, then close stream and return."""
        if not self.enabled:
            import time
            time.sleep(1)
            return

        pa = self._pyaudio.PyAudio()
        rec = self._vosk.KaldiRecognizer(self._model, self.sample_rate)
        try:
            stream = pa.open(
                format=self._pyaudio.paInt16, channels=1,
                rate=self.sample_rate, input=True, frames_per_buffer=4096
            )
        except OSError as e:
            print(f"[Voice] Microphone access failed: {e}. Voice wake word disabled.")
            import time
            time.sleep(10)
            return

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
                        break
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def detect_wake_word(self, wake_word="aura", callback=None):
