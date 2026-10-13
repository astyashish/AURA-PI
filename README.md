# AURA-PI — Quick Start on Raspberry Pi

## 100% Offline — No Internet Needed After Setup

---

## First Time: Full Setup (needs internet once)

```bash
cd /home/ashish/AURA-PI
chmod +x setup.sh scripts/*.sh
bash setup.sh
```

Then pair earbuds:
```bash
bash scripts/setup_bluetooth.sh
```

---

## Every Day: Start AURA

```bash
cd /home/ashish/AURA-PI
bash start.sh
```

Open browser: **http://localhost:5000**

---

## If Voice Not Working

```bash
bash scripts/fix_all.sh
```

This fixes:
- ALSA → PipeWire audio routing
- GPIO library for Pi 5 (lgpio)
- PyAudio, Vosk, Whisper installs
- Vosk model download

---

## Voice Commands

Say **"AURA"** then:
- "Turn on bedroom light"
- "Turn off all lights"  
- "Dim desk light to 50 percent"
- "What time is it?"
- "Tell me a joke"
- Say **"goodbye"** to end conversation

---

## GPIO Pin Connections

| BCM Pin | Connect To | Device |
|---------|-----------|--------|
| 17 | LED + resistor | Living Room Light |
| 4 | LED + resistor | Living Room Lamp |
| 27 | LED + resistor | Bedroom Light |
| 18 | LED + resistor | Night Light |
| 5 | LED + resistor | Desk Light |
| 19 | LED + resistor | Kitchen Light |
| 6 | Relay IN | Ceiling Fan |
| 13 | Relay IN | Bedroom Fan |
| 22 | Blue LED | Status: Thinking |
| 23 | Green LED | Status: Speaking |
| 24 | Red LED | Status: Camera |
| GND | GND | Common Ground |

Use **330Ω resistor** with each LED.

---

## Files Changed (This Session)

| File | Fix |
|------|-----|
| `core/voice_input.py` | ALSA errors suppressed, mic probe before enable |
| `core/voice_output.py` | BT sink auto-detect, paplay/aplay/pw-play fallback |
| `core/conversation_agent.py` | Crash-safe loop, status LEDs, silence timeout |
| `core/llm_engine.py` | Unchanged |
| `hardware/gpio_controller.py` | Pi 5 lgpio support |
| `hardware/lgpio_wrapper.py` | NEW: Pi 5 GPIO backend |
| `main.py` | Auto-restart voice, BT/GPIO status on boot |
| `start.sh` | PipeWire + BT + Ollama startup order |
| `scripts/fix_all.sh` | NEW: One-shot fix for all issues |
| `scripts/setup_bluetooth.sh` | Full BT pairing with auto-reconnect |
| `setup.sh` | Pi 5 GPIO, PipeWire, systemd service |
