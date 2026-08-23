# 🤖 AURA-PI — Local AI Assistant for Raspberry Pi

A fully offline Aura-style AI assistant. Voice commands, text chat, image recognition, GPIO hardware control — all running locally using Ollama LLMs. No internet required after setup.

## Features
- 🎤 Voice input (Vosk STT, offline)
- 🔊 Voice output (Piper TTS, offline)
- 🧠 Multiple local LLMs via Ollama (Gemma, Qwen, LLaVA)
- 📷 Camera + image recognition (LLaVA vision model)
- 💡 GPIO light/relay control via LLM commands
- 🌐 Beautiful sci-fi web dashboard (Flask + SocketIO)
- 💬 Text chat + voice chat both supported
- 🔌 Works on Raspberry Pi 5 AND Windows/Linux (dev mode)

## Quick Start (Raspberry Pi)
```bash
git clone https://github.com/YOUR_USERNAME/aura-pi.git
cd aura-pi
chmod +x setup.sh
./setup.sh
python main.py
```

## Quick Start (Windows)
```cmd
git clone https://github.com/YOUR_USERNAME/aura-pi.git
cd aura-pi
setup_windows.bat
python main.py
```

Then open: http://localhost:5000

## Hardware Required (for full GPIO features)
- Raspberry Pi 5 (8GB RAM recommended)
- USB Microphone
- Speaker (3.5mm or USB)
- LEDs + 220Ω resistors (or relay module for actual lights)
- USB Webcam or Pi Camera Module

## GPIO Pin Layout
| Device | GPIO Pin | Description |
|--------|----------|-------------|
| Living Room Light | GPIO 17 | LED/Relay |
| Bedroom Light | GPIO 27 | LED/Relay |
| Status LED (Blue) | GPIO 22 | Aura thinking indicator |
| Status LED (Green) | GPIO 23 | Aura speaking indicator |
| Camera LED | GPIO 24 | Camera active indicator |
