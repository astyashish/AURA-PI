"""
Voice Input — 100% offline, local STT.
Engines (priority order):
  1. Vosk (fast, keyword-perfect, wake-word)
  2. faster-whisper tiny (multilingual, conversational turns)

Audio device handling:
  - Tries PulseAudio → ALSA → any available input device
  - Never crashes on missing mic — gracefully disables
  - Auto-detects Bluetooth headset microphone
  - Suppresses all ALSA spam to stderr
"""

import os
import sys
import json
import time
import threading
from pathlib import Path
from contextlib import contextmanager

# ── Safe ALSA / PortAudio error suppression ──────────────────────────────────
# Temporarily redirect C-level stderr (fd 2) during PyAudio calls to prevent ALSA
# log spam. This avoids ctypes C-callbacks which cause Segmentation Faults.
@contextmanager
def _suppress_c_stderr():
    """Safely suppress C-level stderr without risky ctypes callbacks."""
    try:
        if sys.platform.startswith("linux"):
            null_fd = os.open(os.devnull, os.O_WRONLY)
            orig_stderr = os.dup(2)
            sys.stderr.flush()
            os.dup2(null_fd, 2)
            os.close(null_fd)
            try:
                yield
            finally:
                os.dup2(orig_stderr, 2)
                os.close(orig_stderr)
        else:
            yield
    except Exception:
        yield


# ── Device probe helpers ─────────────────────────────────────────────────────

def _list_input_devices(pa):
    """Return list of (index, name, sample_rate) for all input devices."""
    devices = []
    try:
        count = pa.get_device_count()
    except Exception:
        return devices

    for i in range(count):
        try:
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                devices.append({
                    "index": i,
                    "name": str(info.get("name", "")),
                    "channels": int(info.get("maxInputChannels", 1)),
                    "sample_rate": int(info.get("defaultSampleRate", 16000)),
                })
        except Exception:
            continue
    return devices


def _pick_best_input_device(pa):
    """
    Return (device_index_or_None, chosen_name).
    Prefers Bluetooth → USB mic → system default.
    Returns (None, 'default') to let PyAudio use the system default.
    """
    bt_kw  = ["bluetooth", "bluez", "a2dp", "hsp", "hfp", "headset",
               "earbuds", "airpod", "headphones"]
    usb_kw = ["usb", "webcam", "c920", "c925", "c922", "logitech", "jabra",
               "rode", "blue", "snowball"]

    devs = _list_input_devices(pa)
    if not devs:
        return None, "none"

    bt_dev  = next((d for d in devs if any(k in d["name"].lower() for k in bt_kw)), None)
    usb_dev = next((d for d in devs if any(k in d["name"].lower() for k in usb_kw)), None)

    # Try system default first as it's usually correct
    try:
        default_info = pa.get_default_input_device_info()
        default_idx  = int(default_info["index"])
        default_name = str(default_info.get("name", "default"))
    except Exception:
        default_idx  = None
        default_name = "none"

    chosen = bt_dev or usb_dev
    if chosen:
        return chosen["index"], chosen["name"]
    if default_idx is not None:
        return default_idx, default_name
    if devs:
        return devs[0]["index"], devs[0]["name"]
    return None, "none"


def _can_open_stream(pa, device_index, sample_rate=16000):
    """Return True if we can actually open a recording stream on this device."""
    kwargs = dict(
        format=0x00000008,  # paInt16 = 8
        channels=1,
        rate=sample_rate,
        input=True,
        frames_per_buffer=4096,
    )
    try:
        # Import paInt16 properly
        import pyaudio
        kwargs["format"] = pyaudio.paInt16
    except Exception:
        return False

    if device_index is not None:
        kwargs["input_device_index"] = device_index
    try:
        stream = pa.open(**kwargs)
        stream.close()
        return True
    except Exception:
        # Try without specific device (system default)
        if device_index is not None:
            kwargs.pop("input_device_index", None)
            try:
                stream = pa.open(**kwargs)
                stream.close()
                return True
            except Exception:
                pass
    return False


# ── Main class ───────────────────────────────────────────────────────────────

class VoiceInput:
    def __init__(
        self,
        model_path="models/vosk-model-small-en-us-0.15",
        sample_rate=16000,
    ):
        self.model_path   = model_path
        self.sample_rate  = sample_rate
        self.enabled      = False          # Vosk ready
        self.whisper_enabled = False       # Whisper ready
        self.last_language   = "en"

        self._vosk   = None
        self._model  = None
        self._pa_lib = None                # pyaudio module
        self._dev_idx = None               # chosen input device index
        self._dev_name = "none"
        self._whisper_model = None

        self._setup_vosk()
        self._setup_whisper()

    # ── Setup ────────────────────────────────────────────────────────────────

    def _setup_vosk(self):
        # Import PyAudio
        try:
            import pyaudio
            self._pa_lib = pyaudio
        except ImportError:
            print("[Voice] PyAudio not installed.")
            print("[Voice] Fix: sudo apt-get install portaudio19-dev && pip install pyaudio")
            return

        # Probe audio devices
        try:
            with _suppress_c_stderr():
                pa = self._pa_lib.PyAudio()
        except Exception as e:
            print(f"[Voice] PyAudio init error: {e}")
            return

        try:
            dev_idx, dev_name = _pick_best_input_device(pa)
            if not _can_open_stream(pa, dev_idx, self.sample_rate):
                # last resort: try every device
                found = False
                for d in _list_input_devices(pa):
                    if _can_open_stream(pa, d["index"], self.sample_rate):
                        dev_idx, dev_name = d["index"], d["name"]
                        found = True
                        break
                if not found:
                    print("[Voice] No working microphone found.")
                    print("[Voice] → Connect a USB mic or pair Bluetooth earbuds.")
                    print("[Voice] → Text commands via web UI still work.")
                    return
            self._dev_idx  = dev_idx
            self._dev_name = dev_name
        finally:
            pa.terminate()

        # Load Vosk model
        try:
            import vosk
            if not Path(self.model_path).exists():
                print(f"[Voice] Vosk model missing: {self.model_path}")
                print("[Voice] Run: bash setup.sh   (it downloads the model)")
                return
            vosk.SetLogLevel(-1)           # suppress Vosk log spam
            self._vosk  = vosk
            self._model = vosk.Model(self.model_path)
            self.enabled = True
            print(f"[Voice] ✓ Vosk STT ready  |  mic: {self._dev_name} (idx={self._dev_idx})")
        except ImportError:
            print("[Voice] Vosk not installed: pip install vosk")
        except Exception as e:
            print(f"[Voice] Vosk init error: {e}")

    def _setup_whisper(self):
        try:
            import faster_whisper
            self.whisper_enabled = True
            print("[Voice] ✓ Whisper STT available (lazy loaded)")
        except ImportError:
            print("[Voice] faster-whisper not installed — English-only mode")
        except Exception as e:
            print(f"[Voice] Whisper check: {e}")

    # ── Stream helpers ───────────────────────────────────────────────────────

    def _open_stream(self):
        """
        Open a PyAudio input stream.
        Returns (pa_instance, stream) or (None, None).
        Never raises — always returns safely.
        """
        try:
            with _suppress_c_stderr():
                pa = self._pa_lib.PyAudio()
        except Exception:
            return None, None

        kwargs = dict(
            format=self._pa_lib.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=4096,
        )
        if self._dev_idx is not None:
            kwargs["input_device_index"] = self._dev_idx

        # Try with chosen device first, then without (system default)
        for attempt_kwargs in [kwargs, {k: v for k, v in kwargs.items()
                                         if k != "input_device_index"}]:
            try:
                stream = pa.open(**attempt_kwargs)
                return pa, stream
            except Exception:
                continue

        pa.terminate()
        return None, None

    # ── Public API ───────────────────────────────────────────────────────────

    def listen_once(self, timeout=10, use_whisper=False) -> str:
        """
        Listen until speech detected or timeout.
        Returns transcribed text string (may be empty on silence/error).
        """
        if not self.enabled:
            return ""

        pa, stream = self._open_stream()
        if stream is None:
            return ""

        rec = self._vosk.KaldiRecognizer(self._model, self.sample_rate)
        stream.start_stream()
        print("[Voice] 🎤 Listening...")

        result_text  = ""
        silence_frames = 0
        max_silence  = int(timeout * self.sample_rate / 4096)
        audio_buf    = bytearray()

        try:
            while silence_frames < max_silence:
                try:
                    data = stream.read(4096, exception_on_overflow=False)
                except OSError:
                    break
                audio_buf.extend(data)

                if rec.AcceptWaveform(data):
                    if use_whisper and self.whisper_enabled:
                        break                          # hand off to Whisper
                    result = json.loads(rec.Result())
                    text   = result.get("text", "").strip()
                    if text:
                        result_text = text
                        break
                    silence_frames += 1
                else:
                    partial = json.loads(rec.PartialResult()).get("partial", "")
                    silence_frames = 0 if partial else silence_frames + 1

        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            pa.terminate()

        # Whisper pass
        if use_whisper and self.whisper_enabled and len(audio_buf) > 2048:
            try:
                if self._whisper_model is None:
                    from faster_whisper import WhisperModel
                    print("[Voice] Loading Whisper model (tiny, int8)...")
                    self._whisper_model = WhisperModel(
                        "tiny", device="cpu", compute_type="int8",
                        download_root="models/whisper"
                    )
                import numpy as np
                print("[Voice] Transcribing with Whisper...")
                audio_np = (
                    np.frombuffer(audio_buf, dtype=np.int16).astype(np.float32) / 32768.0
                )
                segs, info = self._whisper_model.transcribe(audio_np, beam_size=1)
                result_text = " ".join(s.text for s in segs).strip()
                self.last_language = info.language
                print(f"[Voice] Whisper → lang={info.language}  '{result_text}'")
            except Exception as e:
                print(f"[Voice] Whisper error: {e}")

        if result_text:
            print(f"[Voice] Heard: '{result_text}'")
        return result_text

    def wait_for_wake_word(self, wake_word="aura"):
        """
        Block until the wake word is detected (or mic not available → sleep 2s).
        Safe to call in a loop indefinitely.
        """
        if not self.enabled:
            time.sleep(2)
            return

        pa, stream = self._open_stream()
        if stream is None:
            print("[Voice] Mic unavailable — retrying in 10s")
            time.sleep(10)
            return

        rec = self._vosk.KaldiRecognizer(self._model, self.sample_rate)
        stream.start_stream()
        print(f"[Voice] 👂 Waiting for wake word: '{wake_word}'")

        try:
            while True:
                try:
                    data = stream.read(4096, exception_on_overflow=False)
                except OSError:
                    break
                if rec.AcceptWaveform(data):
                    text = json.loads(rec.Result()).get("text", "").lower()
                    if wake_word.lower() in text:
                        print(f"[Voice] ✓ Wake word detected!")
                        break
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            pa.terminate()

    def detect_wake_word(self, wake_word="aura", callback=None):
        """Start wake-word detection loop in a background daemon thread."""
        def _loop():
            while True:
                self.wait_for_wake_word(wake_word)
                if callback:
                    try:
                        callback()
                    except Exception as e:
                        print(f"[Voice] Wake callback error: {e}")

        t = threading.Thread(target=_loop, daemon=True, name="wake-word")
        t.start()
        print(f"[Voice] Wake word listener active — say '{wake_word}'")
        return t

    def list_devices(self):
        """Return list of available audio input devices (for diagnostics)."""
        if not self._pa_lib:
            return []
        pa = self._pa_lib.PyAudio()
        try:
            return _list_input_devices(pa)
        finally:
            pa.terminate()
