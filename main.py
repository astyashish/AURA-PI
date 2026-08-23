"""
AURA-PI — Main Entry Point
Starts the web server and optional background voice listener.
"""

import os
import sys
import json

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
import threading
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def load_config():
    with open("config/aura_config.json", encoding="utf-8") as f:
        return json.load(f)

def print_banner():
    print("""
╔══════════════════════════════════════════════════════╗
║          J A R V I S - P I  v1.0                    ║
║   Local AI Assistant — Raspberry Pi + Ollama         ║
║   100% Offline — No Cloud — No API Keys              ║
╚══════════════════════════════════════════════════════╝
    """)

def check_ollama():
    from core.llm_engine import LLMEngine
    llm = LLMEngine()
    if not llm.is_available():
        print("⚠  WARNING: Ollama is not running!")
        print("   Start it with: ollama serve")
        print("   Then pull a model: ollama pull qwen2.5:3b")
        print("   Aura will still start but LLM won't work until Ollama is running.")
    else:
        models = llm.list_models()
        print(f"✓  Ollama connected. Models available: {', '.join(models) if models else 'none'}")
        if not models:
            print("   Pull a model: ollama pull qwen2.5:3b")

def start_voice_wake_listener(config):
    """Start background wake word listener (if voice enabled)."""
    if not config.get("voice", {}).get("enabled", False):
        return

    from core.voice_input import VoiceInput
    from core.voice_output import VoiceOutput
    from core.llm_engine import LLMEngine
    from core.command_router import CommandRouter
    from hardware.gpio_controller import GPIOController
    from core.wake_word import WakeWordManager

    stt = VoiceInput()
    tts = VoiceOutput()

    if not stt.enabled:
        print("ℹ  Voice input disabled (Vosk model not found or PyAudio missing)")
        return

    llm = LLMEngine()
    gpio = GPIOController()
    router = CommandRouter(gpio)

    def handle_voice_command(text):
        print(f"[Voice Command] {text}")
        response = llm.chat(text)
        result = router.parse_and_execute(response)
        tts.speak(result["spoken"], blocking=False)

    wm = WakeWordManager(stt, tts, wake_word=config["aura"]["wake_word"],
                         on_command_callback=handle_voice_command)
    wm.start()
    print(f"✓  Wake word listener active — say '{config['aura']['wake_word']}'")

def main():
    print_banner()

    # Load config
    config = load_config()

    # Check Ollama
    check_ollama()

    # Start voice listener in background
    voice_thread = threading.Thread(
        target=start_voice_wake_listener,
        args=(config,),
        daemon=True
    )
    voice_thread.start()

    # Start web server
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", 5000))

    print(f"\n✓  Starting Aura web interface...")
    print(f"   Open in browser: http://localhost:{port}")
    print(f"   On network:      http://<your-pi-ip>:{port}")
    print(f"\n   Press Ctrl+C to stop\n")

    from web.app import run_server
    run_server(host=host, port=port)

if __name__ == "__main__":
    main()
