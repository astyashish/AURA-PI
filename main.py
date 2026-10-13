"""
AURA-PI — Main Entry Point
100% local / offline on Raspberry Pi.
  - GPIO via lgpio (Pi 5) or RPi.GPIO (Pi 4)
  - STT via Vosk (wake) + Whisper (chat)
  - TTS via Piper → espeak-ng → espeak
  - LLM via Ollama (local)
  - BT earbuds auto-routed via PipeWire/PulseAudio
"""

import os
import sys
import json
import time

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import threading
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_config():
    with open("config/aura_config.json", encoding="utf-8") as f:
        return json.load(f)


def print_banner():
    print("""
╔══════════════════════════════════════════════════════╗
║         A U R A - P I  v2.0                        ║
║   Local AI Assistant — Raspberry Pi + Ollama         ║
║   100% Offline — No Cloud — No API Keys              ║
╚══════════════════════════════════════════════════════╝""")


def check_ollama():
    from core.llm_engine import LLMEngine
    llm = LLMEngine()
    if not llm.is_available():
        print("  ⚠  Ollama not running — start: ollama serve &")
        print("     LLM features disabled until Ollama is started.")
        return False
    models = llm.list_models()
    names  = ", ".join(models) if models else "none"
    print(f"  ✓  Ollama ready  |  models: {names}")
    if not models:
        print("     Pull a model: ollama pull qwen2.5:3b")
    return True


def check_gpio():
    try:
        from hardware.gpio_controller import GPIO_BACKEND, REAL_GPIO
        status = "real hardware pins" if REAL_GPIO else "mock (dev mode)"
        print(f"  {'✓' if REAL_GPIO else 'ℹ'}  GPIO [{GPIO_BACKEND}] — {status}")
    except Exception as e:
        print(f"  ⚠  GPIO error: {e}")


def check_audio():
    try:
        import subprocess
        r = subprocess.run(
            ["pactl", "list", "sinks", "short"],
            capture_output=True, text=True, timeout=3
        )
        bt = next(
            (l.split("\t")[1] for l in r.stdout.splitlines()
             if any(k in l.lower() for k in ["bluez", "bluetooth", "a2dp"])),
            None
        )
        if bt:
            print(f"  ✓  Bluetooth audio: {bt}")
        else:
            print("  ℹ  No BT sink — using default audio")
            print("     Pair earbuds: bash scripts/setup_bluetooth.sh")
    except Exception:
        print("  ℹ  Audio status check skipped")


# ── Voice loop (runs forever in background) ───────────────────────────────────

def run_voice_loop(config, stt, tts, llm, gpio, router):
    """
    Continuous loop:
      wait_for_wake_word → conversation → wait_for_wake_word → ...
    Restarts automatically if any error occurs.
    """
    from core.conversation_agent import ConversationAgent
    agent     = ConversationAgent(stt, tts, llm, router)
    wake_word = config.get("aura", {}).get("wake_word", "aura")

    print(f"\n  ✓  Voice loop active — say '{wake_word}' to start talking\n")

    while True:
        try:
            stt.wait_for_wake_word(wake_word)
            gpio.pulse_status_led("speaking", times=2, delay=0.08)
            agent.start_conversation()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"  [Voice] Error in voice loop: {e} — restarting in 3s")
            time.sleep(3)


def start_voice_thread(config):
    """
    Build all voice components and start the background voice loop.
    Returns the thread (already started) or None if voice is disabled/broken.
    """
    if not config.get("voice", {}).get("enabled", True):
        print("  ℹ  Voice disabled in config")
        return None

    # Lazy imports — these may print their own status messages
    from core.voice_input  import VoiceInput
    from core.voice_output import VoiceOutput
    from core.llm_engine   import LLMEngine
    from core.command_router import CommandRouter
    from hardware.gpio_controller import GPIOController

    stt  = VoiceInput()
    tts  = VoiceOutput()
    llm  = LLMEngine()
    gpio = GPIOController()
    router = CommandRouter(gpio)

    # Inject device context into LLM system prompt
    try:
        llm.update_device_context(gpio.get_devices_by_room())
    except Exception:
        pass

    if not stt.enabled:
        print("  ⚠  Voice INPUT disabled (no mic / Vosk model missing)")
        print("     Text commands still work via the web dashboard.")

    if not tts.enabled:
        print("  ⚠  Voice OUTPUT disabled (no TTS engine found)")
        print("     Install: sudo apt-get install espeak-ng")

    if not stt.enabled and not tts.enabled:
        return None   # nothing to do in voice thread

    t = threading.Thread(
        target=run_voice_loop,
        args=(config, stt, tts, llm, gpio, router),
        daemon=True,
        name="voice-loop",
    )
    t.start()
    return t


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print_banner()
    config = load_config()

    print("\nSystem status:")
    check_ollama()
    check_gpio()
    check_audio()

    # Start voice listener in background
    voice_thread = start_voice_thread(config)

    # Start web server
    host = os.getenv("FLASK_HOST", config.get("web", {}).get("host", "0.0.0.0"))
    port = int(os.getenv("FLASK_PORT", config.get("web", {}).get("port", 5000)))

    try:
        import socket
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "<your-pi-ip>"

    print(f"\n  Web dashboard:")
    print(f"    http://localhost:{port}")
    print(f"    http://{ip}:{port}")
    print(f"\n  Press Ctrl+C to stop\n")

    from web.app import run_server
    run_server(host=host, port=port)


if __name__ == "__main__":
    main()
