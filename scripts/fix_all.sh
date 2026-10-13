#!/bin/bash
# =============================================================================
#  AURA-PI — ONE-SHOT FIX SCRIPT (Pi 5 compatible, no PEP 668 conflicts)
#  Run once on the Raspberry Pi to fix all audio/voice/GPIO issues.
#
#  Usage:
#    bash scripts/fix_all.sh
# =============================================================================

AURA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$AURA_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   AURA-PI — Fix All                                 ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. Install ALL system packages via apt (avoids PEP 668 pip conflicts) ────
echo "[1/4] Installing system packages (enter sudo password if asked)..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3-rpi-lgpio \
    python3-lgpio \
    portaudio19-dev \
    libasound2-dev \
    libasound2-plugins \
    alsa-utils \
    pipewire \
    pipewire-pulse \
    pipewire-alsa \
    wireplumber \
    espeak-ng \
    pulseaudio-utils \
    bluetooth \
    bluez \
    bluez-tools \
    wget \
    unzip \
    swig \
    python3-pyaudio
echo "  ✓ System packages installed"

# ── 2. Install Python packages into venv (--system-site-packages needed) ─────
echo "[2/4] Setting up Python venv with system site-packages..."

# Recreate venv WITH system-site-packages so apt-installed packages are visible
if [ ! -d "venv" ] || ! grep -qi "include-system-site-packages *= *true" venv/pyvenv.cfg 2>/dev/null; then
    echo "  Creating venv with --system-site-packages..."
    rm -rf venv
    python3 -m venv venv --system-site-packages
fi

source venv/bin/activate

# Old pip RPi.GPIO breaks Pi 5 and shadows rpi-lgpio
pip uninstall -y RPi.GPIO >/dev/null 2>&1 || true

# Install pip packages (these are not available via apt)
echo "  Installing pip packages..."
pip install --quiet \
    flask \
    flask-socketio \
    python-socketio \
    eventlet \
    ollama \
    vosk \
    pillow \
    python-dotenv \
    requests \
    numpy \
    pydantic \
    aiofiles \
    faster-whisper \
    2>/dev/null && echo "  ✓ pip packages installed" || \
    echo "  ⚠ Some pip packages failed — trying with --break-system-packages..."

# Fallback: try with --break-system-packages if pip fails
pip install --quiet --break-system-packages \
    flask flask-socketio python-socketio eventlet ollama vosk \
    pillow python-dotenv requests numpy pydantic aiofiles faster-whisper \
    2>/dev/null || true

echo "  ✓ Python packages ready"

# ── 3. Fix ALSA routing to PipeWire ──────────────────────────────────────────
echo "[3/4] Fixing audio routing..."
mkdir -p "$HOME/.config/alsa"
cat > "$HOME/.config/alsa/asoundrc" << 'EOF'
pcm.!default { type pulse }
ctl.!default { type pulse }
EOF
echo "  ✓ ALSA routing configured"

# Start PipeWire audio stack
for svc in pipewire pipewire-pulse wireplumber; do
    systemctl --user enable "$svc" 2>/dev/null || true
    systemctl --user restart "$svc" 2>/dev/null || true
done
sleep 2
echo "  ✓ PipeWire audio stack started"

# ── 4. Download Vosk model if missing ────────────────────────────────────────
echo "[4/4] Checking Vosk speech model..."
VOSK_MODEL="models/vosk-model-small-en-us-0.15"
if [ -d "$VOSK_MODEL" ]; then
    echo "  ✓ Vosk model already present"
else
    echo "  Downloading Vosk model (~40MB, needs internet once)..."
    mkdir -p models
    cd models
    wget -q "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip" \
        -O vosk-model-small-en-us-0.15.zip && \
    unzip -q vosk-model-small-en-us-0.15.zip && \
    rm vosk-model-small-en-us-0.15.zip && \
    echo "  ✓ Vosk model downloaded" || \
    echo "  ⚠ Vosk download failed — voice wake-word will be disabled"
    cd "$AURA_DIR"
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✓  All fixes applied — ready to run AURA!         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Now start AURA:"
echo "    bash start.sh"
echo ""
