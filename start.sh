#!/bin/bash
# =============================================================================
#  AURA-PI — Start Script (100% local/offline)
#  Starts Ollama, ensures audio is up, then launches AURA.
# =============================================================================

AURA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$AURA_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         Starting AURA-PI on Raspberry Pi            ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Activate venv ─────────────────────────────────────────────────────────────
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "  ✓ Python venv activated"
else
    echo "  ⚠ No venv found. Run: bash setup.sh first"
    exit 1
fi

# ── Ensure Pi 5 GPIO compatibility ───────────────────────────────────────────
PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null || cat /proc/cpuinfo 2>/dev/null || echo "")
if echo "$PI_MODEL" | grep -q "Pi 5"; then
    if ! python3 -c "import lgpio" 2>/dev/null; then
        echo "  Configuring GPIO for Raspberry Pi 5..."
        pip uninstall -y RPi.GPIO >/dev/null 2>&1 || true
        pip install rpi-lgpio lgpio --quiet 2>/dev/null || true
    fi
fi

# ── Start PipeWire if not running ────────────────────────────────────────────
for svc in pipewire pipewire-pulse wireplumber; do
    systemctl --user is-active --quiet "$svc" 2>/dev/null || \
        systemctl --user start "$svc" 2>/dev/null || true
done
sleep 1

# ── Reconnect Bluetooth device if MAC saved ───────────────────────────────────
if [ -f ".bt_device_mac" ]; then
    BT_MAC=$(cat .bt_device_mac)
    echo "  Reconnecting BT device: $BT_MAC"
    bluetoothctl connect "$BT_MAC" 2>/dev/null &
    sleep 2
fi

# ── Set BT as default audio sink if available ────────────────────────────────
BT_SINK=$(pactl list sinks short 2>/dev/null | \
    grep -i "bluez\|bluetooth\|a2dp\|hsp" | head -1 | awk '{print $2}')
if [ -n "$BT_SINK" ]; then
    pactl set-default-sink "$BT_SINK" 2>/dev/null && \
        echo "  ✓ Bluetooth audio: $BT_SINK"
else
    echo "  ℹ Using default audio output (no BT sink)"
fi

# ── Start Ollama if not running ───────────────────────────────────────────────
if ! pgrep -x ollama > /dev/null; then
    echo "  Starting Ollama..."
    ollama serve > /tmp/ollama.log 2>&1 &
    OLLAMA_PID=$!
    # Wait for Ollama to be ready (up to 15s)
    for i in $(seq 1 15); do
        sleep 1
        curl -sf http://localhost:11434/api/tags > /dev/null 2>&1 && break
    done
    curl -sf http://localhost:11434/api/tags > /dev/null 2>&1 && \
        echo "  ✓ Ollama started (pid $OLLAMA_PID)" || \
        echo "  ⚠ Ollama may not be ready yet"
else
    echo "  ✓ Ollama already running"
fi

# ── Launch AURA ───────────────────────────────────────────────────────────────
echo ""
echo "  Starting AURA-PI..."
echo "  Open dashboard: http://localhost:5000"
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -n "$IP" ] && echo "  On network:     http://$IP:5000"
echo ""
echo "  Say 'AURA' to activate voice control"
echo "  Press Ctrl+C to stop"
echo ""

python main.py
