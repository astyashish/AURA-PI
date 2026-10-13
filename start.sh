#!/bin/bash
# =============================================================================
#  AURA-PI — Start Script (100% local/offline, Pi 5 compatible)
# =============================================================================

AURA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$AURA_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         Starting AURA-PI on Raspberry Pi            ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Activate venv (must see apt packages: lgpio, rpi-lgpio, pyaudio) ─────────
NEED_FIX=0
if [ ! -f "venv/bin/activate" ]; then
    NEED_FIX=1
elif ! grep -qi "include-system-site-packages *= *true" venv/pyvenv.cfg 2>/dev/null; then
    echo "  ⚠ venv cannot see system packages — rebuilding..."
    rm -rf venv
    NEED_FIX=1
fi
if [ "$NEED_FIX" = "1" ]; then
    bash scripts/fix_all.sh
fi
source venv/bin/activate
echo "  ✓ Python venv activated"

# GPIO check (Pi 5 needs rpi-lgpio; old RPi.GPIO does not work)
if ! python -c "import lgpio" 2>/dev/null; then
    echo "  Installing GPIO libs via apt (sudo password may be asked)..."
    sudo apt-get install -y python3-lgpio python3-rpi-lgpio
fi
export PYTHONFAULTHANDLER=1

# ── Start PipeWire if not running ────────────────────────────────────────────
for svc in pipewire pipewire-pulse wireplumber; do
    systemctl --user is-active --quiet "$svc" 2>/dev/null || \
        systemctl --user start "$svc" 2>/dev/null || true
done
sleep 1

# ── Reconnect Bluetooth device if MAC saved ───────────────────────────────────
if [ -f ".bt_device_mac" ]; then
    BT_MAC=$(cat .bt_device_mac)
    echo "  Reconnecting BT: $BT_MAC"
    bluetoothctl connect "$BT_MAC" 2>/dev/null &
    sleep 2
fi

# ── Set BT as default audio sink if available ────────────────────────────────
BT_SINK=$(pactl list sinks short 2>/dev/null | \
    grep -i "bluez\|bluetooth\|a2dp\|hsp" | head -1 | awk '{print $2}')
if [ -n "$BT_SINK" ]; then
    pactl set-default-sink "$BT_SINK" 2>/dev/null
    echo "  ✓ Bluetooth audio: $BT_SINK"
else
    echo "  i Using default audio output (no BT sink)"
fi

# ── Start Ollama if not running ───────────────────────────────────────────────
if ! pgrep -x ollama > /dev/null; then
    echo "  Starting Ollama..."
    ollama serve > /tmp/ollama.log 2>&1 &
    for i in $(seq 1 15); do
        sleep 1
        curl -sf http://localhost:11434/api/tags > /dev/null 2>&1 && break
    done
    echo "  ✓ Ollama started"
else
    echo "  ✓ Ollama already running"
fi

# ── Launch AURA ───────────────────────────────────────────────────────────────
echo ""
echo "  Starting AURA-PI..."
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "  Dashboard: http://localhost:5000"
[ -n "$IP" ] && echo "  Network:   http://$IP:5000"
echo ""
echo "  Say 'AURA' to activate voice control"
echo "  Press Ctrl+C to stop"
echo ""

python main.py
