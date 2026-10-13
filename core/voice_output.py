"""
Voice Output — 100% offline, local TTS.
Engine priority: Piper → espeak-ng → espeak → pyttsx3 → silent

Audio routing:
  - Detects Bluetooth sink via pactl (PulseAudio / PipeWire-pulse)
  - Sets BT device as default sink automatically
  - Plays via: aplay → paplay → pw-play → ffplay (first that works)
  - All 100% local — no internet needed
"""

import os
import subprocess
import tempfile
import threading
from pathlib import Path


# ── Bluetooth sink detection ─────────────────────────────────────────────────

def _find_bt_sink() -> str | None:
    """Return the PulseAudio/PipeWire sink name for any connected BT device."""
    try:
        r = subprocess.run(
            ["pactl", "list", "sinks", "short"],
            capture_output=True, text=True, timeout=3
        )
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            name = parts[1]
            if any(k in name.lower() for k in
                   ["bluez", "bluetooth", "a2dp", "hsp", "hfp", "headset"]):
                return name.strip()
    except Exception:
        pass
    return None


def _set_default_sink(sink: str) -> bool:
    try:
        subprocess.run(
            ["pactl", "set-default-sink", sink],
            timeout=3, check=True, capture_output=True
        )
        return True
    except Exception:
        return False


def _play_wav(wav_path: str, bt_sink: str | None = None) -> bool:
    """
    Play a WAV file through the best available player.
    Returns True on success.
    """
    # 1. paplay (PulseAudio native — works with PipeWire-pulse too)
    try:
        cmd = ["paplay"]
        if bt_sink:
            cmd += ["--device", bt_sink]
        cmd.append(wav_path)
        subprocess.run(cmd, timeout=60, check=True, capture_output=True)
        return True
    except Exception:
        pass

    # 2. aplay (ALSA — usually routed through PulseAudio/PipeWire)
    try:
        subprocess.run(["aplay", wav_path],
                       timeout=60, check=True, capture_output=True)
        return True
    except Exception:
        pass

    # 3. pw-play (PipeWire native)
    try:
        subprocess.run(["pw-play", wav_path],
                       timeout=60, check=True, capture_output=True)
        return True
    except Exception:
        pass

    # 4. ffplay (ffmpeg)
    try:
        subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", wav_path],
            timeout=60, check=True
        )
        return True
    except Exception:
        pass

    return False


# ── VoiceOutput ──────────────────────────────────────────────────────────────

class VoiceOutput:
    def __init__(
        self,
        piper_path="/usr/local/bin/piper",
        voice_model_path=None,
    ):
        self.piper_path       = piper_path
        self.voice_model_path = (
            voice_model_path or "models/voices/en_US-lessac-medium.onnx"
        )
        self.enabled   = False
        self.engine    = None
        self._bt_sink  = None
        self._pyttsx3  = None
        self._lock     = threading.Lock()
        self._setup()

    # ── Setup ────────────────────────────────────────────────────────────────

    def _setup(self):
        # 1. Piper TTS (highest quality, fully offline)
        if (Path(self.piper_path).exists()
                and Path(self.voice_model_path).exists()):
            self.engine  = "piper"
            self.enabled = True
            print(f"[TTS] ✓ Piper TTS ready  ({self.voice_model_path})")
        # 2. espeak-ng
        elif self._cmd_exists("espeak-ng"):
            self.engine  = "espeak-ng"
            self.enabled = True
            print("[TTS] ✓ espeak-ng ready (fallback)")
        # 3. espeak
        elif self._cmd_exists("espeak"):
            self.engine  = "espeak"
            self.enabled = True
            print("[TTS] ✓ espeak ready (fallback)")
        # 4. pyttsx3 (Windows / cross-platform)
        else:
            try:
                import pyttsx3
                self._pyttsx3 = pyttsx3.init()
                self.engine   = "pyttsx3"
                self.enabled  = True
                print("[TTS] ✓ pyttsx3 ready (fallback)")
            except Exception:
                pass

        if not self.enabled:
            print("[TTS] ⚠  No TTS engine found — silent mode")
            print("[TTS]    Fix: sudo apt-get install espeak-ng")
            return

        # Detect + activate Bluetooth audio output
        self._detect_bt_sink()

    @staticmethod
    def _cmd_exists(cmd: str) -> bool:
        try:
            r = subprocess.run(
                [cmd, "--version"], capture_output=True, timeout=3
            )
            return r.returncode == 0
        except Exception:
            return False

    def _detect_bt_sink(self):
        sink = _find_bt_sink()
        if sink:
            _set_default_sink(sink)
            self._bt_sink = sink
            print(f"[TTS] ✓ Bluetooth sink → {sink}")
        else:
            print("[TTS]   No BT sink found — using default audio output")

    def refresh_bt(self):
        """Call when a Bluetooth device connects/disconnects."""
        self._detect_bt_sink()

    # ── Public speak API ─────────────────────────────────────────────────────

    def speak(self, text: str, blocking: bool = True, lang: str = "en"):
        """Speak text. lang is BCP-47 code e.g. 'en', 'hi', 'fr'."""
        if not self.enabled or not text.strip():
            return

        def _do():
            with self._lock:   # prevent overlapping speech
                self._speak_internal(text, lang)

        if blocking:
            _do()
        else:
            threading.Thread(target=_do, daemon=True, name="tts-speak").start()

    def _speak_internal(self, text: str, lang: str):
        try:
            if self.engine == "piper" and lang in ("en", "en-US", "en-GB", "en-IN"):
                self._piper_speak(text)
            elif self.engine in ("piper", "espeak-ng"):
                # Use espeak-ng for non-English or when piper is primary but
                # we're speaking a non-English language
                self._espeak_speak(text, lang, binary="espeak-ng")
            elif self.engine == "espeak":
                self._espeak_speak(text, lang, binary="espeak")
            elif self.engine == "pyttsx3" and self._pyttsx3:
                self._pyttsx3.say(text)
                self._pyttsx3.runAndWait()
        except Exception as e:
            print(f"[TTS] speak error: {e}")

    def _piper_speak(self, text: str):
        """Generate WAV with Piper → play via best available player."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
        try:
            cmd = [
                self.piper_path,
                "--model", self.voice_model_path,
                "--output_file", tmp,
            ]
            subprocess.run(
                cmd, input=text.encode("utf-8"),
                timeout=30, check=True, capture_output=True
            )
            ok = _play_wav(tmp, self._bt_sink)
            if not ok:
                print("[TTS] ⚠ All audio players failed — check audio setup")
        except subprocess.CalledProcessError as e:
            print(f"[TTS] Piper error: {e.stderr.decode()[:200]}")
        except Exception as e:
            print(f"[TTS] Piper error: {e}")
        finally:
            Path(tmp).unlink(missing_ok=True)

    def _espeak_speak(self, text: str, lang: str, binary="espeak-ng"):
        """Speak via espeak / espeak-ng — routes through PulseAudio → BT."""
        lang_code = lang.split("-")[0] if lang else "en"
        env = os.environ.copy()
        if self._bt_sink:
            env["PULSE_SINK"] = self._bt_sink
        try:
            subprocess.run(
                [binary, "-v", lang_code, "-s", "145", "-p", "45", text],
                timeout=60, env=env, capture_output=True
            )
        except Exception as e:
            print(f"[TTS] {binary} error: {e}")
