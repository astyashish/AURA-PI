#!/bin/bash
# =============================================================================
#  AURA-PI Complete Setup Script — Raspberry Pi 5 (and Pi 4)
#  Fixes: GPIO (lgpio for Pi 5), Audio (PipeWire), Bluetooth earbuds, Piper TTS
# =============================================================================

set -e

AURA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$AURA_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         AURA-PI Complete Setup — Raspberry Pi 5     ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Detect Pi version ─────────────────────────────────────────────────────────
PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null || echo "unknown")
echo "[Info] Board: $PI_MODEL"
IS_PI5=false
if echo "$PI_MODEL" | grep -q "Pi 5"; then
  IS_PI5=true
  echo "[Info] Raspberry Pi 5 detected — will use lgpio backend"
else
  echo "[Info] Raspberry Pi 4 or older detected — will try RPi.GPIO"
fi

# ── [1/9] System packages ─────────────────────────────────────────────────────
echo ""
echo "[1/9] Updating system packages..."
sudo apt-get update -qq

echo "[1/9] Installing system dependencies..."
sudo apt-get install -y -qq \
  python3-pip python3-venv git curl wget unzip \
  portaudio19-dev libasound2-dev libasound2-plugins \
  ffmpeg libopenblas-dev libopenblas0 \
  build-essential cmake \
  espeak espeak-ng espeak-data \
  alsa-utils pulseaudio pulseaudio-utils \
  bluez bluez-tools \
  pipewire pipewire-pulse pipewire-alsa wireplumber \
  libcamera-dev python3-libcamera \
  v4l-utils \
  2>/dev/null || true

echo "[1/9] ✓ System packages installed"

# ── [2/9] GPIO library ────────────────────────────────────────────────────────
echo ""
echo "[2/9] Installing GPIO library..."

if [ "$IS_PI5" = true ]; then
  echo "  Pi 5: installing lgpio + rpi-lgpio..."
  sudo apt-get install -y -qq python3-lgpio 2>/dev/null || true
  pip install lgpio 2>/dev/null || true
  # rpi-lgpio provides RPi.GPIO-compatible interface backed by lgpio
  pip install rpi-lgpio 2>/dev/null && echo "  ✓ rpi-lgpio installed (Pi 5 GPIO)" \
    || echo "  ⚠ rpi-lgpio install failed — lgpio_wrapper will be used"
else
  echo "  Pi 4: installing RPi.GPIO..."
  pip install RPi.GPIO 2>/dev/null && echo "  ✓ RPi.GPIO installed" \
    || echo "  ⚠ RPi.GPIO install failed — mock GPIO will be used"
fi

# ── [3/9] Python virtual environment ─────────────────────────────────────────
echo ""
echo "[3/9] Creating Python virtual environment..."
python3 -m venv venv --system-site-packages
source venv/bin/activate

echo "[3/9] Installing Python packages..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# GPIO in venv
if [ "$IS_PI5" = true ]; then
  pip install rpi-lgpio -q 2>/dev/null || pip install lgpio -q 2>/dev/null || true
else
  pip install RPi.GPIO -q 2>/dev/null || true
fi

echo "[3/9] ✓ Python environment ready"

# ── [4/9] Audio / PipeWire ────────────────────────────────────────────────────
echo ""
echo "[4/9] Configuring audio (PipeWire/PulseAudio)..."

# Stop PulseAudio standalone if running (PipeWire replaces it)
systemctl --user stop pulseaudio.service pulseaudio.socket 2>/dev/null || true
systemctl --user disable pulseaudio.service pulseaudio.socket 2>/dev/null || true
systemctl --user mask pulseaudio.service 2>/dev/null || true

# Enable PipeWire services
systemctl --user enable pipewire pipewire-pulse wireplumber 2>/dev/null || true
systemctl --user start pipewire pipewire-pulse wireplumber 2>/dev/null || true

# Create ALSA config to use PulseAudio (PipeWire-pulse)
mkdir -p "$HOME/.config/alsa"
cat > "$HOME/.config/alsa/asoundrc" << 'ALSA_EOF'
# Route ALSA output through PulseAudio/PipeWire
pcm.!default {
    type pulse
}
ctl.!default {
    type pulse
}
pcm.pulse {
    type pulse
}
ctl.pulse {
    type pulse
}
ALSA_EOF

echo "[4/9] ✓ Audio (PipeWire) configured"

# ── [5/9] Bluetooth setup ─────────────────────────────────────────────────────
echo ""
echo "[5/9] Configuring Bluetooth..."

# Enable Bluetooth service
sudo systemctl enable bluetooth 2>/dev/null || true
sudo systemctl start bluetooth 2>/dev/null || true

# Enable BT audio in PipeWire
mkdir -p "$HOME/.config/pipewire/pipewire.conf.d"
cat > "$HOME/.config/pipewire/pipewire.conf.d/51-bluetooth-policy.conf" << 'BT_CONF_EOF'
context.modules = [
  { name = libpipewire-module-bluetooth-autoconnect }
]
BT_CONF_EOF

# WirePlumber Bluetooth config
mkdir -p "$HOME/.config/wireplumber/bluetooth.lua.d"
cat > "$HOME/.config/wireplumber/bluetooth.lua.d/51-bluez-config.lua" << 'LUA_EOF'
bluez_monitor.properties = {
  ["bluez5.enable-sbc-xq"] = true,
  ["bluez5.enable-msbc"] = true,
  ["bluez5.enable-hw-volume"] = true,
  ["bluez5.headset-roles"] = "[ hsp_hs hsp_ag hfp_hf hfp_ag ]",
  ["bluez5.codecs"] = "[ sbc sbc_xq aac ldac aptx aptx_hd ]",
  ["bluez5.hfphsp-backend"] = "native",
}
LUA_EOF

# Install blueman (Bluetooth manager GUI) if desktop available
sudo apt-get install -y -qq blueman 2>/dev/null || true

echo "[5/9] ✓ Bluetooth configured"

# ── [6/9] Ollama ──────────────────────────────────────────────────────────────
echo ""
echo "[6/9] Installing Ollama..."
if ! command -v ollama &>/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
  echo "  ✓ Ollama installed"
else
  echo "  ✓ Ollama already installed"
fi

# Pull models
ollama serve &
OLLAMA_PID=$!
sleep 5

echo "  Pulling qwen2.5:3b (main model)..."
ollama pull qwen2.5:3b 2>/dev/null || echo "  ⚠ qwen2.5:3b pull failed"
echo "  Pulling qwen2.5:0.5b (fast/low RAM)..."
ollama pull qwen2.5:0.5b 2>/dev/null || echo "  ⚠ qwen2.5:0.5b pull failed"
echo "  Pulling gemma2:2b..."
ollama pull gemma2:2b 2>/dev/null || echo "  ⚠ gemma2:2b pull failed"
echo "  Pulling llava:7b (vision)..."
ollama pull llava:7b 2>/dev/null || echo "  ⚠ llava:7b pull failed"

kill $OLLAMA_PID 2>/dev/null || true
echo "[6/9] ✓ Ollama ready"

# ── [7/9] Vosk speech model ───────────────────────────────────────────────────
echo ""
echo "[7/9] Downloading Vosk speech model..."
mkdir -p models
cd models

if [ ! -d "vosk-model-small-en-us-0.15" ]; then
  wget -q "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip" \
    -O vosk-model-small-en-us-0.15.zip
  unzip -q vosk-model-small-en-us-0.15.zip
  rm vosk-model-small-en-us-0.15.zip
  echo "  ✓ Vosk model downloaded"
else
  echo "  ✓ Vosk model already present"
fi

# ── [8/9] Piper TTS ───────────────────────────────────────────────────────────
echo ""
echo "[8/9] Installing Piper TTS..."

PIPER_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz"

if [ ! -f "/usr/local/bin/piper" ]; then
  wget -q "$PIPER_URL" -O piper_linux_aarch64.tar.gz || \
    { echo "  ⚠ Piper download failed — espeak-ng will be used"; }

  if [ -f "piper_linux_aarch64.tar.gz" ]; then
    tar -xzf piper_linux_aarch64.tar.gz 2>/dev/null || true
    sudo cp piper/piper /usr/local/bin/piper 2>/dev/null || \
      sudo mv piper /usr/local/bin/piper 2>/dev/null || \
      echo "  ⚠ Could not install Piper globally"
    rm -rf piper_linux_aarch64.tar.gz piper 2>/dev/null || true
    echo "  ✓ Piper installed"
  fi
else
  echo "  ✓ Piper already installed"
fi

mkdir -p voices
if [ ! -f "voices/en_US-lessac-medium.onnx" ]; then
  echo "  Downloading Piper voice model (lessac medium)..."
  BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"
  wget -q "$BASE/en_US-lessac-medium.onnx" -O voices/en_US-lessac-medium.onnx || true
  wget -q "$BASE/en_US-lessac-medium.onnx.json" -O voices/en_US-lessac-medium.onnx.json || true
  echo "  ✓ Voice model downloaded"
else
  echo "  ✓ Voice model already present"
fi

cd "$AURA_DIR"
echo "[8/9] ✓ Piper TTS ready"

# ── [9/9] Final configuration ─────────────────────────────────────────────────
echo ""
echo "[9/9] Final configuration..."

if [ ! -f ".env" ]; then
  cp .env.example .env 2>/dev/null || cat > .env << 'ENV_EOF'
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
OLLAMA_HOST=http://localhost:11434
DEFAULT_MODEL=qwen2.5:3b
ENABLE_GPIO=true
ENV_EOF
  echo "  ✓ .env created"
fi

mkdir -p captured_images

# Systemd service
echo ""
echo "  Creating systemd service..."
sudo tee /etc/systemd/system/aura-pi.service > /dev/null << SERVICE_EOF
[Unit]
Description=AURA-PI AI Assistant
After=network.target bluetooth.target sound.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$AURA_DIR
Environment="PATH=$AURA_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
Environment="ENABLE_GPIO=true"
ExecStartPre=/bin/bash -c 'ollama serve & sleep 3'
ExecStart=$AURA_DIR/venv/bin/python main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE_EOF

sudo systemctl daemon-reload
sudo systemctl enable aura-pi.service
echo "  ✓ systemd service installed and enabled"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✓  AURA-PI Setup Complete!                        ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Next steps:"
echo ""
echo "  1. PAIR Bluetooth earbuds:"
echo "     bash scripts/setup_bluetooth.sh"
echo ""
echo "  2. START AURA-PI:"
echo "     source venv/bin/activate"
echo "     ollama serve &"
echo "     python main.py"
echo ""
echo "  3. Or use systemd (auto-start on boot):"
echo "     sudo systemctl start aura-pi"
echo "     sudo systemctl status aura-pi"
echo ""
echo "  4. Open dashboard:"
echo "     http://localhost:5000"
echo "     http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "  GPIO pins wired:"
echo "    PIN 17 → Living Room Light"
echo "    PIN 4  → Living Room Lamp"
echo "    PIN 27 → Bedroom Light"
echo "    PIN 18 → Night Light"
echo "    PIN 5  → Desk Light"
echo "    PIN 19 → Kitchen Light"
echo "    PIN 6  → Ceiling Fan"
echo "    PIN 13 → Bedroom Fan"
echo "    PIN 22 → Status LED (thinking)"
echo "    PIN 23 → Status LED (speaking)"
echo "    PIN 24 → Status LED (camera)"
echo ""
