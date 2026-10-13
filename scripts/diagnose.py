#!/usr/bin/env python3
"""
AURA-PI System Diagnostic
Run on the Raspberry Pi to check all subsystems before starting AURA.

Usage:
    source venv/bin/activate
    python scripts/diagnose.py
"""

import os
import sys
import subprocess
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"
INFO = "\033[94mℹ\033[0m"

def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return r.returncode == 0, r.stdout.strip()
    except Exception as e:
        return False, str(e)


def check(label, ok, detail=""):
    icon = PASS if ok else FAIL
    print(f"  {icon} {label}", end="")
    if detail:
        print(f"  [{detail}]", end="")
    print()
    return ok


def section(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


def main():
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║   AURA-PI System Diagnostic                         ║")
    print("╚══════════════════════════════════════════════════════╝")

    # ── GPIO ──────────────────────────────────────────────────────
    section("GPIO")
    try:
        from hardware.gpio_controller import GPIOController, GPIO_BACKEND, REAL_GPIO
        ctrl = GPIOController()
        check("GPIO controller initialized", True, f"backend={GPIO_BACKEND}, real={REAL_GPIO}")
        devs = ctrl.get_all_states()
        check(f"Devices loaded ({len(devs)} devices)", len(devs) > 0)
        for did, d in devs.items():
            pin = d["gpio_pin"]
            print(f"      Pin {pin:2d} → {d['name']:<25} [{'ON ' if d['state'] else 'off'}]")
    except Exception as e:
        check("GPIO controller", False, str(e))

    # Test real GPIO if available
    if REAL_GPIO:
        section("GPIO Pin Test")
        try:
            from hardware.gpio_controller import GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(17, GPIO.OUT)
            GPIO.output(17, GPIO.HIGH)
            import time; time.sleep(0.1)
            GPIO.output(17, GPIO.LOW)
            GPIO.cleanup(17)
            check("GPIO pin 17 HIGH/LOW test", True)
        except Exception as e:
            check("GPIO pin test", False, str(e))

    # ── Audio ─────────────────────────────────────────────────────
    section("Audio")

    # PyAudio
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        n_in = sum(1 for i in range(pa.get_device_count())
                   if pa.get_device_info_by_index(i).get("maxInputChannels", 0) > 0)
        n_out = sum(1 for i in range(pa.get_device_count())
                    if pa.get_device_info_by_index(i).get("maxOutputChannels", 0) > 0)
        check("PyAudio installed", True, f"{n_in} input, {n_out} output devices")

        # List input devices
        print("    Input devices:")
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                name = info.get("name", "")
                print(f"      [{i}] {name}")
        print("    Output devices:")
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("maxOutputChannels", 0) > 0:
                name = info.get("name", "")
                print(f"      [{i}] {name}")
        pa.terminate()
    except ImportError:
        check("PyAudio installed", False, "run: pip install pyaudio")
    except Exception as e:
        check("PyAudio", False, str(e))

    # PulseAudio/PipeWire
    ok, out = _run(["pactl", "info"])
    check("PulseAudio/PipeWire running", ok,
          out.split("\n")[0] if ok else "run: systemctl --user start pipewire pipewire-pulse")

    # BT sink
    ok2, out2 = _run(["pactl", "list", "sinks", "short"])
    bt_sink = next((l.split("\t")[1] for l in out2.splitlines()
                    if any(k in l.lower() for k in ["bluez", "bluetooth", "a2dp"])), None)
    check("Bluetooth audio sink", bt_sink is not None,
          bt_sink if bt_sink else "not found — pair earbuds with setup_bluetooth.sh")

    # ── Voice STT ─────────────────────────────────────────────────
    section("Voice — STT")

    vosk_model = Path("models/vosk-model-small-en-us-0.15")
    check("Vosk model exists", vosk_model.exists(),
          str(vosk_model) if not vosk_model.exists() else "")
    try:
        import vosk
        check("Vosk library", True, f"version {vosk.__version__}")
    except ImportError:
        check("Vosk library", False, "run: pip install vosk")

    try:
        from faster_whisper import WhisperModel
        check("faster-whisper library", True)
    except ImportError:
        check("faster-whisper library", False, "run: pip install faster-whisper")

    try:
        from core.voice_input import VoiceInput
        vi = VoiceInput()
        check("VoiceInput initialized", True, f"enabled={vi.enabled}, whisper={vi.whisper_enabled}")
        if vi.enabled:
            devs = vi.list_audio_devices()
            check(f"Audio input devices ({len(devs)})", len(devs) > 0)
    except Exception as e:
        check("VoiceInput", False, str(e))

    # ── Voice TTS ─────────────────────────────────────────────────
    section("Voice — TTS")

    ok, _ = _run(["/usr/local/bin/piper", "--version"])
    check("Piper TTS binary", ok, "/usr/local/bin/piper")

    piper_voice = Path("models/voices/en_US-lessac-medium.onnx")
    check("Piper voice model", piper_voice.exists(), str(piper_voice))

    ok, _ = _run(["espeak-ng", "--version"])
    check("espeak-ng (fallback)", ok)

    try:
        from core.voice_output import VoiceOutput
        vo = VoiceOutput()
        check("VoiceOutput initialized", vo.enabled, f"engine={vo.engine}")
    except Exception as e:
        check("VoiceOutput", False, str(e))

    # ── Bluetooth ─────────────────────────────────────────────────
    section("Bluetooth")

    ok, _ = _run(["bluetoothctl", "show"])
    check("Bluetooth adapter", ok)

    ok, out = _run(["bluetoothctl", "devices"])
    paired = [l for l in out.splitlines() if l.strip()]
    check(f"Paired BT devices ({len(paired)})", len(paired) > 0,
          "run scripts/setup_bluetooth.sh to pair earbuds" if not paired else "")
    for d in paired:
        print(f"      {d}")

    # Check saved MAC
    mac_file = Path(".bt_device_mac")
    if mac_file.exists():
        mac = mac_file.read_text().strip()
        check("Saved BT MAC", True, mac)

    # ── Ollama / LLM ──────────────────────────────────────────────
    section("Ollama / LLM")

    ok, out = _run(["ollama", "list"])
    check("Ollama installed", ok)
    if ok:
        models = [l.split()[0] for l in out.splitlines()[1:] if l.strip()]
        check(f"Models available ({len(models)})", len(models) > 0)
        for m in models:
            print(f"      {m}")

    try:
        from core.llm_engine import LLMEngine
        llm = LLMEngine()
        avail = llm.is_available()
        check("LLM engine running", avail,
              "start with: ollama serve" if not avail else "")
    except Exception as e:
        check("LLM engine", False, str(e))

    # ── Web server ────────────────────────────────────────────────
    section("Web Server")

    try:
        import flask
        check("Flask installed", True, flask.__version__)
    except ImportError:
        check("Flask installed", False)

    print("\n" + "═"*52)
    print("  Diagnostic complete.")
    print("  Fix any ✗ items above, then run: python main.py")
    print("═"*52 + "\n")


if __name__ == "__main__":
    main()
