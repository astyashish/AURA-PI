#!/bin/bash
# =============================================================================
#  AURA-PI — ONE-SHOT FIX SCRIPT
#  Run this on the Raspberry Pi to fix ALL audio/voice/GPIO issues at once.
#  Works fully offline after running setup.sh once.
#
#  Usage:
#    chmod +x scripts/fix_all.sh
#    bash scripts/fix_all.sh
# =============================================================================

set -e
AURA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$AURA_DIR"
source venv/bin/activate 2>/dev/null || true

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   AURA-PI — Fix All Script                          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. Fix ALSA → PulseAudio routing ─────────────────────────────────────────
echo "[1/6] Fixing ALSA audio routing..."
mkdir -p "$HOME/.config/alsa"
cat > "$HOME/.config/alsa/asoundrc" << 'EOF'
pcm.!default { type pulse }
ctl.!default { type pulse }
pcm.pulse    { type pulse }
ctl.pulse    { type pulse }
EOF
echo "  ✓ ~/.config/alsa/asoundrc written"

# ── 2. Start PipeWire audio stack ─────────────────────────────────────────────
echo "[2/6] Starting PipeWire audio stack..."
# Stop legacy PulseAudio standalone (if any)
systemctl --user stop pulseaudio.socket pulseaudio.service 2>/dev/null || true
systemctl --user mask pulseaudio.service 2>/dev/null || true

# Start PipeWire (replaces PulseAudio, provides pipewire-pulse compatibility)
for svc in pipewire pipewire-pulse wireplumber; do
    systemctl --user enable "$svc" 2>/dev/null || true
    systemctl --user restart "$svc" 2>/dev/null || true
    sleep 0.5
    systemctl --user is-active --quiet "$svc" && \
        echo "  ✓ $svc running" || echo "  ⚠ $svc not started"
done
sleep 2

# ── 3. Fix GPIO for Pi 5 ──────────────────────────────────────────────────────
echo "[3/6] Fixing GPIO library..."
PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null || echo "unknown")
if echo "$PI_MODEL" | grep -q "Pi 5"; then
    echo "  Pi 5 detected — installing rpi-lgpio..."
    pip install rpi-lgpio --quiet 2>/dev/null && echo "  ✓ rpi-lgpio installed" \
        || echo "  ⚠ rpi-lgpio failed — trying lgpio..."
    pip install lgpio --quiet 2>/dev/null && echo "  ✓ lgpio installed" || true
else
    echo "  Pi 4/older — ensuring RPi.GPIO..."
    pip install RPi.GPIO --quiet 2>/dev/null && echo "  ✓ RPi.GPIO installed" || true
fi

# ── 4. Ensure audio packages ──────────────────────────────────────────────────
echo "[4/6] Ensuring audio packages..."
sudo apt-get install -y -qq \
    portaudio19-dev libasound2-dev libasound2-plugins \
    pipewire pipewire-pulse pipewire-alsa wireplumber \
    espeak-ng pulseaudio-utils \
    2>/dev/null || true

pip install pyaudio --quiet 2>/dev/null && echo "  ✓ pyaudio" || \
    echo "  ⚠ pyaudio failed — try: sudo apt-get install python3-pyaudio"
pip install vosk --quiet 2>/dev/null && echo "  ✓ vosk" || true
pip install faster-whisper --quiet 2>/dev/null && echo "  ✓ faster-whisper" || true

# ── 5. Download Vosk model if missing ─────────────────────────────────────────
echo "[5/6] Checking Vosk model..."
VOSK_MODEL="models/vosk-model-small-en-us-0.15"
if [ ! -d "$VOSK_MODEL" ]; then
    echo "  Downloading Vosk model (~40MB)..."
    mkdir -p models
    cd models
    wget -q "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip" \
        -O vosk-model-small-en-us-0.15.zip
    unzip -q vosk-model-small-en-us-0.15.zip
    rm vosk-model-small-en-us-0.15.zip
    cd "$AURA_DIR"
    echo "  ✓ Vosk model downloaded"
else
    echo "  ✓ Vosk model present"
fi

# ── 6. Verify everything ──────────────────────────────────────────────────────
echo "[6/6] Verification..."

# Audio devices
echo "  Audio sinks:"
pactl list sinks short 2>/dev/null | sed 's/^/    /' || echo "    (pactl not available)"

echo "  Audio sources (microphones):"
pactl list sources short 2>/dev/null | grep -v "monitor" | sed 's/^/    /' \
    || echo "    (pactl not available)"

# Python imports
python3 - <<'PYEOF'
import sys
results = []

try:
    import pyaudio
    pa = pyaudio.PyAudio()
    n = pa.get_device_count()
    ins  = sum(1 for i in range(n) if pa.get_device_info_by_index(i).get("maxInputChannels",0)>0)
    outs = sum(1 for i in range(n) if pa.get_device_info_by_index(i).get("maxOutputChannels",0)>0)
    pa.terminate()
    results.append(f"  ✓ PyAudio: {ins} input, {outs} output devices")
except Exception as e:
    results.append(f"  ✗ PyAudio: {e}")

try:
    import vosk
    results.append("  ✓ Vosk library OK")
except ImportError:
    results.append("  ✗ Vosk: pip install vosk")

try:
    from faster_whisper import WhisperModel
    results.append("  ✓ faster-whisper OK")
except ImportError:
    results.append("  ✗ faster-whisper: pip install faster-whisper")

for r in results:
    print(r)
PYEOF

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✓  All fixes applied!                             ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Now start AURA:"
echo "    ollama serve &"
echo "    python main.py"
echo ""
echo "  Or run the diagnostic first:"
echo "    python scripts/diagnose.py"
echo ""
